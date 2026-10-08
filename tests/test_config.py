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
