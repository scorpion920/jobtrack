"""Канал DOU — на збереженому фіді, без мережі.

Канал працює через офіційний RSS, а не через браузер: `jobs.dou.ua` віддає
повноцінний фід з описами, і це призначений для машин шлях. Планований
контейнер із Playwright скасовано — разом із найкрихкішою частиною системи.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from app.sources.dou import KEY, parse_dou_feed, parse_dou_title
from app.sources.rss import parse_feed, strip_html
from app.vacancy_facts import interpret

FIXTURE = Path(__file__).parent / "fixtures" / "dou_python_2026-10-08.rss"


@pytest.fixture(scope="module")
def rows():
    return parse_dou_feed(FIXTURE.read_text(encoding="utf-8"))


def test_whole_feed_is_read(rows):
    assert len(rows) == 25


def test_first_item_is_read_whole(rows):
    r = rows[0]
    assert r.source_key == KEY
    assert r.external_id == "358037"
    # Мітка джерела відкидається: вона не частина адреси вакансії.
    assert r.url == "https://jobs.dou.ua/companies/ciklum/vacancies/358037/"
    assert "utm_source" not in r.url
    assert r.title == "Expert Full Stack Engineer (3042)"
    assert r.company == "Ciklum"
    assert r.posted_at == datetime.fromisoformat("2026-10-08T17:14:35+03:00")
    assert len(r.raw_text) > 1000


def test_remote_marker_is_read_from_the_title(rows):
    by_id = {r.external_id: r for r in rows}
    assert interpret(by_id["358037"].payload["facts"]).format == "remote"
    # Вакансія без мітки — «не вказано», а не «офіс».
    assert interpret(by_id["375915"].payload["facts"]).format is None


def test_company_with_a_comma_does_not_break_the_split():
    """«Svitla Systems, Inc.» — кома в назві компанії.

    Розбір віддає перший фрагмент як компанію, а решту — у довідкову локацію.
    Відновити «Inc.» з адреси неможливо (slug його не містить), і вигадувати
    тут нічого не можна: неправильно зібрана назва отруїла б дедуплікацію за
    (компанія, посада) назавжди.
    """
    position, company, fmt, locations = parse_dou_title(
        "Senior Computer Vision Engineer в Svitla Systems, Inc., Київ, за кордоном"
    )
    assert position == "Senior Computer Vision Engineer"
    assert company == "Svitla Systems"
    assert "Inc." in locations
    assert fmt is None


def test_sentence_instead_of_location_does_not_become_a_fact(rows):
    """PLANEKS пише у полі локації ціле речення.

    Воно мусить лишитись довідкою. Якби такий текст потрапив у ознаки,
    тлумач, не впізнавши його, записав би речення у предметну область.
    """
    planeks = next(r for r in rows if r.company == "PLANEKS")
    assert "fully remote team" in planeks.payload["location"]
    facts = interpret(planeks.payload["facts"])
    assert facts.domains == [] and facts.unknown == []


def test_nothing_leaks_into_domains_on_the_real_feed(rows):
    for r in rows:
        f = interpret(r.payload["facts"])
        assert f.unknown == [], f"невпізнане у {r.company}: {f.unknown}"
        assert f.domains == [], f"протекло в домени у {r.company}: {f.domains}"


def test_channel_silence_about_competition_is_explicit(rows):
    """DOU не повідомляє відгуків — і це видно як None, а не як нуль.

    Нуль означав би «ніхто не відгукнувся» і зробив би кожну вакансію DOU
    найпривабливішою в переліку.
    """
    assert all(r.payload["replies"] is None for r in rows)
    assert all(r.payload["views"] is None for r in rows)


def test_title_without_separator_keeps_the_whole_position():
    position, company, fmt, _ = parse_dou_title("Python Developer")
    assert position == "Python Developer" and company == ""


def test_double_escaped_entities_are_unwrapped():
    """В описі RSS трапляється два рівні екранування."""
    assert strip_html("&lt;p&gt;LLM &amp;amp; RAG&lt;/p&gt;") == "LLM & RAG"


def test_feed_item_without_link_is_skipped():
    xml = "<rss><channel><item><title>Без посилання</title></item></channel></rss>"
    assert parse_feed(xml) == []


def test_dedup_keys_are_unique(rows):
    assert len({r.dedup_key for r in rows}) == len(rows)
