"""Точка входу: REST + мінімальний інтерфейс на Jinja.

SPA тут немає навмисно. Поверхня — три сторінки, користувач один, і React
додав би складання, залежності й час на збірку, нічого не давши натомість.
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

from datetime import date

from fastapi import Depends, FastAPI, Form, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.applications import router as applications_router
from app.api.sync import router as sync_router
from app.config import get_settings
from app.db import get_session
from app.funnel import build as build_funnel
from app.models import Application, ApplicationEvent, Channel, Status

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app = FastAPI(title="jobtrack", version="0.1.0",
              description="Журнал подач і моніторинг вакансій")
# Скрипт збору статусів виконується НА сторінці майданчика (djinni.co), а
# звертається сюди. Для браузера це міждоменний запит із власним заголовком
# `X-Sync-Token`, тож він спершу шле передпольотний OPTIONS — і без дозволу
# ріже все, навіть не дійшовши до перевірки токена.
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_methods=["POST", "OPTIONS"],
    allow_headers=["Content-Type", "X-Sync-Token"],
    # Куки не передаємо: автентифікація йде заголовком із токеном, тому
    # дозволяти облікові дані немає потреби.
    allow_credentials=False,
)

app.include_router(applications_router)
app.include_router(sync_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


async def _all(session: AsyncSession) -> list[Application]:
    res = await session.execute(
        select(Application).options(selectinload(Application.events))
        .order_by(Application.applied_on.desc(), Application.id.desc())
    )
    return list(res.scalars())


@app.get("/", response_class=HTMLResponse)
async def index(request: Request, session: AsyncSession = Depends(get_session)):
    apps = await _all(session)
    return templates.TemplateResponse(request, "index.html", {
        "applications": apps,
        "channels": list(Channel),
        "statuses": list(Status),
    })


@app.post("/ui/applications")
async def ui_create(
    request: Request,
    company: str = Form(...),
    position: str = Form(...),
    channel: Channel = Form(Channel.djinni),
    applied_on: date = Form(...),
    cv_version: str = Form(""),
    url: str = Form(""),
    session: AsyncSession = Depends(get_session),
):
    """Форма з головної сторінки. Окремо від REST, бо браузер уміє лише
    `application/x-www-form-urlencoded` без JavaScript, а SPA тут навмисно немає."""
    item = Application(
        company=company.strip(), position=position.strip(), channel=channel,
        applied_on=applied_on, cv_version=cv_version.strip() or None,
        url=url.strip() or None,
    )
    session.add(item)
    await session.flush()
    session.add(ApplicationEvent(application_id=item.id, status=Status.sent,
                                 occurred_on=applied_on, origin="manual"))
    await session.commit()
    return RedirectResponse("/", status_code=303)


@app.get("/sync", response_class=HTMLResponse)
async def sync_page(request: Request):
    """Сторінка з інструментом збору статусів.

    Токен підставляється в сам скрипт: інакше користувачеві довелося б копіювати
    його руками, а крок, який легко зробити неправильно, зрештою зроблять
    неправильно. Сторінка доступна лише локально, тож токен не виходить за
    межі машини.
    """
    cfg = get_settings()
    js = (BASE_DIR / "static" / "collect.js").read_text(encoding="utf-8")
    js = (js.replace("__API__", str(request.base_url).rstrip("/"))
            .replace("__TOKEN__", cfg.sync_token)
            .replace("__SOURCE__", "djinni"))
    minified = " ".join(line.strip() for line in js.splitlines()
                        if line.strip() and not line.strip().startswith("//"))
    return templates.TemplateResponse(request, "sync.html", {
        "snippet": js,
        "diagnose": (BASE_DIR / "static" / "diagnose.js").read_text(encoding="utf-8"),
        "snippet_dou": ((BASE_DIR / "static" / "collect_dou.js").read_text(encoding="utf-8")
                        .replace("__API__", str(request.base_url).rstrip("/"))
                        .replace("__TOKEN__", cfg.sync_token)),
        "bookmarklet": "javascript:" + quote(minified, safe=""),
        "token_set": bool(cfg.sync_token),
    })


@app.get("/funnel", response_class=HTMLResponse)
async def funnel(request: Request, by: str = "channel",
                 session: AsyncSession = Depends(get_session)):
    apps = await _all(session)
    if by not in {"channel", "cv_version", "week"}:
        by = "channel"
    return templates.TemplateResponse(request, "funnel.html", {
        "rows": build_funnel(apps, by),
        "by": by,
        "total": len(apps),
    })
