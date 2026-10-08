"""Правила сповіщень і безпека їх тексту."""

from __future__ import annotations

from datetime import date

import httpx

from app.alerts import (Alert, ApplicationBrief, VacancyBrief, esc,
                        silence_alerts, unsent, vacancy_alerts)
from app.notify import _safe


def _v(**kw):
    base = dict(id=1, url="https://x/1", company="Acme", title="Python Developer",
                source_key="djinni", state="ok", fit="strong", replies=5,
                posted_on=date(2026, 10, 8))
    base.update(kw)
    return VacancyBrief(**base)


def test_suitable_vacancy_produces_an_alert():
    assert len(vacancy_alerts([_v()])) == 1


def test_unchecked_vacancy_is_not_announced():
    """DOU не повідомляє ані років, ані англійської.

    Якби «потребує перегляду» йшло у сповіщення, канал заповнився б
    повідомленнями, які нічого не вирішують, і їх перестали б читати.
    """
    assert vacancy_alerts([_v(state="unchecked")]) == []
    assert vacancy_alerts([_v(state="blocked")]) == []
    assert vacancy_alerts([_v(fit="weak")]) == []


def test_missing_reply_count_is_said_plainly():
    """«Відгуки не видно» і «нуль відгуків» — різні речі."""
    assert "відгуки не видно" in vacancy_alerts([_v(replies=None)])[0].text
    assert "0 відгуків" in vacancy_alerts([_v(replies=0)])[0].text


def test_markup_from_the_site_is_escaped():
    """Вакансія «Senior AI/ML Engineer (Python, LLM & RAG)» існує насправді.

    Без екранування Telegram відповів би 400 Bad Request, сповіщення не
    дійшло б, а причина виглядала б як збій мережі.
    """
    text = vacancy_alerts([_v(company="R&D <b>X</b>", title="LLM & RAG")])[0].text
    assert "R&amp;D" in text and "&lt;b&gt;" in text
    assert "LLM &amp; RAG" in text
    # Власна розмітка лишається робочою.
    assert text.startswith("<b>")


def test_escape_keeps_plain_text_intact():
    assert esc("Python Developer") == "Python Developer"
    assert esc(None) == ""


def test_silence_only_for_channels_that_report():
    """На DOU мовчання нічого не означає — нагадувати про нього було б шумом."""
    reporting = ApplicationBrief(1, "A", "P", "djinni", 12, "sent")
    silent_channel = ApplicationBrief(2, "B", "Q", "dou", None, "sent")
    keys = [a.key for a in silence_alerts([reporting, silent_channel])]
    assert keys == ["silence:1:1"]


def test_finished_applications_are_not_nagged():
    for status in ("rejected", "offer", "withdrawn", "ghosted"):
        app = ApplicationBrief(1, "A", "P", "djinni", 40, status)
        assert silence_alerts([app]) == []


def test_silence_key_changes_only_once_per_period():
    """Ключ описує ПРИВІД, не момент: інакше нагадування йшло б щодня."""
    same = {silence_alerts([ApplicationBrief(1, "A", "P", "djinni", d, "sent")])[0].key
            for d in (10, 13, 19)}
    assert len(same) == 1
    later = silence_alerts([ApplicationBrief(1, "A", "P", "djinni", 21, "sent")])[0].key
    assert later not in same


def test_already_sent_alerts_are_dropped():
    alerts = [Alert("a", "1"), Alert("b", "2")]
    assert [a.key for a in unsent(alerts, {"a"})] == ["b"]


def test_bot_token_never_reaches_the_error_log():
    """httpx кладе повну адресу запиту в текст винятку, а в ній — токен."""
    url = "https://api.telegram.org/bot123456:SECRET-TOKEN-ABCDEFGHIJKLM/sendMessage"
    request = httpx.Request("POST", url)
    try:
        httpx.Response(400, request=request).raise_for_status()
    except httpx.HTTPStatusError as exc:
        text = _safe(exc)
    assert "SECRET-TOKEN-ABCDEFGHIJKLM" not in text
    assert "ТОКЕН ПРИХОВАНО" in text
    # Діагностична цінність зберігається.
    assert "400" in text


def test_repost_does_not_produce_a_second_alert():
    """Office.kh.ua «Python Developer (Django)» опублікована двічі.

    Знайдено перед першою реальною відправкою 08.10.2026: у сповіщення йшли
    обидві публікації. У переліку старішу видно — на неї могло бути подано, —
    але повідомляти про неї означало б слати дублікат.

    Перевіряємо сам інваріант: вакансії, позначені перевипуском, до правил
    сповіщень не доходять.
    """
    from datetime import datetime

    from app.dedup import Publication, find_reposts

    old = Publication("https://x/old", "djinni", "office kh ua",
                      "python developer django", datetime(2026, 9, 27))
    new = Publication("https://x/new", "djinni", "office kh ua",
                      "python developer django", datetime(2026, 10, 8))
    reposts = find_reposts([old, new])

    briefs = [_v(id=1, url="https://x/old"), _v(id=2, url="https://x/new")]
    kept = [b for b in briefs if b.url not in reposts]
    alerts = vacancy_alerts(kept)
    assert len(alerts) == 1
    assert alerts[0].key == "vacancy:2"
