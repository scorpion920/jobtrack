"""Налаштування з оточення. Жодних значень за замовчуванням для секретів."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://jobtrack:jobtrack@db:5432/jobtrack"

    # Ключ для синхронізації статусів із браузера. Порожній — синхронізація вимкнена.
    sync_token: str = ""

    # Контакт у User-Agent. Збирати публічні сторінки анонімно — неввічливо:
    # власник сайту має мати можливість зв'язатися, а не просто заблокувати.
    scraper_contact: str = ""

    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    @property
    def user_agent(self) -> str:
        contact = self.scraper_contact or "no-contact-configured"
        return f"jobtrack/0.1 (+{contact})"


@lru_cache
def get_settings() -> Settings:
    return Settings()
