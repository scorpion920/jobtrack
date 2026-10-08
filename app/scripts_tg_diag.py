"""Діагностика входу: куди Telegram НАСПРАВДІ надсилає код.

Коли код «не приходить», здогадів багато, а відповідь одна й Telegram її
повідомляє сам: у відповіді на запит коду стоїть тип доставки. Він розрізняє
застосунок, SMS, дзвінок і очікування — і саме це знімає питання, де шукати.

Запуск:  docker compose exec api python -m app.scripts_tg_diag
"""

from __future__ import annotations

import asyncio

from telethon import TelegramClient
from telethon.errors import (ApiIdInvalidError, FloodWaitError,
                             PhoneNumberBannedError, PhoneNumberInvalidError)

from app.config import get_settings

_WHERE = {
    "SentCodeTypeApp": "У ЗАСТОСУНОК Telegram — чат «Telegram» угорі списку",
    "SentCodeTypeSms": "SMS на номер",
    "SentCodeTypeCall": "Дзвінок — код продиктують",
    "SentCodeTypeFlashCall": "Скидання дзвінка — код у номері, що дзвонить",
    "SentCodeTypeMissedCall": "Пропущений дзвінок — код у кінці номера",
    "SentCodeTypeEmailCode": "На пошту, прив'язану до акаунта",
    "SentCodeTypeSetUpEmailRequired": "Потрібно спершу прив'язати пошту в акаунті",
}


async def main() -> None:
    cfg = get_settings()
    phone = input("Номер телефону у форматі +380XXXXXXXXX: ").strip()

    client = TelegramClient(cfg.telegram_session,
                            cfg.telegram_api_id, cfg.telegram_api_hash)
    await client.connect()
    try:
        if await client.is_user_authorized():
            me = await client.get_me()
            print(f"Сесія вже активна: {me.first_name} (бот: {me.bot})")
            return

        sent = await client.send_code_request(phone)
        kind = type(sent.type).__name__
        print()
        print(f"Telegram прийняв запит. Тип доставки: {kind}")
        print(f"→ {_WHERE.get(kind, 'невідомий тип — див. документацію')}")
        if getattr(sent, "next_type", None):
            print(f"Якщо не дійде, наступна спроба піде як: "
                  f"{type(sent.next_type).__name__}")
        print()
        print("Цей скрипт код НЕ приймає — він лише показує, куди дивитись.")
        print("Знайшовши код, виконайте: python -m app.scripts_tg_login")
    except PhoneNumberInvalidError:
        print("Telegram не впізнав номер. Перевірте код країни і формат.")
    except PhoneNumberBannedError:
        print("Номер заблоковано в Telegram.")
    except ApiIdInvalidError:
        print("API_ID / API_HASH невірні — перевірте значення з my.telegram.org.")
    except FloodWaitError as exc:
        print(f"Забагато спроб. Telegram просить зачекати {exc.seconds} с "
              f"({exc.seconds // 60} хв).")
    finally:
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
