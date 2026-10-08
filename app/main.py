"""Точка входу: REST + мінімальний інтерфейс на Jinja.

SPA тут немає навмисно. Поверхня — три сторінки, користувач один, і React
додав би складання, залежності й час на збірку, нічого не давши натомість.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from urllib.parse import quote

from datetime import date

from fastapi import Depends, FastAPI, Form, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi import Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.applications import router as applications_router
from app.api.sync import router as sync_router
from app.api.vacancies import router as vacancies_router
from app.collect import collect
from app.dedup import Publication, find_reposts
from app.screen import Candidate, assess, find_alternative
from app.screening import screen as screen_text
from app.config import get_settings
from app.db import get_session
from app.funnel import build as build_funnel
from app.models import (Application, ApplicationEvent, Channel, SourceConfig,
                        Status, SyncRun, Vacancy)

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
app.include_router(vacancies_router)


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
async def index(request: Request, show: str = "all",
                session: AsyncSession = Depends(get_session)):
    """Журнал подач.

    `show` — зріз, бо хронологія ховає найцінніше: усе, що має стан, старе, а
    все нове за визначенням «надіслано». Щоб побачити результати, доводилось
    гортати повз два десятки рядків, які нічого не кажуть.
    """
    apps = await _all(session)

    answered = [a for a in apps if a.current_status is not Status.sent]
    # «Тихі» — лише там, де тиша взагалі щось означає: канал, який не звітує,
    # мовчить не тому, що про вас забули.
    silent = [a for a in apps
              if a.current_status is Status.sent and a.silence_is_meaningful]
    blind = [a for a in apps if not a.silence_is_meaningful]

    shown = {"answered": answered, "silent": silent, "blind": blind}.get(show, apps)

    return templates.TemplateResponse(request, "index.html", {
        "applications": shown,
        "channels": list(Channel),
        "statuses": list(Status),
        "show": show,
        "counts": {"all": len(apps), "answered": len(answered),
                   "silent": len(silent), "blind": len(blind)},
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


@app.get("/userscript.user.js")
async def userscript(request: Request):
    """Userscript для автоматичного збору статусів.

    Розширення на кшталт Tampermonkey впізнають установлюваний скрипт за
    закінченням `.user.js` і типом `text/javascript`. Токен підставляється
    сервером: інакше користувачеві довелося б вставляти його руками в код,
    а крок, який легко зробити неправильно, зрештою зроблять неправильно.
    """
    cfg = get_settings()
    js = (BASE_DIR / "static" / "userscript.js").read_text(encoding="utf-8")
    js = (js.replace("__API__", str(request.base_url).rstrip("/"))
            .replace("__TOKEN__", cfg.sync_token))
    return Response(js, media_type="text/javascript; charset=utf-8")


@app.get("/sync", response_class=HTMLResponse)
async def sync_page(request: Request,
                    session: AsyncSession = Depends(get_session)):
    """Сторінка з інструментом збору статусів.

    Токен підставляється в сам скрипт: інакше користувачеві довелося б копіювати
    його руками, а крок, який легко зробити неправильно, зрештою зроблять
    неправильно. Сторінка доступна лише локально, тож токен не виходить за
    межі машини.
    """
    cfg = get_settings()
    # Останні прогони — головна відповідь на питання «чи працює збирач».
    # ВІДСУТНІСТЬ рядків і рядок із received=0 означають різні поломки, тому
    # показуємо саме журнал, а не «час останнього успіху».
    runs = list((await session.execute(
        select(SyncRun).order_by(SyncRun.at.desc()).limit(10)
    )).scalars())
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
        "runs": runs,
    })


@app.get("/vacancies", response_class=HTMLResponse)
async def vacancies(request: Request, message: str | None = None,
                    session: AsyncSession = Depends(get_session)):
    """Перелік зібраних вакансій.

    Сортування — за свіжістю: вакансія, яку щойно опублікували, має шанс, що
    вже відсутній у тої, яка висить третій тиждень із трьома сотнями відгуків.
    """
    rows = list((await session.execute(
        select(Vacancy).order_by(Vacancy.posted_at.desc().nullslast())
    )).scalars())
    sources = list((await session.execute(
        select(SourceConfig).order_by(SourceConfig.key)
    )).scalars())

    view = []
    for v in rows:
        verdict = assess(format=v.format, years_required=v.years_required,
                         english=v.english, location=v.location)
        content = screen_text(v.raw_text, v.title)
        view.append(SimpleNamespace(**{c.name: getattr(v, c.name)
                                       for c in Vacancy.__table__.columns},
                                    blocked=verdict.blocked, reason=verdict.reason,
                                    state=verdict.state,
                                    unchecked=", ".join(verdict.unchecked),
                                    fit=content.fit,
                                    matched=content.matched,
                                    concerns=content.concerns))

    # Перевипуски: майданчик публікує ту саму вакансію вдруге, щоб підняти
    # її у видачі. Старішу не ховаємо — на неї могло бути подано, і зникнення
    # рядка виглядало б як втрата даних.
    reposts = find_reposts([
        Publication(url=v.url, source_key=v.source_key, company_norm=v.company_norm,
                    title_norm=v.title_norm, posted_at=v.posted_at)
        for v in view
    ])
    for v in view:
        v.repost_of = reposts.get(v.url)

    # Той самий варіант посади в доступному вигляді, якщо він є.
    pool = [Candidate(url=v.url, company_norm=v.company_norm,
                      title_norm=v.title_norm, blocked=v.state == "blocked")
            for v in view]
    for v, me in zip(view, pool):
        v.alternative = find_alternative(me, pool)

    # Порядок показу = порядок, у якому їх варто читати: спершу доступні зі
    # змістовним збігом, далі за зростанням конкуренції. Свіжість сама собою
    # нічого не варта, якщо на вакансію вже 300 відгуків.
    _FIT = {"strong": 0, "possible": 1, "weak": 2}
    _STATE = {"ok": 0, "unchecked": 1, "blocked": 2}
    view.sort(key=lambda v: (_STATE[v.state], _FIT[v.fit],
                             v.replies if v.replies is not None else 10 ** 6))

    last = max((s.last_run_at for s in sources if s.last_run_at), default=None)
    return templates.TemplateResponse(request, "vacancies.html", {
        "rows": view, "sources": sources, "message": message,
        "last_run": last.strftime("%d.%m %H:%M") if last else None,
    })


@app.post("/vacancies/collect/{key}")
async def vacancies_collect(key: str, session: AsyncSession = Depends(get_session)):
    config = (await session.execute(
        select(SourceConfig).where(SourceConfig.key == key)
    )).scalar_one_or_none()
    if not config:
        return RedirectResponse(f"/vacancies?message=каналу+{key}+немає", status_code=303)

    report = await collect(session, config)
    note = (f"{key}: знайдено {report.found}, нових {report.created}, "
            f"оновлено {report.refreshed}") if report.ok else f"{key}: {report.error}"
    return RedirectResponse(f"/vacancies?message={quote(note)}", status_code=303)


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
