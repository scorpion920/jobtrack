"""Перевипуски: та сама вакансія, опублікована майданчиком удруге.

Знайдено оператором у переліку 08.10.2026: Office.kh.ua «Python Developer
(Django)» стоїть двічі — 27.09 з 80 відгуками і 08.10 з трьома. Це не збій
дедуплікації: у майданчика це РІЗНІ оголошення з різними ідентифікаторами,
і ключ `(канал, зовнішній ід)` відпрацював правильно.

Ховати старішу не можна з двох причин:

1. **Свіжа публікація з трьома відгуками краща за стару з вісімдесятьма.**
   Якби ми лишали «першу знайдену», оператор бачив би гіршу з двох.
2. **Відгук на старій лишається відгуком.** Якщо на неї вже подано, зникнення
   рядка з переліку виглядало б як втрата даних.

Тому старішу лишаємо видимою, але позначаємо — із посиланням на свіжу.

Групуємо ТІЛЬКИ в межах одного майданчика. Та сама вакансія на Djinni і на
DOU — не перевипуск, а два канали однієї вакансії, і кількість відгуків у них
непорівнянна: DOU її взагалі не повідомляє.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Publication:
    """Мінімум, потрібний, щоб упізнати перевипуск."""

    url: str
    source_key: str
    company_norm: str
    title_norm: str
    posted_at: datetime | None


def find_reposts(items: list[Publication]) -> dict[str, str]:
    """Повертає {url старішої публікації: url найсвіжішої}.

    Публікація без дати вважається старішою за будь-яку з датою: ми не знаємо,
    коли вона вийшла, і ставити її головною означало б ховати за нею свіжу.
    """
    groups: dict[tuple[str, str, str], list[Publication]] = {}
    for item in items:
        groups.setdefault((item.source_key, item.company_norm, item.title_norm),
                          []).append(item)

    reposts: dict[str, str] = {}
    for group in groups.values():
        if len(group) < 2:
            continue
        newest = max(group, key=lambda p: (p.posted_at is not None,
                                           p.posted_at or datetime.min))
        for item in group:
            if item.url != newest.url:
                reposts[item.url] = newest.url
    return reposts
