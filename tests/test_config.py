"""Тести налаштувань.

Список дозволених джерел перевіряється окремо, бо саме він одного разу
зупинив робочий сценарій: скрипт збору статусів виконується НА сторінці
майданчика, і без дозволу браузер ріже запит передпольотною перевіркою —
не дійшовши навіть до перевірки токена. Помилка виглядала як «сервер
недоступний», хоча сервер відповідав.
"""

from __future__ import annotations

from app.config import Settings


def test_origins_are_split_and_trimmed():
    s = Settings(cors_origins=" https://a.io , https://b.io ")
    assert s.cors_origin_list == ["https://a.io", "https://b.io"]


def test_empty_origins_give_empty_list_not_wildcard():
    """Порожнє значення має означати «нікому», а не «всім»."""
    assert Settings(cors_origins="").cors_origin_list == []


def test_trailing_separator_does_not_create_empty_origin():
    assert Settings(cors_origins="https://a.io,").cors_origin_list == ["https://a.io"]


def test_user_agent_names_a_contact():
    """Збирати публічні сторінки анонімно — неввічливо: власник сайту має
    мати можливість зв'язатися, а не лише заблокувати."""
    assert "me@example.com" in Settings(scraper_contact="me@example.com").user_agent


def test_user_agent_is_explicit_when_contact_missing():
    assert "no-contact-configured" in Settings(scraper_contact="").user_agent


class TestUserscriptIsInstallable:
    """Userscript мусить лишатися встановлюваним і самодостатнім.

    Розширення на кшталт Tampermonkey впізнають скрипт за блоком ==UserScript==
    і директивою @match. Загубити будь-що з цього означає, що файл просто
    відкриється як текст, і користувач не зрозуміє чому.
    """

    @staticmethod
    def _src() -> str:
        from pathlib import Path
        return (Path(__file__).resolve().parent.parent / "app" / "static"
                / "userscript.js").read_text(encoding="utf-8")

    def test_has_userscript_header(self):
        src = self._src()
        assert src.lstrip().startswith("// ==UserScript=="), "блок метаданих має бути ПЕРШИМ"
        assert "// ==/UserScript==" in src
        assert "@match        https://djinni.co/*" in src

    def test_placeholders_are_present_for_server_substitution(self):
        """Сервер підставляє адресу й токен. Якщо заповнювачі перейменують,
        підстановка тихо не спрацює, і скрипт звертатиметься в нікуди."""
        src = self._src()
        assert "__API__" in src and "__TOKEN__" in src

    def test_auto_reply_guard_present(self):
        """Автовідповідь не має зараховуватись як перегляд і тут теж —
        userscript має власну копію логіки й розходиться з нею найлегше."""
        src = self._src()
        assert "auto_reply" in src
        assert "автоматична відповідь" in src

    def test_polite_interval(self):
        """Темп опитування має лишатися ввічливим: не частіше разу на 10 хв."""
        import re
        m = re.search(r"EVERY_MIN\s*=\s*(\d+)", self._src())
        assert m and int(m.group(1)) >= 10, "надто частий опит зовнішнього сайту"

    def test_does_not_store_credentials(self):
        """Сторож проти повернення до ідеї «робот із логіном»."""
        src = self._src().lower()
        for forbidden in ("password", "пароль", "document.cookie", "login("):
            assert forbidden not in src, f"у скрипті з'явилось {forbidden!r}"
