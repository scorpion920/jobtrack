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

    # Сторінки, з яких браузер має право звертатися до цього API.
    # Саме з них виконується скрипт збору статусів, і без цього дозволу
    # браузер ріже запит передпольотною перевіркою (CORS), навіть якщо
    # токен правильний.
    #
    # Список, а не "*": зірочка дозволила б будь-якій відкритій сторінці
    # стукати в локальний сервіс. Токен це зупинив би, але покладатися на
    # один рубіж там, де дешево мати два, не варто.
    #
    # ⚠️ `dou.ua` і `jobs.dou.ua` — РІЗНІ джерела з погляду браузера.
    # Сторінка з відгуками лежить на першому, вакансії — на другому; дозвіл
    # лише для `jobs.` не допоміг, і помилка знову виглядала як «сервер
    # недоступний».
    cors_origins: str = (
        "https://djinni.co,https://jobs.dou.ua,https://dou.ua,https://www.linkedin.com"
    )

    # Планувальник. Вимикається для тестів і коли процесів кілька:
    # двоє планувальників ходили б до майданчика вдвічі частіше,
    # ніж домовлено.
    scheduler_enabled: bool = True

    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def user_agent(self) -> str:
        contact = self.scraper_contact or "no-contact-configured"
        return f"jobtrack/0.1 (+{contact})"


@lru_cache
def get_settings() -> Settings:
    return Settings()
