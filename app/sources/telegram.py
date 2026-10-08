"""Канал Telegram: читання публічних каналів з вакансіями.

Чому MTProto, а не бот. Бот не бачить каналу, у якому не перебуває, і не може
читати його історію — для читання потрібен обліковий запис користувача. Це
означає, що файл сесії рівноцінний входу в акаунт, тож він лежить у `data/`,
який не потрапляє ані в git, ані в образ.

Головна відмінність від Djinni і DOU: **структури немає**. Майданчик віддає
поля, канал — вільний текст, у якому автор пише як заманеться. Тому тут не
розбір, а обережне впізнавання: беремо те, що видно напевно (посилання,
перший рядок, назва каналу), і НЕ вигадуємо решти.

Наслідок, названий чесно: вакансії з каналів приходять із меншою кількістю
ознак, ніж із майданчиків, і майже завжди потраплять у «потребує перегляду».
Це правильно — канал не повідомляє ані років, ані англійської, і вдавати,
що повідомляє, означало б давати впевненість, якої немає.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from app.sources.base import RawVacancy
from app.sources.rss import is_safe_link

KEY = "telegram"

#  Скільки повідомлень читати за прогін. Межа існує, щоб перший запуск на
#  великому каналі не викачав його історію цілком.
DEFAULT_LIMIT = 50

_URL = re.compile(r"https?://[^\s<>\"']+")
_COMPANY = re.compile(r"^\s*(?:компан[іи]я|company|роботодавець)\s*[:\-—]\s*(.+)$",
                      re.I | re.M)
_POSITION = re.compile(r"^\s*(?:вакансія|посада|position|role)\s*[:\-—]\s*(.+)$",
                       re.I | re.M)

#  Ознаки того, що повідомлення взагалі про вакансію. Канали публікують і
#  новини, і мемів, і оголошення про стажування — без фільтра в базу
#  потрапляло б усе підряд.
_LOOKS_LIKE_JOB = re.compile(
    r"вакансі|шука[ює]мо|hiring|we are looking|розробник|developer|engineer|"
    r"резюме|cv\b|відгук|apply|зарплат|salary|досвід|experience", re.I)


#  Рядок із самих хештегів — не назва вакансії. Канали майже завжди
#  починають саме з них («#Python #Middle #remote»), і перша редакція
#  брала «hiring» за посаду.
_ONLY_TAGS = re.compile(r"^(?:[#@][\w_]+[\s,]*)+$")


def _first_line(text: str) -> str:
    for line in (text or "").splitlines():
        raw = line.strip()
        if not raw or _ONLY_TAGS.match(raw):
            continue
        cleaned = re.sub(r"[#*_`]+", " ", raw).strip()
        if len(cleaned) > 3:
            return cleaned[:300]
    return ""


def parse_message(*, channel: str, message_id: int, text: str,
                  posted_at: datetime | None) -> RawVacancy | None:
    """Повідомлення каналу → вакансія, або `None`, якщо це не вакансія.

    `None` — звичайний стан: канали публікують не лише вакансії, і брати
    все підряд означало б засмітити перелік настільки, що ним перестануть
    користуватись.
    """
    body = (text or "").strip()
    if not body or not _LOOKS_LIKE_JOB.search(body):
        return None

    links = [u for u in _URL.findall(body) if is_safe_link(u)]
    # Посилання на саме повідомлення — запасний варіант: вакансію треба
    # мати куди відкрити, навіть якщо автор не дав зовнішньої адреси.
    url = links[0] if links else f"https://t.me/{channel.lstrip('@')}/{message_id}"

    company = _COMPANY.search(body)
    position = _POSITION.search(body)

    return RawVacancy(
        source_key=KEY,
        # Ідентифікатор обов'язково з назвою каналу: номери повідомлень
        # унікальні лише в межах каналу, і без префікса два канали
        # затирали б вакансії одне одного.
        external_id=f"{channel.lstrip('@')}:{message_id}",
        url=url,
        title=(position.group(1).strip()[:300] if position else _first_line(body)),
        company=(company.group(1).strip()[:200] if company
                 else f"@{channel.lstrip('@')}"),
        raw_text=body,
        posted_at=posted_at,
        payload={
            "facts": [],            # канал ознак не повідомляє — і це видно
            "tags": [],
            "replies": None,
            "views": None,
            "salary_tier": None,
            "channel": channel,
            "links": links[:5],
        },
    )


# ─────────────────────────────── мережа ───────────────────────────────

import logging  # noqa: E402

from telethon import TelegramClient  # noqa: E402

from app.config import get_settings  # noqa: E402

log = logging.getLogger("jobtrack.telegram")


class TelegramSource:
    """Адаптер одного каналу.

    `params`:
        channel — назва каналу, з «@» або без.
        limit   — скільки останніх повідомлень читати за прогін.

    Один канал — один запис у `source`. Десяток каналів означає десяток
    записів із тим самим `kind`, і жодної зміни в коді: саме так було
    задумано з першого дня.
    """

    def __init__(self, key: str = KEY, params: dict | None = None) -> None:
        self.key = key
        params = params or {}
        self.channel = str(params.get("channel") or "").lstrip("@")
        self.limit = max(1, min(int(params.get("limit", DEFAULT_LIMIT)), 200))

    async def fetch(self) -> list[RawVacancy]:
        cfg = get_settings()
        if not cfg.telegram_api_id or not cfg.telegram_api_hash:
            raise RuntimeError(
                "TELEGRAM_API_ID / TELEGRAM_API_HASH не задані — канал читати нічим")
        if not self.channel:
            raise RuntimeError(f"канал {self.key}: не вказано параметр `channel`")

        out: list[RawVacancy] = []
        client = TelegramClient(cfg.telegram_session,
                                cfg.telegram_api_id, cfg.telegram_api_hash)
        await client.connect()
        try:
            if not await client.is_user_authorized():
                # Вхід інтерактивний і робиться ОДИН раз окремою командою.
                # Робити його всередині збору не можна: прогін за розкладом
                # не має де запитати код підтвердження і просто завис би.
                raise RuntimeError(
                    "сесію Telegram не створено — виконайте "
                    "`docker compose exec api python -m app.scripts_tg_login`")

            async for message in client.iter_messages(self.channel, limit=self.limit):
                vacancy = parse_message(
                    channel=self.channel, message_id=message.id,
                    text=message.message or "",
                    posted_at=(message.date.astimezone(timezone.utc)
                               if message.date else None),
                )
                if vacancy:
                    out.append(vacancy)
        finally:
            await client.disconnect()

        log.info("канал @%s: повідомлень прочитано до %d, вакансій %d",
                 self.channel, self.limit, len(out))
        return out
