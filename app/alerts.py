"""Про що повідомляти і — головне — про що мовчати.

Сповіщення, яке приходить занадто часто, перестають читати; це той самий
збиток, що й від відсутності сповіщень, тільки непомітніший. Тому правила тут
складені так, щоб привід був рідкісним і дієвим.

Два приводи, і обидва перевірені практикою 08.10.2026:

1. **Нова придатна вакансія.** Office.kh.ua опублікував «Python Developer
   (Django)» вранці — і на момент перегляду вона мала ТРИ відгуки проти
   вісімдесяти на тій самій вакансії тижневої давнини. Години тут вирішують,
   а дізнатися про неї можна було тільки відкривши сторінку.

2. **Тиха подача.** Подача, на яку десять днів немає жодної реакції, — це
   сигнал оператору, а не системі. Але надсилати його можна ЛИШЕ для каналів,
   які взагалі повідомляють статуси: на DOU мовчання нічого не означає, і
   нагадування про нього було б шумом із самого початку.

Повтори гасить журнал `notification`: один привід — одне повідомлення
назавжди, незалежно від того, скільки разів прогін його побачить.
"""

from __future__ import annotations

import html
from dataclasses import dataclass
from datetime import date


def esc(value: str) -> str:
    """Екранувати те, що прийшло з чужого майданчика.

    Повідомлення надсилаються з `parse_mode=HTML`, і назва компанії потрапляє
    в розмітку. Telegram вимагає екранування `<`, `>` і `&`; без нього
    вакансія «Senior AI/ML Engineer (Python, LLM &amp; RAG)» дала б 400 Bad
    Request — тобто сповіщення просто не дійшло б, і причина виглядала б як
    збій мережі.

    Перевірено на зібраних даних 08.10.2026: такі назви там уже є (Xenoss,
    DOIT Software), тож це не теоретичний випадок.
    """
    return html.escape(value or "", quote=False)


@dataclass(frozen=True)
class Alert:
    """Привід повідомити.

    `key` — те, за чим гаситься повтор. Він мусить описувати ПРИВІД, а не
    момент: ключ із датою всередині слав би те саме щодня.
    """

    key: str
    text: str


@dataclass(frozen=True)
class VacancyBrief:
    """Вакансія у вигляді, якого достатньо для рішення про сповіщення."""

    id: int
    url: str
    company: str
    title: str
    source_key: str
    state: str                   # ok | unchecked | blocked
    fit: str                     # strong | possible | weak
    replies: int | None = None
    posted_on: date | None = None


@dataclass(frozen=True)
class ApplicationBrief:
    id: int
    company: str
    position: str
    channel: str
    days_silent: int | None      # None — канал статусів не повідомляє
    current_status: str


def vacancy_alerts(vacancies: list[VacancyBrief]) -> list[Alert]:
    """Нові вакансії, варті уваги просто зараз.

    Поріг свідомо вузький: тільки ті, що проходять формальні умови І мають
    змістовний збіг. Вакансія «потребує перегляду» в сповіщення не йде —
    інакше DOU, який не повідомляє ані років, ані англійської, заповнив би
    канал повідомленнями, які нічого не вирішують.
    """
    out: list[Alert] = []
    for v in vacancies:
        if v.state != "ok" or v.fit not in {"strong", "possible"}:
            continue
        competition = (f"{v.replies} відгуків" if v.replies is not None
                       else "відгуки не видно")
        out.append(Alert(
            key=f"vacancy:{v.id}",
            text=(f"<b>{esc(v.company)}</b> — {esc(v.title)}\n"
                  f"{competition} · {esc(v.source_key)}"
                  + (f" · {v.posted_on.strftime('%d.%m')}" if v.posted_on else "")
                  + f"\n{v.url}"),
        ))
    return out


def silence_alerts(applications: list[ApplicationBrief],
                   days: int = 10) -> list[Alert]:
    """Подачі, які мовчать довше за норму.

    `days_silent is None` означає «питання не має сенсу»: канал не повідомляє
    статусів узагалі. Такі подачі пропускаємо — нагадування про них було б
    шумом, що не веде до жодної дії.
    """
    out: list[Alert] = []
    for app in applications:
        if app.days_silent is None or app.days_silent < days:
            continue
        if app.current_status in {"rejected", "offer", "withdrawn", "ghosted"}:
            continue
        out.append(Alert(
            key=f"silence:{app.id}:{app.days_silent // days}",
            text=(f"Тиша {app.days_silent} днів: <b>{esc(app.company)}</b> — "
                  f"{esc(app.position)} ({esc(app.channel)})"),
        ))
    return out


def unsent(alerts: list[Alert], already: set[str]) -> list[Alert]:
    """Відкинути те, що вже надсилалось.

    Окремою функцією, щоб гасіння повторів можна було перевірити без БД —
    саме тут найлегше помилитись і слати те саме щодня.
    """
    return [a for a in alerts if a.key not in already]
