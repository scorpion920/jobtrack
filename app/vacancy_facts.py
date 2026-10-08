"""Тлумачення рядка ознак вакансії у величини, якими можна фільтрувати.

Канал віддає ознаки як є — «Тільки віддалено», «1 рік досвіду»,
«Англійська - B2». Звести їх до чисел і прапорців треба в ОДНОМУ місці:
інакше кожен новий канал привезе власну копію тлумачень, і вони розійдуться
саме тоді, коли від них залежатиме рішення подаватись.

Головне рішення модуля: **невпізнане не зникає**. Усе, що не лягло у відому
категорію, повертається у `unknown` і доходить до інтерфейсу. Мовчки
відкинута ознака — це та сама поломка, що й мовчазний збирач статусів: ознака
зникає, число лишається правдоподібним, і помилку не видно роками.

Межа застосовності названа чесно: формулювання тут — ті, що СПРАВДІ зустрілися
у збережених сторінках. Новий канал майже напевно додасть свої, і правильна
реакція на це — побачити їх у `unknown` і дописати зразок, а не розширювати
регулярку навмання.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Рівні англійської числом — щоб порівнювати з профілем без таблиць
# відповідності в кожному місці виклику.
ENGLISH_LEVELS = {"none": 0, "a1": 1, "a2": 2, "b1": 3, "b2": 4, "c1": 5, "c2": 6}

_ENGLISH = re.compile(r"англійськ\w*\s*[-—:]\s*(.+)$", re.I)
_NO_ENGLISH = re.compile(r"^(немає|не потрібна|no english)$", re.I)
_YEARS = re.compile(r"(\d+)\s*(?:рік|роки|років)\s+досвіду", re.I)
_NO_EXPERIENCE = re.compile(r"без досвіду", re.I)

_REMOTE = re.compile(r"тільки віддалено|remote only|віддалена робота", re.I)
_OFFICE = re.compile(r"тільки офіс|office only", re.I)
_HYBRID = re.compile(r"гібрид|hybrid", re.I)

_PART_TIME = re.compile(r"part[\s-]?time|неповн\w+ (день|зайнятість)", re.I)
_LOCATION = re.compile(r"^(україна|країни європи|європа|сша|польща|ukraine|europe|worldwide|весь світ)", re.I)


@dataclass
class Facts:
    """Витлумачені ознаки. Будь-яке поле може бути `None` — «не повідомлено».

    `None` і нуль — різні стани, і плутати їх не можна: «англійська не
    вказана» та «англійська не потрібна» ведуть до протилежних рішень.
    """

    format: str | None = None            # "remote" | "office" | "hybrid"
    years_required: int | None = None
    english: str | None = None           # ключ із ENGLISH_LEVELS
    part_time: bool = False
    location: str | None = None
    domains: list[str] = field(default_factory=list)
    unknown: list[str] = field(default_factory=list)

    @property
    def english_level(self) -> int | None:
        return ENGLISH_LEVELS.get(self.english) if self.english else None


def interpret(parts: list[str]) -> Facts:
    """Розкласти рядок ознак на величини. Порядок частин значення не має."""
    out = Facts()

    for part in parts:
        p = part.strip()
        if not p:
            continue

        if _REMOTE.search(p):
            out.format = "remote"
            continue
        if _OFFICE.search(p):
            out.format = "office"
            continue
        if _HYBRID.search(p):
            out.format = "hybrid"
            continue

        if _NO_EXPERIENCE.search(p):
            out.years_required = 0
            continue
        years = _YEARS.search(p)
        if years:
            out.years_required = int(years.group(1))
            continue

        english = _ENGLISH.search(p)
        if english:
            value = english.group(1).strip()
            out.english = "none" if _NO_ENGLISH.match(value) else value.lower()
            # Рівень, якого немає в таблиці, не мовчить: він лишається в
            # `english` як є, і одночасно потрапляє у `unknown`, щоб його
            # побачили й дописали зразок.
            if out.english not in ENGLISH_LEVELS:
                out.unknown.append(p)
            continue

        if _PART_TIME.search(p):
            out.part_time = True
            continue

        if _LOCATION.match(p):
            out.location = p
            continue

        # Решта — предметна область («Fintech», «Gambling», «SaaS»).
        # Переліку доменів у майданчика немає, тому вгадувати нічого:
        # усе, що лишилось і схоже на домен, зберігається як домен.
        out.domains.append(p)

    return out
