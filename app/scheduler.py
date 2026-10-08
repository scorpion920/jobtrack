"""Розклад фонових робіт.

APScheduler у тому ж процесі, а не Celery — рішення зафіксоване в ADR 0001.
Коротко: черга задач дала б мінус один контейнер і плюс дві залежності заради
навантаження, яке вміщається в кілька запитів на годину. Для портфоліо
свідомий вибір простішого інструмента є кращим сигналом, ніж Celery «бо так
заведено».

Три роботи, і темп кожної заданий не зручністю, а природою джерела:

* **збір** — раз на годину. Djinni віддає 15 найсвіжіших вакансій за фільтром,
  тож рідший темп означав би пропускати ті, що встигли витіснитись; частіший
  не дав би нічого, крім навантаження на чужий майданчик;
* **сповіщення** — одразу після збору, бо повідомляти нема про що, поки не
  зібрано;
* **нагадування про тишу** — раз на добу вранці. Подача, що мовчить десять
  днів, не стане терміновою через годину.

Усі роботи `coalesce=True` і `max_instances=1`: якщо машина спала, після
прокидання має виконатись ОДИН прогін, а не черга пропущених.
"""

from __future__ import annotations

import logging
from datetime import date

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

from app.alerts import (ApplicationBrief, VacancyBrief, silence_alerts,
                        unsent, vacancy_alerts)
from app.collect import collect
from app.db import get_sessionmaker
from app.models import Application, SourceConfig, Vacancy
from app.notify import NotConfigured, already_sent, deliver
from app.screen import assess
from app.screening import screen

log = logging.getLogger("jobtrack.scheduler")


async def collect_all() -> None:
    """Зібрати всі активні канали й повідомити про нові придатні вакансії."""
    async with get_sessionmaker()() as session:
        configs = list((await session.execute(
            select(SourceConfig).where(SourceConfig.active.is_(True))
        )).scalars())

        fresh: list[int] = []
        for config in configs:
            report = await collect(session, config)
            if report.error:
                # Канал, що впав, не зупиняє решту: джерела незалежні.
                log.error("канал %s: %s", config.key, report.error)
                continue
            log.info("канал %s: знайдено %d, нових %d",
                     config.key, report.found, report.created)
            fresh.append(report.created)

        if sum(fresh):
            await announce_new(session)


async def announce_new(session) -> None:
    """Сповістити про вакансії, які варті уваги просто зараз."""
    vacancies = list((await session.execute(select(Vacancy))).scalars())
    applied = {
        a.vacancy_id for a in (await session.execute(
            select(Application).where(Application.vacancy_id.isnot(None))
        )).scalars()
    }

    briefs = []
    for v in vacancies:
        if v.id in applied:
            continue
        verdict = assess(format=v.format, years_required=v.years_required,
                         english=v.english, location=v.location)
        content = screen(v.raw_text, v.title)
        briefs.append(VacancyBrief(
            id=v.id, url=v.url, company=v.company, title=v.title,
            source_key=v.source_key, state=verdict.state, fit=content.fit,
            replies=v.replies,
            posted_on=v.posted_at.date() if v.posted_at else None,
        ))

    alerts = unsent(vacancy_alerts(briefs), await already_sent(session))
    if not alerts:
        return
    try:
        sent, failed = await deliver(session, alerts)
        log.info("сповіщень надіслано %d, не вдалося %d", sent, failed)
    except NotConfigured as exc:
        # Не налаштований бот — стан, а не помилка. Але ГУЧНИЙ: інакше
        # «немає про що повідомляти» і «нема куди повідомляти» виглядали б
        # однаково, і це та сама пара, через яку збирач мовчав три години.
        log.warning("сповіщення не надіслані: %s", exc)


async def remind_silence() -> None:
    """Нагадати про подачі, які мовчать довше за норму."""
    async with get_sessionmaker()() as session:
        from sqlalchemy.orm import selectinload

        apps = list((await session.execute(
            select(Application).options(selectinload(Application.events))
        )).scalars())

        briefs = [ApplicationBrief(
            id=a.id, company=a.company, position=a.position,
            channel=a.channel.value, days_silent=a.days_silent,
            current_status=a.current_status.value if a.current_status else "sent",
        ) for a in apps]

        alerts = unsent(silence_alerts(briefs), await already_sent(session))
        if not alerts:
            return
        try:
            await deliver(session, alerts)
        except NotConfigured as exc:
            log.warning("нагадування не надіслані: %s", exc)


def build(today: date | None = None) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="Europe/Kyiv")
    scheduler.add_job(collect_all, "interval", hours=1, id="collect",
                      coalesce=True, max_instances=1, misfire_grace_time=600)
    scheduler.add_job(remind_silence, "cron", hour=9, minute=30, id="silence",
                      coalesce=True, max_instances=1, misfire_grace_time=3600)
    return scheduler
