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

from app.alerts import (Alert, ApplicationBrief, VacancyBrief,
                        silence_alerts, unsent, vacancy_alerts)
from app.collect import collect
from app.dedup import Publication, find_reposts
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
        else:
            # Тиша теж буває змістовною: прогін відбувся і нового не знайшов.
            # У канал це не шлемо — щогодинне «нічого нового» перестали б
            # читати, а з ним і решту, — але в лог іде завжди.
            log.info("прогін завершено: нових вакансій немає")


async def announce_new(session) -> None:
    """Сповістити про вакансії, які варті уваги просто зараз."""
    vacancies = list((await session.execute(select(Vacancy))).scalars())
    applied = {
        a.vacancy_id for a in (await session.execute(
            select(Application).where(Application.vacancy_id.isnot(None))
        )).scalars()
    }

    # Перевипуск не дає другого сповіщення: це та сама вакансія, яку
    # майданчик опублікував удруге. У переліку старішу видно (на неї могло
    # бути подано), а повідомляти про неї означало б слати дублікат.
    reposts = find_reposts([
        Publication(url=v.url, source_key=v.source_key,
                    company_norm=v.company_norm, title_norm=v.title_norm,
                    posted_at=v.posted_at)
        for v in vacancies
    ])

    briefs = []
    for v in vacancies:
        if v.id in applied or v.url in reposts:
            continue
        verdict = assess(format=v.format, years_required=v.years_required,
                         english=v.english, location=v.location)
        content = screen(v.raw_text, v.title)
        briefs.append(VacancyBrief(
            id=v.id, url=v.url, company=v.company, title=v.title,
            source_key=v.source_key, state=verdict.state, fit=content.fit,
            replies=v.replies,
            posted_on=v.posted_at.date() if v.posted_at else None,
            format=v.format, years_required=v.years_required,
            english=v.english, location=v.location,
            matched=tuple(content.matched), gaps=tuple(content.gaps),
        ))

    alerts = unsent(vacancy_alerts(briefs), await already_sent(session))
    if not alerts:
        return

    # Зведення попереду переліку: воно відповідає на питання «скільки з
    # того, що зібрано, взагалі варте уваги», якого окремі картки не
    # закривають. Ключ несе дату — зведення за різні дні різні за змістом,
    # на відміну від картки вакансії, яка назавжди та сама.
    fit = sum(1 for b in briefs if b.state == "ok"
              and b.fit in {"strong", "possible"})
    summary = Alert(
        key=f"digest:{date.today():%Y-%m-%d}:{len(alerts)}",
        text=(f"<b>Нових вакансій: {len(alerts)}</b>\n"
              f"Усього в переліку {len(briefs)}, придатних {fit}, "
              f"подано на {len(applied)}."),
    )
    alerts = unsent([summary], await already_sent(session)) + alerts

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
