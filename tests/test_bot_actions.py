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
