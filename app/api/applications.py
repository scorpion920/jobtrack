"""REST над журналом подач."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db import get_session
from app.models import Application, ApplicationEvent
from app.schemas import ApplicationIn, ApplicationOut, EventIn, EventOut

router = APIRouter(prefix="/api/applications", tags=["applications"])


async def _load(session: AsyncSession, app_id: int) -> Application:
    res = await session.execute(
        select(Application).options(selectinload(Application.events))
        .where(Application.id == app_id)
    )
    app = res.scalar_one_or_none()
    if app is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"подачі {app_id} немає")
    return app


@router.get("", response_model=list[ApplicationOut])
async def list_applications(session: AsyncSession = Depends(get_session)):
    res = await session.execute(
        select(Application).options(selectinload(Application.events))
        .order_by(Application.applied_on.desc(), Application.id.desc())
    )
    return list(res.scalars())


@router.post("", response_model=ApplicationOut, status_code=status.HTTP_201_CREATED)
async def create_application(payload: ApplicationIn,
                             session: AsyncSession = Depends(get_session)):
    app = Application(**payload.model_dump())
    session.add(app)
    await session.flush()
    # Подача без жодної події виглядала б як «нічого не сталося». Факт
    # надсилання — теж подія, і вона мусить мати дату.
    session.add(ApplicationEvent(application_id=app.id, status="sent",
                                 occurred_on=payload.applied_on, origin="manual"))
    await session.commit()
    return await _load(session, app.id)


@router.get("/{app_id}", response_model=ApplicationOut)
async def get_application(app_id: int, session: AsyncSession = Depends(get_session)):
    return await _load(session, app_id)


@router.post("/{app_id}/events", response_model=EventOut,
             status_code=status.HTTP_201_CREATED)
async def add_event(app_id: int, payload: EventIn,
                    session: AsyncSession = Depends(get_session)):
    app = await _load(session, app_id)

    # Той самий статус тією самою датою — не нова інформація. Без цієї перевірки
    # повторна синхронізація з браузера (E1) дублювала б історію щоразу.
    for existing in app.events:
        if existing.status == payload.status and existing.occurred_on == payload.occurred_on:
            return existing

    event = ApplicationEvent(application_id=app_id, **payload.model_dump())
    session.add(event)
    await session.commit()
    await session.refresh(event)
    return event


@router.delete("/{app_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_application(app_id: int, session: AsyncSession = Depends(get_session)):
    app = await _load(session, app_id)
    await session.delete(app)
    await session.commit()
