"""Сторож проти німого збирача статусів.

Поломка, заради якої написано: 08.10.2026 userscript установили, він віддався
браузеру (видно в логах сервера) — і даних не з'явилось. Причину знайти було
НІДЕ, бо скрипт мав три німі виходи:

    if (!rows.length) return;            ← вихід без жодного сліду
    console.debug("журнал недоступний")  ← рівень, прихований у консолі
    (порожній результат не надсилався)   ← у журналі нічого, як і при незапуску

Через це «не запускався» і «запустився й нічого не побачив» виглядали
однаково. Тест фіксує протилежне правило: кожен вихід лишає слід, а порожній
прогін доходить до сервера нарівні з результативним.
"""

from __future__ import annotations

import re
from pathlib import Path

STATIC = Path(__file__).resolve().parent.parent / "app" / "static"
USERSCRIPT = STATIC / "userscript.js"


def test_userscript_has_no_debug_level_diagnostics():
    """`console.debug` приховано у консолі за замовчуванням — отже це мовчання."""
    text = USERSCRIPT.read_text(encoding="utf-8")
    assert "console.debug(" not in text, (
        "console.debug не видно в консолі без зміни рівня логування — "
        "діагностика, якої ніхто не побачить, дорівнює її відсутності"
    )


def test_userscript_reports_even_an_empty_run():
    """Порожній прогін мусить дійти до журналу — саме він і несе діагностику."""
    text = USERSCRIPT.read_text(encoding="utf-8")
    assert not re.search(r"if\s*\(\s*!\s*rows\.length\s*\)\s*return", text), (
        "вихід без надсилання робить порожній прогін невідрізнюваним від "
        "того, що скрипт узагалі не запускався"
    )
    assert "origin: \"userscript\"" in text, (
        "прогін має називати себе, інакше в журналі не видно, що саме писало"
    )


def test_userscript_failure_path_is_visible():
    """Невдалий прогін говорить голосом, який видно без налаштувань консолі."""
    text = USERSCRIPT.read_text(encoding="utf-8")
    catch = text[text.index(".catch("):]
    assert "console.warn" in catch[:400], (
        "гілка помилки мусить писати console.warn — найчастіше саме вона "
        "й пояснює, чому журнал порожній"
    )


def test_userscript_can_update_itself():
    """Без @updateURL кожна правка вимагала б перевстановлення вручну."""
    text = USERSCRIPT.read_text(encoding="utf-8")
    assert "@updateURL" in text and "@downloadURL" in text, (
        "правки збирача мусять доїжджати до вже встановленого скрипта"
    )
