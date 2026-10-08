"""Базовий читач RSS.

Окремо від конкретного каналу, бо RSS — формат, а не майданчик: той самий
розбір обслуговує DOU, стрічки компаній і будь-що інше, що віддає фід.
Специфічне для майданчика (як саме в заголовку закодовано компанію й формат)
лишається в його власному адаптері.

Чому stdlib, а не `feedparser`: у фіді, який нас цікавить, немає нічого, заради
чого варто тягнути залежність. `xml.etree` розбирає його повністю.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from datetime import datetime
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree

_TAGS = re.compile(r"<[^>]+>")
_SPACE = re.compile(r"[ \t]+")

# Посилання з чужого фіду потрапляє просто в `href` на нашій сторінці.
# Екранування Jinja захищає від лапок, але НЕ від схеми: `javascript:alert(1)`
# у `<link>` лишився б клікабельним кодом. Тому схема перевіряється на вході —
# це інваріант, а не фільтр на виході.
_SAFE_SCHEME = re.compile(r"^https?://", re.I)


def is_safe_link(url: str) -> bool:
    return bool(_SAFE_SCHEME.match((url or "").strip()))


@dataclass(frozen=True)
class FeedItem:
    """Запис фіду, як він є. Нічого не витлумачено."""

    title: str
    link: str
    description: str
    published: datetime | None
    guid: str


def strip_html(raw: str) -> str:
    """Текст із HTML-опису.

    Розгортаємо сутності ДВІЧІ свідомо: у RSS опис уже екранований один раз
    (`&lt;p&gt;`), а всередині трапляється другий рівень (`&amp;amp;`). Один
    прохід лишив би в тексті `&amp;` і зіпсував би пошук за словами.
    """
    text = html.unescape(html.unescape(raw or ""))
    text = _TAGS.sub(" ", text)
    text = _SPACE.sub(" ", text)
    return "\n".join(line.strip() for line in text.splitlines() if line.strip())


def parse_feed(xml: str) -> list[FeedItem]:
    """Розібрати фід. Запис без посилання або назви пропускається."""
    root = ElementTree.fromstring(xml)
    out: list[FeedItem] = []

    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        if not title or not link:
            continue
        if not is_safe_link(link):
            # Запис із посиланням небезпечної схеми не беремо взагалі:
            # «полагодити» таке посилання неможливо, а вакансія без робочої
            # адреси все одно нічого не варта.
            continue

        raw_date = item.findtext("pubDate")
        published: datetime | None = None
        if raw_date:
            try:
                published = parsedate_to_datetime(raw_date)
            except (TypeError, ValueError):
                # Невідомий формат дати не має коштувати нам вакансії:
                # дата тут допоміжна, а посилання й назва — ні.
                published = None

        out.append(FeedItem(
            title=html.unescape(title),
            link=link,
            description=strip_html(item.findtext("description") or ""),
            published=published,
            guid=(item.findtext("guid") or link).strip(),
        ))

    return out
