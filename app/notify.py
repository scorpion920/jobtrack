"""Надсилання сповіщень у Telegram.

Бот тут односторонній: він повідомляє, але нічим не керує. Це свідомо —
команди в боті означали б другий інтерфейс до тих самих даних, який треба
тримати в згоді з вебом. Посилання на сторінку дешевше й не розходиться.

Невідправлене НЕ зникає: кожна спроба лишає рядок у журналі, і невдала —
з причиною. Інакше «не було про що повідомляти» і «повідомлення не дійшло»
виглядали б однаково, а це рівно та пара станів, через яку збирач статусів
мовчав три години непоміченим.
"""

from __future__ import annotations

import re

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.alerts import Alert
from app.config import get_settings
from app.models import Notification

API = "https://api.telegram.org/bot{token}/{method}"


def _safe(exc: Exception) -> str:
    """Текст помилки без токена.

    `httpx` кладе повну адресу запиту в текст винятку, а в ній стоїть токен
    бота: «Client error '400' for url 'https://api.telegram.org/bot<ТОКЕН>/…».
    Без маскування токен осів би у таблиці `notification` і на сторінці —
    тобто секрет витік би саме через механізм, що існує для діагностики.
    """
    text = f"{type(exc).__name__}: {exc}"
    token = get_settings().telegram_bot_token
    if token:
        text = text.replace(token, "<ТОКЕН ПРИХОВАНО>")
    # Другий рубіж на випадок, коли токен у тексті відрізняється від
    # поточного (перевипущений, інша інсталяція): ріжемо будь-що схоже.
    return re.sub(r"bot\d{6,}:[\w-]{20,}", "bot<ТОКЕН ПРИХОВАНО>", text)


class NotConfigured(RuntimeError):
    """Бот не налаштований. Це стан, а не помилка — але ГУЧНИЙ стан."""


async def call(method: str, payload: dict) -> dict:
    """Виклик Bot API. Єдине місце, що знає про токен."""
    cfg = get_settings()
    if not cfg.telegram_bot_token:
        raise NotConfigured("TELEGRAM_BOT_TOKEN не заданий у .env")

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            API.format(token=cfg.telegram_bot_token, method=method), json=payload)
        if response.status_code >= 400:
            # Telegram пояснює відмову в тілі відповіді, а `raise_for_status`
            # цього не показує — лишається голий «400 Bad Request», по якому
            # неможливо зрозуміти, що саме не так. Беремо опис.
            try:
                why = response.json().get("description", "")
            except Exception:                     # noqa: BLE001
                why = response.text[:200]
            raise RuntimeError(f"{method}: {response.status_code} {why}")
        return response.json()


def _buttons(key: str) -> dict | None:
    """Кнопки дій під карткою вакансії.

    Чому кнопки, попри те, що бот свідомо односторонній. Команди в боті
    означали б другий інтерфейс до тих самих даних — і це рішення лишається.
    Кнопка ж не є інтерфейсом: вона діє над КОНКРЕТНИМ повідомленням, яке
    бот щойно надіслав, і не вимагає нічого пам'ятати.

    Цінність саме в «не цікавить»: кожна відмова оператора ставала правилом
    скринера (no-code, академічна математика, DevOps, Oracle, гібрид —
    усі п'ять прийшли так за один вечір). Зараз це коштує окремої розмови;
    кнопка робить це дотиком.
    """
    if not key.startswith("vacancy:"):
        return None
    vacancy_id = key.split(":", 1)[1]
    return {"inline_keyboard": [[
        {"text": "✅ Подав", "callback_data": f"applied:{vacancy_id}"},
        {"text": "🚫 Не цікавить", "callback_data": f"skip:{vacancy_id}"},
    ]]}


async def send(text: str, key: str = "") -> None:
    cfg = get_settings()
    if not cfg.telegram_chat_id:
        raise NotConfigured("TELEGRAM_CHAT_ID не заданий у .env")

    payload = {"chat_id": cfg.telegram_chat_id, "text": text,
               "parse_mode": "HTML", "disable_web_page_preview": True}
    markup = _buttons(key)
    if markup:
        payload["reply_markup"] = markup
    await call("sendMessage", payload)


async def already_sent(session: AsyncSession) -> set[str]:
    """Ключі приводів, про які вже повідомляли.

    Беремо ВСІ, включно з невдалими: повторна спроба надіслати те саме за
    розкладом перетворила б недоступний Telegram на потік дублікатів, щойно
    він повернеться.
    """
    rows = await session.execute(select(Notification.key))
    return set(rows.scalars())


async def deliver(session: AsyncSession, alerts: list[Alert]) -> tuple[int, int]:
    """Надіслати і записати. Повертає (надіслано, не вдалося).

    Запис іде ДО відправки, бо збій посеред пачки не повинен давати
    повторів наступного разу: краще втратити одне повідомлення, ніж
    надсилати його щогодини.
    """
    sent = failed = 0
    for alert in alerts:
        row = Notification(key=alert.key, text=alert.text)
        session.add(row)
        await session.flush()
        try:
            await send(alert.text, alert.key)
            row.delivered, sent = True, sent + 1
        except Exception as exc:                      # noqa: BLE001
            row.error, failed = _safe(exc), failed + 1
    await session.commit()
    return sent, failed


async def deliver_digest(session: AsyncSession, text: str, keyboard: dict,
                         keys: list[str]) -> bool:
    """Надіслати ОДНЕ повідомлення, погасивши повтор для всіх вакансій у ньому.

    Ключі гасіння лишаються по вакансіях, а не по повідомленню: інакше та
    сама вакансія приїхала б у наступному зведенні знову. Записуються ДО
    відправки — збій посеред доставки не повинен давати повторів, бо
    щогодинне повторення того самого переліку гірше за одне втрачене
    повідомлення.
    """
    from app.models import Notification

    for key in keys:
        session.add(Notification(key=key, text=text[:4000]))
    await session.flush()

    try:
        cfg = get_settings()
        if not cfg.telegram_chat_id:
            raise NotConfigured("TELEGRAM_CHAT_ID не заданий у .env")
        await call("sendMessage", {
            "chat_id": cfg.telegram_chat_id, "text": text, "parse_mode": "HTML",
            "disable_web_page_preview": True, "reply_markup": keyboard,
        })
        for row in (await session.execute(
            select(Notification).where(Notification.key.in_(keys))
        )).scalars():
            row.delivered = True
        ok = True
    except Exception as exc:                      # noqa: BLE001
        for row in (await session.execute(
            select(Notification).where(Notification.key.in_(keys))
        )).scalars():
            row.error = _safe(exc)
        ok = False

    await session.commit()
    return ok
