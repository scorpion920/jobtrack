"""Декларативна база і доступ до сесії.

**Двигун створюється ліниво, і це не дрібниця.** У першій редакції
`create_async_engine()` стояв на рівні модуля — отже сам імпорт `app.models`
піднімав пул з'єднань. Наслідок виявився одразу: тести чистої логіки воронки
не запускались без БД і без повного набору залежностей, хоч не торкались ані
того, ані іншого.

Правило, яке з цього випливає: шар моделі не повинен нічого робити під час
імпорту. Усе, що потребує оточення, — за викликом функції.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


@lru_cache
def get_engine() -> AsyncEngine:
    from sqlalchemy.ext.asyncio import create_async_engine

    from app.config import get_settings

    return create_async_engine(get_settings().database_url, pool_pre_ping=True)


@lru_cache
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_engine(), expire_on_commit=False, class_=AsyncSession)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with get_sessionmaker()() as session:
        yield session
