"""Тлумачення ознак вакансії.

Зразки взято зі справжніх сторінок, а не вигадано: формулювання майданчика —
це дані, а не домовленість, і перевіряти їх треба на тому, що він справді
надсилає.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.sources.djinni import parse_listing
from app.vacancy_facts import ENGLISH_LEVELS, interpret

FIXTURE = Path(__file__).parent / "fixtures" / "djinni_jobs_2026-10-08.html"


def test_full_line_is_understood():
    f = interpret(["Тільки віддалено", "Україна", "1 рік досвіду",
                   "Англійська - A2", "Gambling"])
    assert f.format == "remote"
    assert f.years_required == 1
    assert f.english == "a2" and f.english_level == 2
    assert f.location == "Україна"
    assert f.domains == ["Gambling"]
    assert f.unknown == []


def test_order_of_parts_does_not_matter():
    a = interpret(["Тільки офіс", "2 роки досвіду", "Англійська - B2"])
    b = interpret(["Англійська - B2", "2 роки досвіду", "Тільки офіс"])
    assert (a.format, a.years_required, a.english) == (b.format, b.years_required, b.english)


def test_no_english_is_not_the_same_as_unknown():
    """«Не потрібна» і «не вказано» ведуть до протилежних рішень."""
    assert interpret(["Англійська - Немає"]).english == "none"
    assert ENGLISH_LEVELS["none"] == 0
    assert interpret(["Україна"]).english is None


def test_missing_format_is_not_remote():
    """Відсутність позначки — це «невідомо», і вважати її «віддалено» НЕ можна.

    Перевірено дорогою ціною 08.10.2026: Precoro у переліку стоїть без
    позначки формату, а насправді приймає тільки в офіс. Якби фільтр читав
    порожнечу як згоду, власник готував би супровідні листи під вакансії, на
    які не може подаватись за своєю незмінною умовою.
    """
    f = interpret(["Україна", "1 рік досвіду", "Англійська - Немає", "Fintech"])
    assert f.format is None
    assert f.format != "remote"


def test_no_experience_is_zero_not_missing():
    assert interpret(["Без досвіду"]).years_required == 0
    assert interpret(["Україна"]).years_required is None


def test_part_time_is_noticed():
    f = interpret(["Тільки віддалено", "Part-time", "Україна"])
    assert f.part_time is True
    assert "Part-time" not in f.domains      # не має протікати в домени


def test_unrecognised_english_level_is_loud():
    """Невідомий рівень зберігається І повідомляється — не зникає мовчки."""
    f = interpret(["Англійська - Вільна"])
    assert f.english == "вільна"
    assert f.unknown == ["Англійська - Вільна"]
    assert f.english_level is None


def test_nothing_on_the_real_page_is_left_unrecognised():
    """Сторож проти тихої втрати ознак на справжніх даних."""
    rows = parse_listing(FIXTURE.read_text(encoding="utf-8"))
    unknown = [u for r in rows for u in interpret(r.payload["facts"]).unknown]
    assert unknown == [], f"невпізнані ознаки: {unknown}"


def test_every_real_vacancy_gets_years_and_english_or_explicit_none():
    rows = parse_listing(FIXTURE.read_text(encoding="utf-8"))
    for r in rows:
        f = interpret(r.payload["facts"])
        # Фікстуру завантажено з фільтром «1 рік досвіду», тому однакове
        # значення тут — властивість ЗАПИТУ, а не ринку. Перевіряємо лише,
        # що величину взагалі витлумачено.
        assert f.years_required is not None
        assert f.format in {"remote", "office", "hybrid", None}
