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

from app.models import (Application, ApplicationEvent, BotState, Channel,
                        Notification, Status, Vacancy)
from app.alerts import esc
from app.config import get_settings
from app.draft import prepare as prepare_draft
from app.notify import NotConfigured, _safe, call
from app.screening import screen

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

    # Назва компанії й посада приходять із майданчика, а підтвердження
    # вставляється в <b>…</b> із parse_mode=HTML. Без екранування вакансія
    # «Senior AI/ML Engineer (Python, LLM & RAG)» — вона є в базі — дала б
    # 400 Bad Request, і позначка не з'явилась би саме там, де дію виконано.
    if action == "skip":
        vacancy.dismissed = True
        return f"🚫 приховано: {esc(vacancy.company)}"

    existing = (await session.execute(
        select(Application).where(Application.vacancy_id == vacancy_id)
    )).scalar_one_or_none()
    if existing:
        return f"вже записано раніше: {esc(vacancy.company)}"

    # Версію резюме записуємо САМІ, а не лишаємо порожньою.
    #
    # Вимір 09.10.2026: три подачі з дев'яти не мали версії — рівно ті, що
    # зроблені кнопкою. А воронка «за треком» існує саме для того, щоб
    # порівняти варіанти резюме між собою: без версії подача в неї не
    # потрапляє, і кнопка, задумана як спрощення, тихо псувала вимірювання.
    #
    # Трек система вже визначила, коли вирішувала, чи вартий лист: беремо
    # той самий, щоб у журналі стояло рівно те, що оператор і надіслав.
    content = screen(vacancy.raw_text, vacancy.title)
    draft = prepare_draft(title=vacancy.title, raw_text=vacancy.raw_text,
                          matched=content.matched, gaps=content.gaps,
                          replies=vacancy.replies, english=vacancy.english)

    app = Application(
        company=vacancy.company, position=vacancy.title, url=vacancy.url,
        channel=Channel(vacancy.source_key) if vacancy.source_key in
        Channel.__members__ else Channel.other,
        applied_on=date.today(), vacancy_id=vacancy_id,
        cv_version=f"CV_{draft.track}",
    )
    session.add(app)
    await session.flush()
    session.add(ApplicationEvent(application_id=app.id, status=Status.sent,
                                 occurred_on=date.today(), origin="telegram"))
    return f"✅ записано: {esc(vacancy.company)} — {esc(vacancy.title[:40])}"


def _is_owner(query: dict) -> bool:
    """Чи натиснув кнопку власник системи.

    Перевірка потрібна, бо повідомлення з inline-кнопками МОЖНА переслати в
    інший чат, і кнопки лишаться робочими: натискання прийде нам від того,
    хто натиснув, а не від того, кому ми писали. Без звірки будь-хто, до
    кого дійшло переслане повідомлення, створював би подачі в чужому журналі
    і ховав чужі вакансії.

    Умова СУВОРА: власником має бути саме відправник натискання, а чат —
    або наш, або не вказаний узагалі.

    Перша редакція перевіряла `allowed in {sender, chat}`, тобто «або-або», і
    цього не досить: збігу самого лише чату достатньо, щоб дію виконав
    хтось інший. Найпростіший випадок — бот, доданий у групу, де
    натискає будь-хто з учасників, а `message.chat.id` для бота виглядає
    знайомим. Авторизація, яку можна задовольнити ПОЛОВИНОЮ умови, не є
    авторизацією.
    """
    allowed = str(get_settings().telegram_chat_id or "").strip()
    if not allowed:
        # Не налаштовано — не дозволено нікому. Порожнє значення не може
        # означати «пускати всіх»: це рівно та помилка, через яку системи
        # відкриваються назовні при неповному налаштуванні.
        return False

    sender = str((query.get("from") or {}).get("id", "")).strip()
    if sender != allowed:
        return False

    chat = str(((query.get("message") or {}).get("chat") or {}).get("id", "")).strip()
    # Чат відсутній у callback з inline-режиму — там перевіряти нема чого,
    # і відправника вже звірено. Але якщо чат названий, він мусить бути наш.
    return not chat or chat == allowed


async def _mark_message(session: AsyncSession, query: dict, key: str,
                        answer: str) -> None:
    """Показати в САМОМУ повідомленні, що дію виконано.

    Редагуємо текст, а не клавіатуру. Три причини:

    * `answerCallbackQuery` спливає і зникає, а при опитуванні з інтервалом
      ще й застаріває — Telegram дає на відповідь близько п'ятнадцяти секунд;
    * позначка в тексті лишається в історії каналу: через тиждень видно, на
      що вже відреаговано;
    * текст із розміткою в нас уже збережений — у журналі сповіщень, — тож
      нічого відновлювати не треба. `query.message.text` для цього не
      годиться: він приходить без HTML, і редагування з'їло б жирний шрифт.
    """
    message = query.get("message") or {}
    if not message.get("message_id"):
        return

    row = (await session.execute(
        select(Notification).where(Notification.key == key)
    )).scalars().first()
    original = row.text if row else (message.get("text") or "")

    try:
        await call("editMessageText", {
            "chat_id": message["chat"]["id"],
            "message_id": message["message_id"],
            "text": f"<b>{answer}</b>\n\n{original}",
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
            # Кнопки прибираємо: дію вже виконано, і друге натискання лише
            # повідомило б «вже записано раніше».
            "reply_markup": {"inline_keyboard": []},
        })
    except Exception as exc:                      # noqa: BLE001
        log.warning("не вдалось позначити повідомлення: %s", _safe(exc))


async def poll(session: AsyncSession) -> int:
    """Забрати натискання й виконати їх. Повертає кількість опрацьованих."""
    state = await _offset(session)
    try:
        data = await call("getUpdates", {"offset": state.update_offset + 1,
                                         "timeout": 0, "limit": 50,
                                         "allowed_updates": ["callback_query"]})
    except NotConfigured:
        return 0
    except Exception as exc:                      # noqa: BLE001
        # Виняток від httpx несе повну адресу запиту, а в ній — токен бота.
        # Піднявши його вище, ми віддали б секрет у лог APScheduler разом із
        # трасуванням. Тому гасимо тут і пишемо вже знешкоджений текст.
        log.warning("опитування телеграму не вдалось: %s", _safe(exc))
        return 0

    handled = 0
    for update in data.get("result", []):
        state.update_offset = max(state.update_offset, update["update_id"])
        query = update.get("callback_query")
        if not query:
            continue

        if not _is_owner(query):
            # Чуже натискання не виконуємо і не відповідаємо на нього:
            # мовчання не підказує, що бот узагалі щось уміє.
            log.warning("натискання від стороннього — проігноровано")
            continue

        payload = query.get("data", "")
        action, _, raw_id = payload.partition(":")
        if action == "done":
            continue                              # натиснуто позначку, не дію
        if action not in {"applied", "skip"} or not raw_id.isdigit():
            continue

        answer = await _apply(session, action, int(raw_id))
        handled += 1

        # Підтвердження замінює кнопки В САМОМУ повідомленні, а не спливає
        # над ним. Так вирішено після першої ж перевірки 08.10.2026:
        # `answerCallbackQuery` вимагає відповіді протягом ~15 секунд, а
        # опитування йде з інтервалом — тож спливаюче підтвердження майже
        # завжди запізнюється, і дія виглядає як така, що не спрацювала.
        #
        # Позначка в повідомленні ще й корисніша: вона лишається в історії
        # каналу, тож видно, на що вже відреаговано, навіть через тиждень.
        await _mark_message(session, query, f"vacancy:{raw_id}", answer)

        # Спливаюче підтвердження лишається спробою: коли натискання
        # опрацьовується швидко, воно приємніше за редагування.
        try:
            await call("answerCallbackQuery",
                       {"callback_query_id": query["id"], "text": answer})
        except Exception:                         # noqa: BLE001
            # Прострочений ідентифікатор — звичайний стан при опитуванні,
            # а не поломка: позначку вже поставлено вище.
            pass
        log.info("дія з телеграму: %s → %s", payload, answer)

    await session.commit()
    return handled
