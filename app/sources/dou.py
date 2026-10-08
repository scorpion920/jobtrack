"""Канал DOU — через офіційний RSS.

Спочатку цей канал планувався через Playwright з обходом JS-челенджу. Виявилось
непотрібним: `jobs.dou.ua/vacancies/feeds/` віддає повноцінний фід з описами,
і це офіційний, призначений для машин шлях. Окремий контейнер із браузером
скасовано — разом із найкрихкішою частиною системи.

Що DOU НЕ дає, на відміну від Djinni: років досвіду, рівня англійської,
кількості відгуків. Це не вада розбору, а властивість каналу, і система мусить
це розрізняти: `None` тут означає «канал не повідомляє», а не «не вимагає».
Саме тому порівнювати конкуренцію між каналами не можна — лише всередині.
"""

from __future__ import annotations

import re

from app.sources.base import RawVacancy
from app.sources.rss import parse_feed

KEY = "dou"
BASE = "https://jobs.dou.ua"
DEFAULT_FEED = "/vacancies/feeds/?category=Python"

# Посилання на вакансію містить і компанію, і номер:
#   /companies/ciklum/vacancies/358037/
_FROM_URL = re.compile(r"/companies/([^/]+)/vacancies/(\d+)")
# Запасний варіант для вакансій поза компанією: /vacancies/358037/
_PLAIN_ID = re.compile(r"/vacancies/(\d+)")

# Заголовок: «Посада в Компанія, Локація, Локація, віддалено».
# Розділювач беремо ОСТАННІЙ: назва посади частіше містить « в », ніж назва
# компанії (порівняй «Engineer в команду X в Ciklum»).
_SPLIT = " в "
_REMOTE = re.compile(r",\s*віддалено\s*$", re.I)


def _company_slug(url: str) -> str:
    m = _FROM_URL.search(url)
    return m.group(1) if m else ""


def _external_id(url: str) -> str:
    m = _FROM_URL.search(url) or _PLAIN_ID.search(url)
    # Без номера вакансія не має стійкого ідентифікатора, і дедуплікація
    # злетить на першій же зміні адреси. Краще пропустити, ніж завести
    # запис, який завтра приїде вдруге.
    return m.group(2) if m and m.lastindex == 2 else (m.group(1) if m else "")


def parse_dou_title(title: str) -> tuple[str, str, str | None, str]:
    """Розкласти заголовок на посаду, компанію, формат і локації.

    Повертає `(посада, компанія, формат, локації)`. Коли розділювач не
    знайдено, посадою стає весь заголовок, а компанія лишається порожньою —
    її підставить виклична сторона з адреси. Мовчки вигадувати тут нічого
    не можна: неправильно розділена назва отруїть дедуплікацію за
    (компанія, посада) назавжди.
    """
    remote = bool(_REMOTE.search(title))
    body = _REMOTE.sub("", title).strip()

    if _SPLIT not in body:
        return body, "", ("remote" if remote else None), ""

    position, rest = body.rsplit(_SPLIT, 1)
    company, _, locations = rest.partition(",")
    return (position.strip(), company.strip(),
            ("remote" if remote else None), locations.strip())


def parse_dou_feed(xml: str) -> list[RawVacancy]:
    out: list[RawVacancy] = []

    for item in parse_feed(xml):
        external_id = _external_id(item.link)
        if not external_id:
            continue

        position, company, fmt, locations = parse_dou_title(item.title)
        if not company:
            # Запасний шлях — slug з адреси: негарно, але стійко.
            company = _company_slug(item.link).replace("-", " ").title()

        # У `facts` кладемо ЛИШЕ те, що має вигляд ознаки у стилі Djinni.
        # Локації DOU сюди не йдуть: вони бувають довільним текстом
        # («We're a fully remote team…» у PLANEKS) або несуть залишок назви
        # компанії («Inc.» у Svitla Systems, Inc.), і тлумач ознак, не
        # впізнавши їх, записав би це у предметну область.
        facts = ["Тільки віддалено"] if fmt == "remote" else []

        out.append(RawVacancy(
            source_key=KEY,
            external_id=external_id,
            # Посилання чистимо від мітки джерела: вона не частина адреси
            # вакансії, а слід того, звідки ми прийшли.
            url=item.link.split("?")[0],
            title=position,
            company=company,
            raw_text="\n".join(x for x in [position, item.description] if x),
            posted_at=item.published,
            payload={
                "facts": facts,
                "tags": [],
                # DOU не повідомляє конкуренції — і це видно явно, а не
                # вгадується нулем.
                "replies": None,
                "views": None,
                "salary_tier": None,
                "title_raw": item.title,
                # Локація окремим ключем — як довідка, а не як ознака.
                # Обрізаємо під ширину колонки; це довідкове поле, і втрата
                # хвоста довгого речення нічого не вирішує.
                "location": locations[:200] or None,
            },
        ))

    return out


# ─────────────────────────────── мережа ───────────────────────────────

import httpx  # noqa: E402

from app.config import get_settings  # noqa: E402


class DouSource:
    """Адаптер каналу DOU.

    Один запит на прогін: фід віддає всі свіжі вакансії категорії одразу,
    тож ані пагінації, ані пауз тут не потрібно — а отже й немає місця для
    помилки, яка коштувала нам чужих даних на Djinni.

    `params`:
        feed — шлях фіду з категорією, як його дає майданчик.
    """

    def __init__(self, key: str = KEY, params: dict | None = None) -> None:
        self.key = key
        self.feed = (params or {}).get("feed") or DEFAULT_FEED

    @property
    def url(self) -> str:
        return BASE + self.feed

    async def fetch(self) -> list[RawVacancy]:
        headers = {"User-Agent": get_settings().user_agent}
        async with httpx.AsyncClient(headers=headers, timeout=30.0,
                                     follow_redirects=True) as client:
            response = await client.get(self.url)
            response.raise_for_status()

        rows = parse_dou_feed(response.text)
        if not rows:
            # Фід, який відкрився і не дав жодної вакансії, — це або порожня
            # категорія, або змінений формат. Промовчати не можна: обидва
            # випадки виглядають як «нових вакансій немає».
            raise RuntimeError(f"фід {self.url} прочитано, вакансій не знайдено")
        return rows
