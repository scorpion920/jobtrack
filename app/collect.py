"""Прогін збору: канал → план → запис.

Тонкий шар навмисно. Усе, у чому можна помилитись, лежить окремо й
перевіряється без бази: розбір — у `sources/djinni.py`, рішення — в
`ingest.py`. Тут лишилось тільки те, що без БД не існує.

Стан каналу записується ЗАВЖДИ, включно з невдачею. Причина та сама, що й у
журналі прогонів збирача статусів: найчастіша поломка збору — не падіння, а
тиша, і відрізнити «канал не запускався» від «запустився й нічого не знайшов»
можна лише тоді, коли обидва випадки лишають слід.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ingest import KnownVacancy, plan_ingest
from app.models import SourceConfig, Vacancy, VacancyRaw
from app.sources.registry import build


@dataclass
class CollectReport:
    source_key: str
    found: int = 0
    created: int = 0
    refreshed: int = 0
    cross_channel: int = 0
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


async def collect(session: AsyncSession, config: SourceConfig) -> CollectReport:
    report = CollectReport(source_key=config.key)
    now = datetime.now(timezone.utc)

    try:
        source = build(config.kind, config.key, config.params or {})
        rows = list(await source.fetch())
    except Exception as exc:                     # noqa: BLE001
        # Широкий перехват свідомий: канал ходить у чужу систему, і спосіб
        # зламатися там будь-який. Важливо не ЩО саме сталось, а щоб причина
        # дійшла до оператора, а не осіла в логах контейнера.
        report.error = f"{type(exc).__name__}: {exc}"
        config.last_run_at, config.last_error, config.last_found = now, report.error, None
        await session.commit()
        return report

    report.found = len(rows)

    known = [
        KnownVacancy(id=v.id, source_key=v.source_key, external_id=v.external_id,
                     company_norm=v.company_norm, title_norm=v.title_norm,
                     replies=v.replies)
        for v in (await session.execute(select(Vacancy))).scalars()
    ]

    plan = plan_ingest(rows, known, now)

    for item in plan.create:
        raw = item.raw
        vacancy = Vacancy(
            source_key=raw.source_key, external_id=raw.external_id,
            url=raw.url, title=raw.title, company=raw.company,
            company_norm=item.company_norm, title_norm=item.title_norm,
            posted_at=raw.posted_at,
            format=item.format, years_required=item.years_required,
            english=item.english, part_time=item.part_time, location=item.location,
            replies=raw.payload.get("replies"), views=raw.payload.get("views"),
            salary_tier=raw.payload.get("salary_tier"),
            raw_text=raw.raw_text, first_seen=now, last_seen=now,
        )
        session.add(vacancy)
        await session.flush()
        # Сире тіло — щоб виправлений розбір проганявся по збереженому.
        session.add(VacancyRaw(vacancy_id=vacancy.id, payload=raw.payload, fetched_at=now))

    by_id = {v.id: v for v in (await session.execute(select(Vacancy))).scalars()}
    for upd in plan.refresh:
        vacancy = by_id.get(upd.vacancy_id)
        if not vacancy:
            continue
        vacancy.last_seen = upd.last_seen
        if upd.replies is not None:
            vacancy.replies = upd.replies
        if upd.views is not None:
            vacancy.views = upd.views

    report.created = len(plan.create)
    report.refreshed = len(plan.refresh)
    report.cross_channel = len(plan.cross_channel)

    config.last_run_at, config.last_found, config.last_error = now, report.found, None
    await session.commit()
    return report
