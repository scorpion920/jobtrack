"""Канал Djinni: читання публічного переліку вакансій.

Правила майданчика перевірено за `robots.txt` 08.10.2026: заборонені `/jobs2`,
`/q`, `/developers`, `/free-jobs`, `/set_lang`; сторінки вакансій дозволені.
Тому збір ведеться лише з `/jobs/`, ввічливим темпом і з `User-Agent`, у якому
стоїть контакт — щоб адміністратор майданчика мав до кого звернутися, а не
мусив блокувати наосліп.

Розбір і мережа розділені навмисно: `parse_listing()` — чиста функція від
рядка HTML, тож тести ганяються на збереженій сторінці й не залежать ані від
мережі, ані від того, що сьогодні опубліковано. Коли Djinni змінить розмітку,
впаде саме тест розбору, а не щось віддалене від причини.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Iterable

from bs4 import BeautifulSoup, Tag

from app.sources.base import RawVacancy

KEY = "djinni"
BASE = "https://djinni.co"

# Час публікації майданчик кладе у підказку: «9г» у тексті, але
# title="10:54 08.10.2026". Беремо точне значення — відносне ламається, щойно
# сторінку збережено й прочитано пізніше.
_WHEN = re.compile(r"^(\d{2}):(\d{2})\s+(\d{2})\.(\d{2})\.(\d{4})$")
_VIEWS = re.compile(r"(\d[\d\s ]*)\s*перегляд")
_REPLIES = re.compile(r"(\d[\d\s ]*)\s*відгук")
_ID = re.compile(r"^job-item-(\d+)$")


def _text(node: Tag | None) -> str:
    return re.sub(r"\s+", " ", node.get_text(" ", strip=True)) if node else ""


def _int(raw: str) -> int | None:
    digits = re.sub(r"[^\d]", "", raw)
    return int(digits) if digits else None


def _posted_at(block: Tag) -> datetime | None:
    for span in block.select("span[title]"):
        m = _WHEN.match(span["title"].strip())
        if m:
            hh, mm, dd, mo, yy = (int(g) for g in m.groups())
            return datetime(yy, mo, dd, hh, mm)
    return None


def _facts(block: Tag) -> list[str]:
    """Рядок ознак: «Тільки віддалено · Україна · 1 рік досвіду · Англійська - A2».

    Шукаємо його за ВМІСТОМ, а не за повним набором класів: класи-утиліти
    Bootstrap на цьому майданчику переставляються від релізу до релізу, і
    прив'язка до їх порядку — найкоротший шлях до мовчазної поломки.
    """
    for div in block.find_all("div", class_="fw-medium"):
        if div.find("span", class_="middot") or div.find("span", class_="location-text"):
            return [p.strip() for p in _text(div).split("·") if p.strip()]
    return []


def _description(block: Tag, external_id: str) -> str:
    box = block.find(id=f"job-description-{external_id}")
    if not box:
        return ""
    # Повний текст лежить прихованим поруч зі скороченим; беремо саме його,
    # інакше скринер судив би про вакансію за трьома першими реченнями.
    full = box.find("span", class_="js-original-text")
    return _text(full) if full else _text(box.find("span", class_="js-truncated-text"))


def parse_listing(html: str) -> list[RawVacancy]:
    """Розібрати сторінку переліку вакансій.

    Пропускає блок, у якого немає посилання або назви: напівпорожній запис
    гірший за його відсутність — він створює вакансію, яку ніхто не зможе
    відкрити, і вона назавжди лишається в переліку як сміття.
    """
    soup = BeautifulSoup(html, "html.parser")
    out: list[RawVacancy] = []

    for block in soup.find_all("div", id=_ID):
        external_id = _ID.match(block["id"]).group(1)

        link = block.find("a", class_="job_item__header-link")
        title = _text(block.find("h2", class_="job-item__position"))
        if not link or not link.get("href") or not title:
            continue

        company_node = block.find("span", class_="text-gray-800")
        facts = _facts(block)
        blob = _text(block)

        salary_tier = block.find("span", class_="text-body-tertiary")
        tags = [_text(t) for t in block.select(".job-item__tags .badge")]

        views, replies = _VIEWS.search(blob), _REPLIES.search(blob)
        description = _description(block, external_id)

        out.append(RawVacancy(
            source_key=KEY,
            external_id=external_id,
            url=BASE + link["href"],
            title=title,
            company=_text(company_node) or "—",
            # Назва й компанія входять у текст свідомо: скринер шукає
            # ключові слова і в заголовку теж, а окремо склеювати їх у
            # кожному місці означало б забути це зробити в якомусь одному.
            raw_text="\n".join(x for x in [title, " · ".join(facts), description] if x),
            posted_at=_posted_at(block),
            payload={
                "facts": facts,
                "tags": tags,
                "salary_tier": len(_text(salary_tier)) or None,
                "views": _int(views.group(1)) if views else None,
                "replies": _int(replies.group(1)) if replies else None,
            },
        ))

    return out


# ─────────────────────────────── мережа ───────────────────────────────
#
# Нижче — єдине місце модуля, яке ходить назовні. Розбір вище від нього не
# залежить, тому тести розбору не потребують ані мережі, ані моків.

import asyncio  # noqa: E402

import httpx  # noqa: E402

from app.config import get_settings  # noqa: E402

# Ввічливий темп. Не рекомендація: збір публічних сторінок у межах правил
# майданчика тримається саме на тому, що він не створює навантаження.
# 10 секунд між запитами — приблизно темп людини, яка гортає перелік.
MIN_INTERVAL_SECONDS = 10.0

# Скільки сторінок переліку читати за прогін — межа зверху, не ціль.
MAX_PAGES = 5

DEFAULT_LISTING = "/jobs/?primary_keyword=Python&exp_level=1y"


class DjinniSource:
    """Адаптер каналу Djinni.

    `params`:
        listing  — шлях переліку з фільтрами, як його показує адресний рядок
                   майданчика. За замовчуванням — Python з порогом «1 рік».
        pages    — скільки сторінок читати (не більше MAX_PAGES).
    """

    def __init__(self, key: str = KEY, params: dict | None = None) -> None:
        self.key = key
        params = params or {}
        self.listing = params.get("listing") or DEFAULT_LISTING
        self.pages = max(1, min(int(params.get("pages", 2)), MAX_PAGES))

    def _page_url(self, page: int) -> str:
        sep = "&" if "?" in self.listing else "?"
        return BASE + self.listing + ("" if page == 1 else f"{sep}page={page}")

    @staticmethod
    def _has_next_page(html: str) -> bool:
        """Чи дає сама сторінка посилання на наступну.

        НЕ «чи можна підставити page=2». Перевірено 08.10.2026 дорогою ціною:
        Djinni на `?page=2` для фільтра з однією сторінкою віддає не порожнечу
        і не помилку, а ІНШИЙ, нефільтрований перелік. Дані приходять валідні,
        у правильній розмітці, з усіма полями — і просто не ті: замість
        Python-вакансій приїхали Media Buyer і Supply Chain Manager.

        Захист «порожньо → зупинитись» такого не ловить за побудовою: він
        перевіряє НАЯВНІСТЬ, а зламалась ТОТОЖНІСТЬ. Тому єдине джерело істини
        про наступну сторінку — сама сторінка.
        """
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.select("a[href]"):
            if "page=" in a["href"]:
                return True
        return False

    async def fetch(self) -> list[RawVacancy]:
        """Прочитати перелік. Повертає те, що СПРАВДІ розібралось.

        Сторінка, яку не вдалось прочитати, не обриває прогін: решта каналу
        від неї не залежить. Але й не зникає мовчки — причина піднімається
        вгору винятком лише тоді, коли не прочиталась ЖОДНА сторінка, бо саме
        це означає «канал не працює», а не «одна сторінка не відкрилась».
        """
        out: list[RawVacancy] = []
        failures: list[str] = []
        headers = {"User-Agent": get_settings().user_agent,
                   "Accept-Language": "uk,en;q=0.8"}

        async with httpx.AsyncClient(headers=headers, timeout=30.0,
                                     follow_redirects=True) as client:
            for page in range(1, self.pages + 1):
                if page > 1:
                    await asyncio.sleep(MIN_INTERVAL_SECONDS)
                url = self._page_url(page)
                try:
                    response = await client.get(url)
                    response.raise_for_status()
                except httpx.HTTPError as exc:
                    failures.append(f"{url}: {exc}")
                    break

                rows = parse_listing(response.text)
                if not rows:
                    if page == 1:
                        failures.append(f"{url}: сторінка прочитана, вакансій не знайдено")
                    break
                out.extend(rows)

                # Наступну сторінку беремо, лише якщо майданчик сам на неї
                # послався. Інакше зупиняємось — навіть коли ліміт не вичерпано.
                if not self._has_next_page(response.text):
                    break

        if not out and failures:
            raise RuntimeError("канал djinni не дав нічого: " + "; ".join(failures))
        return out
