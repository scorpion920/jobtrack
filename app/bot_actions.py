"""Обробка натискань на кнопки під сповіщеннями.

Опитування, а не webhook: система працює на машині оператора за NAT, і
достукатись до неї ззовні неможливо. Той самий принцип, що й у доставці
релізів на інсталяції клієнтів — ініціатива завжди на боці того, хто за
фаєрволом.

Дві дії, і обидві існують заради одного: зробити дотиком те, що досі
коштувало окремої розмови.

* **Подав** — створює запис у журналі, зв'язаний із вакансією. Без цього
  подачу доводиться вносити руками, а крок, який легко пропустити, зрештою
  пропускають — і вимірювання втрачає сенс.
* **Не цікавить** — ховає вакансію з переліку. Відмова при цьому НЕ
  зникає: саме з відмов оператора за один вечір народилось п'ять правил
  скринера. Вакансія лишається в базі позначеною, щоб колись можна було
  спитати «а що саме я відхиляв».
"""

from __future__ import annotations

import logging
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Application, ApplicationEvent, BotState, Channel, Status, Vacancy
from app.notify import NotConfigured, call

log = logging.getLogger("jobtrack.bot")


async def _offset(session: AsyncSession) -> BotState:
    state = (await session.execute(select(BotState))).scalars().first()
    if not state:
        state = BotState(update_offset=0)
        session.add(state)
        await session.flush()
    return state


async def _apply(session: AsyncSession, action: str, vacancy_id: int) -> str:
    vacancy = (await session.execute(
        select(Vacancy).where(Vacancy.id == vacancy_id)
    )).scalar_one_or_none()
    if not vacancy:
        return "вакансії вже немає в базі"

    if action == "skip":
        vacancy.dismissed = True
        return f"🚫 приховано: {vacancy.company}"

    existing = (await session.execute(
        select(Application).where(Application.vacancy_id == vacancy_id)
    )).scalar_one_or_none()
    if existing:
        return f"вже записано раніше: {vacancy.company}"

    app = Application(
        company=vacancy.company, position=vacancy.title, url=vacancy.url,
        channel=Channel(vacancy.source_key) if vacancy.source_key in
        Channel.__members__ else Channel.other,
        applied_on=date.today(), vacancy_id=vacancy_id,
    )
    session.add(app)
    await session.flush()
    session.add(ApplicationEvent(application_id=app.id, status=Status.sent,
                                 occurred_on=date.today(), origin="telegram"))
    return f"✅ записано: {vacancy.company} — {vacancy.title[:40]}"


async def poll(session: AsyncSession) -> int:
    """Забрати натискання й виконати їх. Повертає кількість опрацьованих."""
    state = await _offset(session)
    try:
        data = await call("getUpdates", {"offset": state.update_offset + 1,
                                         "timeout": 0, "limit": 50,
                                         "allowed_updates": ["callback_query"]})
    except NotConfigured:
        return 0

    handled = 0
    for update in data.get("result", []):
        state.update_offset = max(state.update_offset, update["update_id"])
        query = update.get("callback_query")
        if not query:
            continue

        payload = query.get("data", "")
        action, _, raw_id = payload.partition(":")
        if action not in {"applied", "skip"} or not raw_id.isdigit():
            continue

        answer = await _apply(session, action, int(raw_id))
        handled += 1
        # Відповідь спливає над кнопкою: дія без підтвердження виглядає як
        # дія, що не спрацювала.
        try:
            await call("answerCallbackQuery",
                       {"callback_query_id": query["id"], "text": answer})
        except Exception as exc:                  # noqa: BLE001
            log.warning("не вдалось відповісти на натискання: %s", type(exc).__name__)
        log.info("дія з телеграму: %s → %s", payload, answer)

    await session.commit()
    return handled
