"""Зв'язування подачі із зібраною вакансією.

Навіщо окремий модуль, а не порівняння адрес. Подача заводиться руками або
збирачем статусів, і адреса в ній несе сліди шляху: `?applied=ok` після
натискання кнопки, `?sender=` з листа, `/my/inbox/26731485/` замість самої
вакансії. Нормалізація параметрів тут не рятує — їх безліч і вони різні.

Стабільне в адресі одне: **номер вакансії на майданчику**. Djinni і DOU
обидва тримають його в шляху, тож ключ будується з нього, а все інше
ігнорується само собою.

Перевірено на реальному журналі 08.10.2026: точний збіг адрес зводив ОДНУ
подачу з восьми, ключ за номером — сім (восьма веде на сторінку листування,
а не на вакансію, і зв'язати її неможливо в принципі).
"""

from __future__ import annotations

import re

_DJINNI = re.compile(r"djinni\.co/jobs/(\d+)", re.I)
_DOU = re.compile(r"jobs\.dou\.ua/(?:companies/[^/]+/)?vacancies/(\d+)", re.I)


def vacancy_key(url: str | None) -> tuple[str, str] | None:
    """`(майданчик, номер)` або `None`, якщо адреса не веде на вакансію.

    `None` — звичайний стан, а не збій: подача могла прийти поштою, з
    LinkedIn або зі сторінки листування. Зв'язувати тоді нема з чим, і
    вигадувати зв'язок за назвою компанії небезпечно — у великої компанії
    одночасно відкрито кілька вакансій.
    """
    if not url:
        return None
    m = _DJINNI.search(url)
    if m:
        return ("djinni", m.group(1))
    m = _DOU.search(url)
    if m:
        return ("dou", m.group(1))
    return None


def link(applications: list[tuple[int, str | None]],
         vacancies: list[tuple[int, str, str]]) -> dict[int, int]:
    """{id подачі: id вакансії}.

    `applications` — (id, url), `vacancies` — (id, source_key, external_id).
    Повертає лише однозначні зв'язки.
    """
    by_key = {(source, external): vid for vid, source, external in vacancies}
    out: dict[int, int] = {}
    for app_id, url in applications:
        key = vacancy_key(url)
        if key and key in by_key:
            out[app_id] = by_key[key]
    return out
