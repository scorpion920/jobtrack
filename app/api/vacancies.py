"""Керування збором вакансій."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.collect import collect
from app.db import get_session
from app.models import SourceConfig
from app.sources.djinni import validate_listing

router = APIRouter(prefix="/api/sources", tags=["sources"])


class CollectOut(BaseModel):
    source_key: str
    found: int
    created: int
    refreshed: int
    cross_channel: int
    error: str | None = None


class ValidateOut(BaseModel):
    source_key: str
    ok: bool
    note: str


@router.post("/{key}/validate", response_model=ValidateOut)
async def run_validate(key: str,
                       session: AsyncSession = Depends(get_session)) -> ValidateOut:
    """Перевірити, що фільтр каналу справді звужує видачу.

    Окремо від збору навмисно: це перевірка НАЛАШТУВАННЯ, і робити два
    додаткові запити на кожному прогоні заради неї не можна. Запускається
    при заведенні каналу й після зміни його параметрів.
    """
    config = (await session.execute(
        select(SourceConfig).where(SourceConfig.key == key)
    )).scalar_one_or_none()
    if not config:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"каналу {key!r} немає")
    if config.kind != "djinni":
        return ValidateOut(source_key=key, ok=True,
                           note=f"для каналів виду {config.kind!r} перевірка не потрібна")

    ok, note = await validate_listing((config.params or {}).get("listing") or "")
    if not ok:
        # Недієвий фільтр — це стан каналу, а не разова невдача: він
        # наповнюватиме базу чужими вакансіями при кожному прогоні.
        config.last_error = f"фільтр не працює: {note}"
        await session.commit()
    return ValidateOut(source_key=key, ok=ok, note=note)


@router.post("/{key}/collect", response_model=CollectOut)
async def run_collect(key: str,
                      session: AsyncSession = Depends(get_session)) -> CollectOut:
    """Зібрати канал зараз.

    Ручний запуск лишається назавжди, навіть коли з'явиться розклад: перевірка
    «чи працює канал» не повинна вимагати чекати наступного вікна.
    """
    config = (await session.execute(
        select(SourceConfig).where(SourceConfig.key == key)
    )).scalar_one_or_none()
    if not config:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"каналу {key!r} немає")
    if not config.active:
        raise HTTPException(status.HTTP_409_CONFLICT, f"канал {key!r} вимкнено")

    report = await collect(session, config)
    return CollectOut(**report.__dict__)
