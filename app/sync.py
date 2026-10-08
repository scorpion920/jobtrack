"""Зіставлення записів, прочитаних у браузері, з журналом подач.

Чому це окремий модуль із чистими функціями: зіставлення — найтонше місце
всієї системи. Та сама подача приходить із різними написаннями назви компанії,
з URL із трекінговими параметрами і без них, іноді взагалі без URL. Помилка
зіставлення або створює дубль, або дописує подію чужій подачі — і те й інше
псує саме те число, заради якого все будувалося.

Тому логіка зіставлення тестується без БД і без мережі.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from urllib.parse import urlsplit, urlunsplit

# Параметри, що не змінюють сторінку, лише позначають, звідки на неї прийшли.
_TRACKING = re.compile(r"^(utm_|gclid|fbclid|ref|from|source$)", re.I)
_WS = re.compile(r"\s+")
_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)

# Суфікси організаційно-правової форми: «ТОВ Вчасно» і «Вчасно» — одне й те саме.
_LEGAL = {
    "тов", "пп", "фоп", "пат", "прат", "ат", "дп", "ооо", "зао", "оао",
    "llc", "ltd", "inc", "corp", "gmbh", "co", "company", "sp", "zoo",
}


def normalize_url(url: str | None) -> str | None:
    """Прибирає те, що не змінює адресу сторінки: схему, www, трекінг, слеш.

    Без цього та сама вакансія, відкрита з листа і з пошуку, дасть два записи.
    """
    if not url or not url.strip():
        return None
    parts = urlsplit(url.strip())
    if not parts.netloc:
        return None

    host = parts.netloc.lower().removeprefix("www.")
    path = parts.path.rstrip("/") or "/"
    query = "&".join(
        sorted(q for q in parts.query.split("&")
               if q and not _TRACKING.match(q.split("=", 1)[0]))
    )
    return urlunsplit(("https", host, path, query, ""))


def normalize_name(value: str | None) -> str:
    """Канонічна форма назви для нечіткого зіставлення."""
    if not value:
        return ""
    text = _PUNCT.sub(" ", value.lower())
    words = [w for w in _WS.split(text) if w and w not in _LEGAL]
    return " ".join(words)


@dataclass(frozen=True)
class SyncItem:
    """Один рядок, прочитаний зі сторінки відгуків."""

    company: str
    position: str
    url: str | None = None
    applied_on: date | None = None
    status: str | None = None
    status_on: date | None = None
    note: str | None = None
    # Яким саме резюме подавались. DOU показує ім'я файлу, Djinni — ні.
    # Без цього поля воронка не може порівняти версії між собою, а саме
    # заради такого порівняння журнал і ведеться.
    cv_version: str | None = None


@dataclass
class Candidate:
    """Мінімум, потрібний для зіставлення. Навмисно не ORM-модель —
    щоб логіку можна було перевірити без бази."""

    id: int
    company: str
    position: str
    url: str | None
    cv_version: str | None = None


def find_match(item: SyncItem, candidates: list[Candidate]) -> Candidate | None:
    """Шукає подачу, якій належить прочитаний рядок.

    Два рівні за спаданням надійності:
      1. нормалізований URL — точний збіг;
      2. нормалізовані назва компанії І позиція разом.

    Збігу лише за компанією НЕ досить: в одну компанію можна подаватись на
    кілька позицій, і зарахувати подію не тій — гірше, ніж не зарахувати нікому.
    """
    url = normalize_url(item.url)
    if url:
        for c in candidates:
            if normalize_url(c.url) == url:
                return c

    company = normalize_name(item.company)
    position = normalize_name(item.position)
    if not company or not position:
        return None

    hits = [c for c in candidates
            if normalize_name(c.company) == company
            and normalize_name(c.position) == position]

    # Два однакові кандидати означають, що в журналі вже є дубль. Вибір
    # навмання приховав би його; краще не зарахувати й показати в підсумку.
    return hits[0] if len(hits) == 1 else None


# ─── Планування синхронізації ────────────────────────────────────────────────
#
# Рішення «що саме зробити» відокремлене від «зробити». Причина не естетична:
# перша редакція перевіряла наявні події через `target.events` на щойно
# створеному ORM-об'єкті, і SQLAlchemy намагався довантажити зв'язок ліниво —
# поза greenlet-контекстом, тобто з `MissingGreenlet`. Помилка проявилась лише
# на справжньому записі, бо сухий прогін до тієї гілки не доходив.
#
# Корінь був не в лінивому завантаженні, а в тому, що логіка взагалі торкалась
# ORM. Тепер вона працює з простими структурами, і цей клас помилок до неї не
# має доступу. Побічно це зробило її придатною до тестування без бази.


@dataclass
class PlannedEvent:
    application_id: int | None   # None = подача ще не створена в цьому прогоні
    item_index: int
    status: str
    occurred_on: date
    note: str | None = None


@dataclass
class PlannedApplication:
    item_index: int
    company: str
    position: str
    url: str | None
    applied_on: date
    cv_version: str | None = None


@dataclass
class SyncPlan:
    create: list[PlannedApplication]
    events: list[PlannedEvent]
    matched: int = 0
    ambiguous: list[str] = None  # type: ignore[assignment]
    # id подачі → версія резюме, якої їй бракувало.
    fill_cv: dict[int, str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.ambiguous is None:
            self.ambiguous = []
        if self.fill_cv is None:
            self.fill_cv = {}


def plan_sync(
    items: list[SyncItem],
    candidates: list[Candidate],
    known_events: dict[int, set[tuple[str, date]]],
    today: date,
) -> SyncPlan:
    """Вирішує, що створити й які події додати. Нічого не записує.

    `known_events` — вже наявні пари (стан, дата) по кожній подачі. Саме за ними
    працює ідемпотентність: повторна синхронізація тієї самої сторінки не має
    додавати жодного рядка.
    """
    plan = SyncPlan(create=[], events=[])
    pool = list(candidates)

    for idx, item in enumerate(items):
        hit = find_match(item, pool)
        app_id: int | None

        if hit is not None:
            plan.matched += 1
            app_id = hit.id
            # Доповнюємо ПОРОЖНЄ, але ніколи не затираємо заповнене.
            # Перший прогін DOU не зчитав імені файлу резюме через хибний
            # контейнер; без цього правила виправлення збирача нічого б не
            # дало — зіставлені рядки лишились би назавжди без версії.
            if item.cv_version and not hit.cv_version:
                plan.fill_cv[hit.id] = item.cv_version
        else:
            same_company = [c for c in pool
                            if normalize_name(c.company) == normalize_name(item.company)]
            if len(same_company) > 1:
                # Кілька подач у ту саму компанію, але позиція не збіглася з
                # жодною. Створити ще одну — найімовірніше, зробити дубль.
                plan.ambiguous.append(f"{item.company} / {item.position}")
                continue

            applied = item.applied_on or today
            plan.create.append(PlannedApplication(idx, item.company.strip(),
                                                  item.position.strip(),
                                                  item.url, applied,
                                                  item.cv_version))
            app_id = None
            # Нова подача одразу стає кандидатом: якщо та сама вакансія
            # трапиться у списку двічі, другий рядок має зіставитись, а не
            # створити дубль.
            pool.append(Candidate(-(len(plan.create)), item.company,
                                  item.position, item.url))
            plan.events.append(PlannedEvent(None, idx, "sent", applied))

        if not item.status:
            continue

        when = item.status_on or today
        if app_id is not None and (item.status, when) in known_events.get(app_id, set()):
            continue
        plan.events.append(PlannedEvent(app_id, idx, item.status, when, item.note))

    return plan
