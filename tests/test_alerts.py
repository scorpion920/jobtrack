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


def test_weak_and_blocked_are_never_announced():
    """Поріг лишається вузьким: якби в канал ішло все підряд, його
    перестали б читати, а з ним і те, що справді варте уваги.

    Виняток один і він вузький — сильний збіг при невідомих умовах
    (Telegram-канали); його перевіряє окремий тест нижче.
    """
    assert vacancy_alerts([_v(state="blocked")]) == []
    assert vacancy_alerts([_v(fit="weak")]) == []
    assert vacancy_alerts([_v(state="unchecked", fit="possible")]) == []


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
    # Власна розмітка лишається робочою (рядок тепер починається з позначки
    # відповідності, тому перевіряємо наявність, а не початок).
    assert "<b>R&amp;D" in text


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


def test_notification_carries_enough_to_decide():
    """Повідомлення, після якого однаково треба відкривати сторінку, нічого
    не економить. Перевіряємо, що в ньому є все для рішення."""
    from app.alerts import describe

    v = _v(company="Office.kh.ua", title="Python Developer (Django)", replies=3,
           format="remote", years_required=1, english="b2", location="Україна",
           matched=("Python", "FastAPI", "PostgreSQL"),
           gaps=("Django: працював на FastAPI",))
    text = describe(v)

    assert "🟢" in text                      # сила збігу — з першого погляду
    assert "віддалено" in text               # чи візьмуть
    assert "1 р. досвіду" in text
    assert "англ. B2" in text
    assert "Україна" in text
    assert "3 відгуків" in text              # наскільки людно
    assert "FastAPI" in text                 # чим збігається
    assert v.url in text
    # Картка скорочена до чотирьох рядків: кнопки Telegram ставляться лише
    # ПІД повідомленням, тож «кнопки навпроти кожної вакансії» означають
    # окремі повідомлення, а їх читають тільки доти, доки вони короткі.
    assert len(text.splitlines()) == 4


def test_possible_and_strong_are_visually_distinct():
    from app.alerts import describe

    assert describe(_v(fit="strong")).startswith("🟢")
    assert describe(_v(fit="possible")).startswith("🟡")


def test_long_match_list_is_shortened_with_a_counter():
    """Чотири збіги на екрані, решта числом: довгий перелік перестають читати."""
    from app.alerts import describe

    text = describe(_v(matched=tuple(f"skill{i}" for i in range(9))))
    assert "+5" in text
    assert "skill4" not in text


def test_english_not_needed_is_said_in_words():
    """«англ. NONE» читається як помилка, а не як «не потрібна»."""
    from app.alerts import describe

    assert "англ. не потрібна" in describe(_v(english="none"))


def test_missing_fields_do_not_break_the_message():
    """DOU не повідомляє ані років, ані англійської — рядок просто коротший."""
    from app.alerts import describe

    text = describe(_v(format=None, years_required=None, english=None,
                       location=None, replies=None, matched=(), gaps=()))
    assert "відгуки не видно" in text
    assert "Збіг:" not in text


def test_every_external_field_is_escaped():
    """Жодне поле, що прийшло ззовні, не є винятком.

    Перевірено 08.10.2026: тлумач ознак пропускає розмітку наскрізь —
    «Англійська - <b>X</b>» дає english='<b>x</b>'. Перша редакція
    `describe()` екранувала назву компанії й посаду, але не формат,
    англійську та адресу.
    """
    from app.alerts import describe

    text = describe(_v(company="<i>C</i>", title="<i>T</i>",
                       format="<i>F</i>", english="<i>e</i>",
                       location="<i>L</i>", source_key="<i>S</i>",
                       url="https://x/?a=<i>u</i>",
                       matched=("<i>M</i>",), gaps=("<i>G</i>",)))
    # Жодного чужого тега не лишилось — тільки наші <b>.
    assert "<i>" not in text
    # Шість полів у картці: компанія, посада, формат, англійська, локація,
    # джерело, плюс збіг і адреса — прогалини в компактний формат не входять.
    assert text.count("&lt;i&gt;") == 8 - 1


def test_strong_match_without_known_conditions_is_still_told():
    """Telegram-канал не повідомляє ані років, ані англійської.

    Кожна його вакансія навіки лишається «потребує перегляду». Вимагати від
    неї `ok` означало б ніколи не повідомити про жодну — тобто завести
    вісім каналів і не дізнатися з них нічого.
    """
    from app.alerts import worth_telling

    assert worth_telling(_v(state="unchecked", fit="strong"))
    # Поріг вищий саме тому, що перевірити умови нема чим: платою за
    # сповіщення стає ручний перегляд, і він має окупатися.
    assert not worth_telling(_v(state="unchecked", fit="possible"))
    assert not worth_telling(_v(state="unchecked", fit="weak"))


def test_blocked_is_never_told_however_strong():
    from app.alerts import worth_telling

    assert not worth_telling(_v(state="blocked", fit="strong"))


def test_unknown_conditions_are_marked_differently():
    """Позначка має читатись інакше, ніж у перевіреної вакансії: вона
    вимагає від оператора дії — відкрити й подивитись самому."""
    from app.alerts import describe

    text = describe(_v(state="unchecked", fit="strong"))
    assert text.startswith("⚪")
    assert "умови не вказані" in text
    # «Невідомо» без пояснення читається як недогляд системи.
    assert "перевірити на сторінці" in text
