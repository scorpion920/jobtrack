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

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.alerts import Alert
from app.config import get_settings
from app.models import Notification

API = "https://api.telegram.org/bot{token}/sendMessage"


class NotConfigured(RuntimeError):
    """Бот не налаштований. Це стан, а не помилка — але ГУЧНИЙ стан."""


async def send(text: str) -> None:
    cfg = get_settings()
    if not cfg.telegram_bot_token or not cfg.telegram_chat_id:
        raise NotConfigured(
            "TELEGRAM_BOT_TOKEN або TELEGRAM_CHAT_ID не задані у .env")

    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(
            API.format(token=cfg.telegram_bot_token),
            json={"chat_id": cfg.telegram_chat_id, "text": text,
                  "parse_mode": "HTML", "disable_web_page_preview": False},
        )
        response.raise_for_status()


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
            await send(alert.text)
            row.delivered, sent = True, sent + 1
        except Exception as exc:                      # noqa: BLE001
            row.error, failed = f"{type(exc).__name__}: {exc}", failed + 1
    await session.commit()
    return sent, failed
