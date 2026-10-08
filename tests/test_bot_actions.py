"""Дії з кнопок під сповіщеннями.

Кнопка існує заради одного: зробити дотиком те, що досі коштувало окремої
розмови. За вечір 08.10.2026 п'ять відмов оператора стали правилами
скринера — no-code, академічна математика, DevOps, Oracle, гібрид. Кожна
з них проходила через діалог; кнопка прибирає цей крок.
"""

from __future__ import annotations

from app.notify import _buttons


def test_vacancy_card_gets_both_actions():
    markup = _buttons("vacancy:125")
    actions = [b["callback_data"] for b in markup["inline_keyboard"][0]]
    assert actions == ["applied:125", "skip:125"]


def test_digest_has_no_buttons():
    """Зведення не є вакансією — діяти над ним нема чим."""
    assert _buttons("digest:2026-10-08:6") is None
    assert _buttons("silence:1:1") is None
    assert _buttons("") is None


def test_callback_payload_is_parsed_strictly():
    """Розбір навмисно суворий: `callback_data` приходить ззовні.

    Telegram гарантує лише те, що рядок — наш власний, але підміна чи
    пошкодження не повинні призводити до дії над випадковою вакансією.
    """
    for payload in ("applied:125", "skip:7"):
        action, _, raw = payload.partition(":")
        assert action in {"applied", "skip"} and raw.isdigit()

    for bad in ("applied:abc", "delete:1", "applied:", ":1", "applied",
                "applied:1;drop", "skip:-1"):
        action, _, raw = bad.partition(":")
        assert not (action in {"applied", "skip"} and raw.isdigit()), bad


def test_only_the_pressed_row_is_marked():
    """У зведенні рядок на вакансію, і дія стосується однієї з них.

    Замінити всю клавіатуру одним підтвердженням означало б відібрати
    можливість відреагувати на решту — а саме заради цього зведення й існує.
    """
    from app.bot_actions import _mark_row

    keyboard = [
        [{"text": "1 ✅ подав", "callback_data": "applied:10"},
         {"text": "1 🚫 нецікаво", "callback_data": "skip:10"}],
        [{"text": "2 ✅ подав", "callback_data": "applied:20"},
         {"text": "2 🚫 нецікаво", "callback_data": "skip:20"}],
    ]
    result = _mark_row(keyboard, "skip:10", "🚫 приховано: Acme")["inline_keyboard"]

    assert len(result[0]) == 1 and result[0][0]["callback_data"] == "done"
    assert result[0][0]["text"].startswith("1 ")      # номер позиції зберігся
    assert result[1] == keyboard[1]                   # друга лишилась робочою


def test_stranger_cannot_act():
    """Повідомлення з кнопками МОЖНА переслати в інший чат, і кнопки
    лишаться робочими: натискання прийде від того, хто натиснув.

    Без звірки будь-хто, до кого дійшло переслане повідомлення, створював
    би подачі в чужому журналі і ховав чужі вакансії.
    """
    from app.bot_actions import _is_owner

    assert not _is_owner({"from": {"id": 999999999},
                          "message": {"chat": {"id": 888888}}})
    assert not _is_owner({})
    assert not _is_owner({"from": {}})


def test_digest_numbers_match_the_keyboard():
    """Номер у підписі кнопки мусить збігатися з номером у тексті —
    інакше при шести однакових рядках неможливо зрозуміти, яка до чого."""
    from datetime import date

    from app.alerts import VacancyBrief, digest_keyboard, digest_text

    items = [VacancyBrief(i, f"https://x/{i}", f"Company{i}", "Dev", "djinni",
                          "ok", "strong", i, date(2026, 10, 8))
             for i in (1, 2, 3)]
    text = digest_text(items, total=10, applied=2)
    keyboard = digest_keyboard(items)["inline_keyboard"]

    assert len(keyboard) == 3
    for n, row in enumerate(keyboard, start=1):
        assert row[0]["text"].startswith(f"{n} ")
        assert f"{n}. " in text


def test_authorization_needs_both_sender_and_chat(monkeypatch):
    """Авторизація, яку можна задовольнити ПОЛОВИНОЮ умови, не є авторизацією.

    Перша редакція перевіряла `allowed in {sender, chat}` — «або-або». Цього
    не досить: збігу самого лише чату достатньо, щоб дію виконав хтось
    інший. Найпростіший випадок — бот у групі, де натискає будь-хто.
    """
    from app import bot_actions
    from app.config import Settings

    monkeypatch.setattr(bot_actions, "get_settings",
                        lambda: Settings(telegram_chat_id="555"))

    # Свій відправник у своєму чаті.
    assert bot_actions._is_owner({"from": {"id": 555},
                                  "message": {"chat": {"id": 555}}})
    # Свій відправник без чату (inline-режим).
    assert bot_actions._is_owner({"from": {"id": 555}})

    # Чужий відправник у НАШОМУ чаті — саме випадок, який пропускала
    # перша редакція.
    assert not bot_actions._is_owner({"from": {"id": 999},
                                      "message": {"chat": {"id": 555}}})
    # Свій відправник у чужому чаті (бот доданий у групу).
    assert not bot_actions._is_owner({"from": {"id": 555},
                                      "message": {"chat": {"id": -100200}}})


def test_unconfigured_chat_allows_nobody(monkeypatch):
    """Порожнє значення не може означати «пускати всіх»."""
    from app import bot_actions
    from app.config import Settings

    monkeypatch.setattr(bot_actions, "get_settings",
                        lambda: Settings(telegram_chat_id=""))
    assert not bot_actions._is_owner({"from": {"id": 555},
                                      "message": {"chat": {"id": 555}}})
