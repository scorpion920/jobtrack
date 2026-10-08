"""Керування збором вакансій."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.collect import collect
from app.db import get_session
from app.models import SourceConfig

router = APIRouter(prefix="/api/sources", tags=["sources"])


class CollectOut(BaseModel):
    source_key: str
    found: int
    created: int
    refreshed: int
    cross_channel: int
    error: str | None = None


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
