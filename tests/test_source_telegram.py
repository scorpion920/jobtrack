"""Канал Telegram: впізнавання вакансії у вільному тексті.

Головна відмінність від Djinni і DOU — структури немає. Майданчик віддає
поля, канал — текст, у якому автор пише як заманеться. Тому тут не розбір,
а обережне впізнавання: беремо те, що видно напевно, і не вигадуємо решти.
"""

from __future__ import annotations

from datetime import datetime

from app.sources.telegram import KEY, parse_message

STRUCTURED = """#Python #Middle

Компанія: Acme Tech
Вакансія: Python Developer (FastAPI)

Шукаємо розробника з досвідом FastAPI та PostgreSQL.
Деталі: https://example.com/jobs/1"""

FREE_FORM = """Шукаємо Python developer у команду фінтех-стартапу.
Досвід від року, віддалено. Резюме у приват."""


def test_structured_message_is_read_by_labels():
    v = parse_message(channel="@python_jobs_ua", message_id=4821,
                      text=STRUCTURED, posted_at=datetime(2026, 10, 9))
    assert v.source_key == KEY
    assert v.company == "Acme Tech"
    assert v.title == "Python Developer (FastAPI)"
    assert v.url == "https://example.com/jobs/1"


def test_external_id_carries_the_channel():
    """Номери повідомлень унікальні лише в межах каналу.

    Без префікса два канали затирали б вакансії одне одного — і це була б
    втрата, яку ніхто не помітив би: запис просто не з'явився б.
    """
    a = parse_message(channel="@one", message_id=100, text=FREE_FORM, posted_at=None)
    b = parse_message(channel="@two", message_id=100, text=FREE_FORM, posted_at=None)
    assert a.external_id != b.external_id
    assert a.external_id == "one:100"


def test_message_without_link_points_at_itself():
    """Вакансію треба мати куди відкрити, навіть якщо автор не дав адреси."""
    v = parse_message(channel="@x", message_id=7, text=FREE_FORM, posted_at=None)
    assert v.url == "https://t.me/x/7"


def test_non_vacancy_is_skipped():
    """Канали публікують не лише вакансії.

    Брати все підряд означало б засмітити перелік настільки, що ним
    перестануть користуватись.
    """
    for text in ("Доброго ранку, колеги!", "Підписуйтесь на наш канал",
                 "", "   ", "Ось корисна стаття про ООП"):
        assert parse_message(channel="@x", message_id=1, text=text,
                             posted_at=None) is None


def test_dangerous_link_is_not_taken():
    """Посилання з чужого тексту доходить до href на нашій сторінці."""
    text = "Шукаємо Python developer. Деталі: javascript:alert(1)"
    v = parse_message(channel="@x", message_id=9, text=text, posted_at=None)
    assert v.url == "https://t.me/x/9"


def test_channel_reports_no_conditions_and_says_so():
    """Канал не повідомляє ані років, ані англійської, ані конкуренції.

    Вдавати, що повідомляє, означало б давати впевненість, якої немає:
    такі вакансії мусять потрапляти в «потребує перегляду».
    """
    v = parse_message(channel="@x", message_id=1, text=FREE_FORM, posted_at=None)
    assert v.payload["facts"] == []
    assert v.payload["replies"] is None and v.payload["views"] is None


def test_title_falls_back_to_the_first_meaningful_line():
    v = parse_message(channel="@x", message_id=1,
                      text="#hiring\n\nШукаємо Python розробника\nвіддалено",
                      posted_at=None)
    assert v.title == "Шукаємо Python розробника"


def test_hashtag_line_is_not_a_title():
    """Канали майже завжди починають із тегів — «#Python #Middle #remote».

    Перша редакція брала «hiring» за посаду: після очищення символів рядок
    тегів виглядає як звичайний текст.
    """
    from app.sources.telegram import _first_line

    assert _first_line("#hiring\n\nШукаємо Python розробника") == \
        "Шукаємо Python розробника"
    assert _first_line("#Python #Middle #remote\nPython Developer") == \
        "Python Developer"
    assert _first_line("@channel_name\nВакансія тижня") == "Вакансія тижня"
