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

    # Номер запитуємо САМІ й перевіряємо формат.
    #
    # `client.start()` без аргументів питає «phone (or bot token)» і приймає
    # обидва: токен бота розпізнається за двокрапкою. 09.10.2026 так і
    # сталося — у сесію увійшов бот, а бот не може читати канали взагалі
    # («BotMethodInvalidError»). Помилка при цьому випливла аж на зборі,
    # за кілька кроків від причини.
    phone = input("Номер телефону у форматі +380XXXXXXXXX: ").strip()
    if ":" in phone or not phone.lstrip("+").isdigit():
        raise SystemExit(
            "Це не номер телефону. Потрібен САМЕ номер облікового запису: "
            "бот не бачить каналів, у яких не перебуває, і не може читати "
            "їх історію."
        )

    # Де шукати код — питання не риторичне: Telegram надсилає його В
    # ЗАСТОСУНОК, якщо на акаунті вже є активна сесія, і SMS приходить лише
    # коли інших сесій немає. Людина натомість чекає SMS і вважає, що вхід
    # зламався.
    print()
    print("Код прийде В ЗАСТОСУНОК Telegram — чат «Telegram» угорі списку,")
    print("а не SMS. Він летить на ВСІ активні сесії: перевірте і телефон,")
    print("і десктоп. Для щойно створеного api_id перший код інколи йде")
    print("кілька хвилин; якщо не дочекались — Ctrl+C і спробуйте знову.")
    print()

    await client.start(phone=phone)
    me = await client.get_me()
    if me.bot:
        await client.disconnect()
        raise SystemExit(
            "У сесію увійшов бот — читати канали він не зможе. "
            "Видаліть файл сесії і повторіть вхід номером телефону."
        )

    print(f"Вхід виконано: {me.first_name} (@{me.username})")
    print(f"Сесію збережено: {cfg.telegram_session}")
    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
