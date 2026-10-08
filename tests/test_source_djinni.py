"""Розбір переліку вакансій Djinni — на збереженій сторінці, без мережі.

Фікстура `djinni_jobs_2026-10-08.html` — справжня сторінка, завантажена
08.10.2026. Саме тому тест має сенс: коли майданчик змінить розмітку, різниця
між фікстурою і живою сторінкою стане видимою як падіння ЦЬОГО тесту, а не як
порожній перелік вакансій у системі через тиждень.

Очікування навмисно конкретні (назви, числа, час), а не «список не порожній»:
розбір, що повертає 15 напівпорожніх записів, формально проходить перевірку на
кількість і тихо робить систему непридатною.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from app.sources.djinni import KEY, parse_listing

FIXTURE = Path(__file__).parent / "fixtures" / "djinni_jobs_2026-10-08.html"


@pytest.fixture(scope="module")
def rows():
    return parse_listing(FIXTURE.read_text(encoding="utf-8"))


def test_finds_every_vacancy_on_the_page(rows):
    assert len(rows) == 15


def test_first_vacancy_is_read_whole(rows):
    r = rows[0]
    assert r.source_key == KEY
    assert r.external_id == "848707"
    assert r.url == "https://djinni.co/jobs/848707-python-developer-automation/"
    assert r.title == "Python Developer (Automation)"
    assert r.company == "Trident Media"
    # Точний час із підказки, а не «9г»: відносна позначка стає хибною
    # одразу, щойно сторінку збережено й прочитано пізніше.
    assert r.posted_at == datetime(2026, 10, 8, 10, 54)


def test_facts_line_is_split_into_parts(rows):
    assert rows[0].payload["facts"] == [
        "Тільки віддалено", "Україна", "1 рік досвіду", "Англійська - A2", "Gambling",
    ]


def test_competition_is_measured(rows):
    """Кількість відгуків — головне, чого не видно оком при ручному перегляді."""
    by_id = {r.external_id: r for r in rows}
    assert by_id["848707"].payload["replies"] == 98
    assert by_id["848707"].payload["views"] == 454
    # 341 відгук проти 60 — різниця, яка прямо визначає пріоритет подачі.
    assert by_id["778695"].payload["replies"] == 341
    assert by_id["850367"].payload["replies"] == 60


def test_salary_tier_counts_dollar_signs(rows):
    by_id = {r.external_id: r for r in rows}
    assert by_id["778695"].payload["salary_tier"] == 4   # «$$$$» — найвищий
    assert by_id["848707"].payload["salary_tier"] == 1
    # Майданчик показує рівень не завжди; відсутність — це None, а не нуль,
    # інакше «не повідомлено» зливається з «найнижчий».
    assert by_id["846236"].payload["salary_tier"] is None


def test_description_is_full_not_truncated(rows):
    """Скринер мусить судити про вакансію за всім текстом, а не за анонсом."""
    r = rows[0]
    assert len(r.raw_text) > 1000
    assert "Selenium" in r.raw_text          # з тіла оголошення
    assert r.title in r.raw_text             # заголовок теж шукається скринером


def test_no_vacancy_is_half_empty(rows):
    """Запис без посилання чи назви не створюється взагалі.

    Напівпорожня вакансія гірша за відсутню: її не можна відкрити, а в
    переліку вона лишається назавжди."""
    for r in rows:
        assert r.url.startswith("https://djinni.co/jobs/")
        assert r.title and r.company != "—"
        assert r.posted_at is not None
        assert len(r.raw_text) > 100


def test_dedup_key_is_channel_plus_id(rows):
    assert rows[0].dedup_key == ("djinni", "848707")
    assert len({r.dedup_key for r in rows}) == len(rows)


def test_empty_page_yields_nothing():
    """Порожнє — це порожнє, а не падіння: сторінка може не мати вакансій."""
    assert parse_listing("<html><body><p>нічого</p></body></html>") == []


def test_next_page_is_taken_from_the_page_not_guessed():
    """Наступна сторінка береться лише з посилання на самій сторінці.

    Поломка, заради якої написано (08.10.2026): Djinni на `?page=2` для
    фільтра з однією сторінкою віддає не порожнечу і не помилку, а ІНШИЙ,
    нефільтрований перелік. У базу приїхали Media Buyer і Supply Chain
    Manager замість Python-вакансій — валідні дані, правильна розмітка, усі
    поля на місці, просто не ті.

    Захист «порожньо → зупинитись» такого не ловить за побудовою: він
    перевіряє наявність, а зламалась тотожність.
    """
    from app.sources.djinni import DjinniSource

    html = FIXTURE.read_text(encoding="utf-8")
    assert DjinniSource._has_next_page(html) is False

    # А там, де посилання є, воно впізнається.
    assert DjinniSource._has_next_page(
        '<a href="/jobs/?primary_keyword=Python&page=2">2</a>'
    ) is True


def test_page_url_keeps_the_filter():
    from app.sources.djinni import DjinniSource

    s = DjinniSource("djinni", {"listing": "/jobs/?primary_keyword=Python"})
    assert s._page_url(1) == "https://djinni.co/jobs/?primary_keyword=Python"
    assert s._page_url(2) == "https://djinni.co/jobs/?primary_keyword=Python&page=2"


def test_polite_interval_is_not_shortened():
    """Збір у межах правил майданчика тримається на темпі, а не на дозволі."""
    from app.sources.djinni import MIN_INTERVAL_SECONDS

    assert MIN_INTERVAL_SECONDS >= 10.0


def test_user_agent_carries_a_contact():
    """Адміністратор майданчика має мати до кого звернутись, а не блокувати наосліп."""
    from app.config import Settings

    agent = Settings(scraper_contact="someone@example.com").user_agent
    assert "jobtrack" in agent and "someone@example.com" in agent
