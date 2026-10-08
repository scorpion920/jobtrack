"""Сторож проти повторного створення типу enum у міграціях.

Знайдено на першому ж піднятті стеку: `sa.Enum(...)` у `create_table` створює
тип САМ, і разом із явним `.create(checkfirst=True)` це дає
`DuplicateObjectError`. Підступність у тому, що помилка видима лише на ЧИСТІЙ
базі — на вже накоченій усе проходить, тож дефект легко доїжджає до того, хто
клонує репозиторій і піднімає його вперше.
"""

from __future__ import annotations

import re
from pathlib import Path

VERSIONS = Path(__file__).resolve().parent.parent / "alembic" / "versions"


def test_every_enum_in_migrations_disables_auto_create():
    offenders: list[str] = []
    for path in VERSIONS.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        for match in re.finditer(r"(sa\.Enum|postgresql\.ENUM)\(", text):
            tail = text[match.start(): match.start() + 600]
            # Межа оголошення — закривальна дужка верхнього рівня; грубо, але
            # достатньо: нас цікавить лише наявність прапорця поруч.
            if "create_type=False" not in tail.split("\n\n")[0]:
                line = text[: match.start()].count("\n") + 1
                offenders.append(f"{path.name}:{line}")
    assert not offenders, (
        "enum без create_type=False — накат на чистій базі впаде "
        f"DuplicateObjectError: {offenders}"
    )
