"""`.env.example` мусить піднімати систему без правок.

Знайдено перевіркою на чистому клоні 09.10.2026. Приклад конфігурації
містить `TELEGRAM_API_ID=` без значення — так і має бути, бо він показує
СКЛАД, а не секрети. Але поле оголошене як `int`, і pydantic падав при
старті:

    ValidationError: Input should be a valid integer,
    unable to parse string as an integer [input_value='']

Кожен, хто пішов би рекомендованим шляхом «скопіюй приклад у .env»,
отримав би систему, яка не піднімається. Міграції теж не виконувались:
падіння відбувалось усередині `alembic/env.py`, тобто ДО створення таблиць.

Тест перевіряє не одне поле, а правило: будь-яке значення з прикладу має
прийматись. Інакше наступне числове поле повторить ту саму історію —
а помітиться вона знову лише на чужій машині.
"""

from __future__ import annotations

import re
from pathlib import Path

from app.config import Settings

EXAMPLE = Path(__file__).resolve().parent.parent / ".env.example"


def _parse_example() -> dict[str, str]:
    values: dict[str, str] = {}
    for line in EXAMPLE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip().lower()] = value.strip()
    return values


def test_settings_accept_every_value_from_the_example():
    """Головна перевірка: приклад не містить значення, яке зламає старт."""
    example = _parse_example()
    known = {name for name in Settings.model_fields}
    payload = {k: v for k, v in example.items() if k in known}

    settings = Settings(_env_file=None, **payload)
    assert settings is not None


def test_example_covers_every_required_field():
    """Поле без значення за замовчуванням мусить бути в прикладі.

    Інакше людина дізнається про нього з падіння, а не з документації.
    """
    example = _parse_example()
    missing = [
        name for name, field in Settings.model_fields.items()
        if field.is_required() and name not in example
    ]
    assert not missing, f"немає у .env.example: {missing}"


def test_empty_numeric_value_means_unset():
    """Порожнє у `.env` означає «не налаштовано», а не помилку."""
    assert Settings(_env_file=None, telegram_api_id="").telegram_api_id == 0
    assert Settings(_env_file=None, telegram_api_id="12345").telegram_api_id == 12345


def test_example_has_no_real_secrets():
    """Приклад показує склад, а не значення.

    Справжній токен у прикладі — найтихіший спосіб опублікувати секрет:
    файл виглядає службовим, і його не перечитують.
    """
    text = EXAMPLE.read_text(encoding="utf-8")
    # Токен бота Telegram: цифри, двокрапка, довгий рядок.
    assert not re.search(r"=\s*\d{6,}:[\w-]{30,}", text)
    # Хеш api_hash — рівно 32 шістнадцяткові символи.
    assert not re.search(r"TELEGRAM_API_HASH=\s*[0-9a-f]{32}", text, re.I)
