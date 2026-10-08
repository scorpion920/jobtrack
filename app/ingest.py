"""Рішення про те, що робити з принесеними вакансіями.

Чиста логіка, без ORM і без сесії — як і `sync.py`. Причина та сама і вона
оплачена: звернення до зв'язку на щойно створеному об'єкті дало `MissingGreenlet`
у реальному записі, і лікувалося не guard'ом, а винесенням рішення туди, де
бази взагалі немає. Тут можна помилитися лише в логіці, і тест це покаже без
контейнера.

Три рівні дедуплікації, і вони різні за силою:

1. **(канал, зовнішній ід)** — тримає СХЕМА, унікальним індексом. Помилка в
   адаптері не повинна мати можливості завести ту саму вакансію двічі.
2. **посилання** — у межах каналу збігається з першим; між каналами різне.
3. **(компанія, посада)** — підозра на ту саму вакансію з РІЗНИХ каналів.
   Вона лише ПОВІДОМЛЯЄТЬСЯ, а не зливається автоматично: доки канал один,
   зливати нема чого, а автоматичне злиття за схожістю назв — найкоротший
   шлях сховати дві різні вакансії однієї компанії під одним записом.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from app.sources.base import RawVacancy
from app.sync import normalize_name
from app.vacancy_facts import interpret


@dataclass(frozen=True)
class KnownVacancy:
    """Те, що вже є в базі, у вигляді, який не вимагає сесії."""

    id: int
    source_key: str
    external_id: str
    company_norm: str
    title_norm: str
    replies: int | None = None


@dataclass
class NewVacancy:
    """Запис, який належить створити. Поля вже витлумачені."""

    raw: RawVacancy
    company_norm: str
    title_norm: str
    format: str | None
    years_required: int | None
    english: str | None
    part_time: bool
    location: str | None


@dataclass
class Refresh:
    """Вакансія вже відома — змінилось лише те, що змінюється з часом."""

    vacancy_id: int
    last_seen: datetime
    replies: int | None
    views: int | None
    # Наскільки зросла конкуренція з минулого разу. None, коли порівнювати
    # нема з чим; саме ця величина, а не абсолютне число, показує, чи
    # вакансія «розігрівається».
    replies_delta: int | None = None


@dataclass
class IngestPlan:
    create: list[NewVacancy] = field(default_factory=list)
    refresh: list[Refresh] = field(default_factory=list)
    # Підозри на ту саму вакансію з іншого каналу: (нова, вже відома).
    # Не зливаємо — показуємо.
    cross_channel: list[tuple[str, str]] = field(default_factory=list)


def plan_ingest(rows: list[RawVacancy], known: list[KnownVacancy],
                now: datetime) -> IngestPlan:
    """Вирішити долю кожної принесеної вакансії.

    Повторюваний виклик з тими самими даними не створює нічого нового — це
    головна властивість: збір іде за розкладом, і кожен прогін бачить ті самі
    вакансії, що й попередній.
    """
    plan = IngestPlan()

    by_external = {(k.source_key, k.external_id): k for k in known}
    by_name: dict[tuple[str, str], KnownVacancy] = {}
    for k in known:
        by_name.setdefault((k.company_norm, k.title_norm), k)

    seen_now: set[tuple[str, str]] = set()

    for raw in rows:
        # Канал може віддати ту саму вакансію двічі в межах однієї сторінки
        # (так буває при переході між сторінками переліку). Другий раз —
        # не оновлення, а шум.
        if raw.dedup_key in seen_now:
            continue
        seen_now.add(raw.dedup_key)

        company_norm = normalize_name(raw.company)
        title_norm = normalize_name(raw.title)

        existing = by_external.get(raw.dedup_key)
        if existing:
            replies = raw.payload.get("replies")
            delta = (replies - existing.replies
                     if replies is not None and existing.replies is not None else None)
            plan.refresh.append(Refresh(
                vacancy_id=existing.id, last_seen=now,
                replies=replies, views=raw.payload.get("views"),
                replies_delta=delta,
            ))
            continue

        twin = by_name.get((company_norm, title_norm))
        if twin and twin.source_key != raw.source_key:
            plan.cross_channel.append((raw.url, twin.source_key))

        facts = interpret(raw.payload.get("facts", []))
        plan.create.append(NewVacancy(
            raw=raw, company_norm=company_norm, title_norm=title_norm,
            format=facts.format, years_required=facts.years_required,
            english=facts.english, part_time=facts.part_time,
            location=facts.location,
        ))

    return plan
