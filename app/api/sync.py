"""Приймання статусів, прочитаних у власній сесії браузера користувача.

Чому саме так, а не роботом із збереженим входом: сторінка відгуків лежить за
логіном, і автоматизувати вхід означало б тримати чужі облікові дані й ризикувати
акаунтом, який є єдиним каналом пошуку. Тут натомість сторінку читає САМ
користувач у своєму браузері, а сюди приходить уже витяг.

`dry_run` — не зручність, а вимога: DOM сторінки може змінитись будь-коли, і
тихо записати сміття гірше, ніж не записати нічого.
"""

from __future__ import annotations

import hmac
from datetime import date

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.db import get_session
from app.models import Application, ApplicationEvent, Channel, Status
from app.sync import Candidate, SyncItem, plan_sync

router = APIRouter(prefix="/api/sync", tags=["sync"])


class SyncItemIn(BaseModel):
    company: str = Field(min_length=1, max_length=200)
    position: str = Field(min_length=1, max_length=300)
    url: str | None = None
    applied_on: date | None = None
    status: Status | None = None
    status_on: date | None = None
    note: str | None = None
    cv_version: str | None = None


class SyncIn(BaseModel):
    source: Channel
    items: list[SyncItemIn]
    # За замовчуванням НЕ пишемо. Записати мовчки те, що невідомо звідки
    # взялося, — найгірший із можливих варіантів для журналу.
    dry_run: bool = True


class SyncReport(BaseModel):
    dry_run: bool
    received: int
    created: int = 0
    matched: int = 0
    events_added: int = 0
    ambiguous: list[str] = []
    details: list[str] = []


def _check_token(token: str | None) -> None:
    secret = get_settings().sync_token
    if not secret:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "SYNC_TOKEN не налаштовано — синхронізація вимкнена")
    if not token or not hmac.compare_digest(token, secret):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "невірний токен синхронізації")


@router.post("", response_model=SyncReport)
async def sync(payload: SyncIn,
               x_sync_token: str | None = Header(default=None),
               session: AsyncSession = Depends(get_session)) -> SyncReport:
    _check_token(x_sync_token)

    res = await session.execute(
        select(Application).options(selectinload(Application.events))
    )
    existing = list(res.scalars())

    # Усе, що потрібно для рішення, перекладається у прості структури ТУТ,
    # поки сесія ще жива і зв'язки завантажені. Далі ORM не торкаємось:
    # саме звернення до `.events` на щойно створеному об'єкті давало
    # MissingGreenlet.
    candidates = [Candidate(a.id, a.company, a.position, a.url, a.cv_version)
                  for a in existing]
    known: dict[int, set[tuple[str, date]]] = {
        a.id: {(e.status.value, e.occurred_on) for e in a.events} for a in existing
    }

    items = [SyncItem(company=i.company, position=i.position, url=i.url,
                      applied_on=i.applied_on,
                      status=i.status.value if i.status else None,
                      status_on=i.status_on, note=i.note,
                      cv_version=i.cv_version)
             for i in payload.items]

    today = date.today()
    plan = plan_sync(items, candidates, known, today)

    report = SyncReport(
        dry_run=payload.dry_run, received=len(items),
        created=len(plan.create), matched=plan.matched,
        # Подія «надіслано» для нової подачі — не нова інформація для звіту:
        # вона нерозривна з самим фактом створення.
        events_added=sum(1 for e in plan.events if not (e.application_id is None
                                                        and e.status == "sent")),
        ambiguous=plan.ambiguous,
        details=([f"нова подача: {c.company} — {c.position}" for c in plan.create]
                 + [f"{items[e.item_index].company}: {e.status} від {e.occurred_on}"
                    for e in plan.events
                    if not (e.application_id is None and e.status == "sent")]),
    )

    if payload.dry_run:
        return report

    created_ids: dict[int, int] = {}
    for planned in plan.create:
        obj = Application(company=planned.company, position=planned.position,
                          url=planned.url, channel=payload.source,
                          applied_on=planned.applied_on,
                          cv_version=planned.cv_version)
        session.add(obj)
        await session.flush()
        created_ids[planned.item_index] = obj.id

    by_id = {a.id: a for a in existing}
    for app_id, version in plan.fill_cv.items():
        by_id[app_id].cv_version = version

    for event in plan.events:
        app_id = event.application_id
        if app_id is None:
            app_id = created_ids[event.item_index]
        session.add(ApplicationEvent(application_id=app_id,
                                     status=Status(event.status),
                                     occurred_on=event.occurred_on,
                                     note=event.note, origin="browser-sync"))

    await session.commit()
    return report
