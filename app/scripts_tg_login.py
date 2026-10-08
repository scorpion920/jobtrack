"""Одноразовий вхід у Telegram для читання каналів.

Окремою командою, а не всередині збору: вхід інтерактивний — Telegram
надсилає код підтвердження, — і прогін за розкладом не має де його запитати.
Спроба зробити це у фоні дала б задачу, яка мовчки висить вічно.

Запуск:  docker compose exec api python -m app.scripts_tg_login

Створює `data/jobtrack.session`. Цей файл рівноцінний входу в акаунт:
він лежить у томі, який не потрапляє ані в git, ані в образ.
"""

from __future__ import annotations

import asyncio

from telethon import TelegramClient

from app.config import get_settings


async def main() -> None:
    cfg = get_settings()
    if not cfg.telegram_api_id or not cfg.telegram_api_hash:
        raise SystemExit(
            "TELEGRAM_API_ID / TELEGRAM_API_HASH не задані у .env.\n"
            "Після зміни .env потрібен `docker compose up -d api`, "
            "а не `restart`: змінні середовища задаються при створенні "
            "контейнера.")

    client = TelegramClient(cfg.telegram_session,
                            cfg.telegram_api_id, cfg.telegram_api_hash)
    await client.start()                       # запитає номер і код
    me = await client.get_me()
    print(f"Вхід виконано: {me.first_name} (@{me.username})")
    print(f"Сесію збережено: {cfg.telegram_session}")
    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
