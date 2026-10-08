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
    """Вакансія у вигляді, якого достатньо для РІШЕННЯ, а не лише для згадки.

    Склад полів продиктований питанням, на яке оператор відповідає, читаючи
    сповіщення: подаватись зараз чи ні. Для цього треба бачити умови
    (формат, роки, англійська), конкуренцію і — головне — чим вакансія
    збігається з профілем. Повідомлення, після якого однаково треба
    відкривати сторінку, не економить нічого.
    """

    id: int
    url: str
    company: str
    title: str
    source_key: str
    state: str                   # ok | unchecked | blocked
    fit: str                     # strong | possible | weak
    replies: int | None = None
    posted_on: date | None = None

    # Умови, за якими подачу або дадуть, або ні.
    format: str | None = None
    years_required: int | None = None
    english: str | None = None
    location: str | None = None

    # Чим збігається і чого бракує — те, заради чого сповіщення й читають.
    matched: tuple[str, ...] = ()
    gaps: tuple[str, ...] = ()


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
        out.append(Alert(key=f"vacancy:{v.id}", text=describe(v)))
    return out


#  Умовні позначки. Один символ на початку рядка дає змогу відрізнити
#  сильний збіг від імовірного, не читаючи тексту, — а саме так сповіщення
#  і проглядають: швидко і в черзі з іншими.
_MARK = {"strong": "🟢", "possible": "🟡"}

_ENGLISH_NOT_NEEDED = "не потрібна"


def describe(v: VacancyBrief) -> str:
    """Текст, після якого не треба відкривати сторінку, щоб вирішити.

    Порядок рядків — за тим, у якому їх читають: спершу що це, далі чи
    візьмуть, потім наскільки людно, і аж тоді чим цікаво.
    """
    head = f"{_MARK.get(v.fit, '•')} <b>{esc(v.company)}</b> — {esc(v.title)}"

    terms: list[str] = []
    if v.format:
        # Екрануємо і тут: невідомий формат підставляється як є, а значення
        # походить із тексту майданчика. Перевірено 08.10.2026 — тлумач ознак
        # пропускає розмітку наскрізь: «Англійська - <b>X</b>» дає
        # english='<b>x</b>'. Жодне поле, що прийшло ззовні, не є винятком.
        terms.append(esc({"remote": "віддалено", "office": "офіс",
                          "hybrid": "гібрид"}.get(v.format, v.format)))
    if v.years_required is not None:
        terms.append(f"{v.years_required} р. досвіду")
    if v.english:
        terms.append("англ. " + (_ENGLISH_NOT_NEEDED if v.english == "none"
                                 else esc(v.english.upper())))
    if v.location:
        terms.append(esc(v.location))

    # «Відгуки не видно» і «нуль відгуків» — різні речі, і плутати їх не
    # можна: DOU конкуренції не повідомляє взагалі.
    competition = (f"{v.replies} відгуків" if v.replies is not None
                   else "відгуки не видно")
    source = f"{competition} · {esc(v.source_key)}"
    if v.posted_on:
        source += f" · {v.posted_on.strftime('%d.%m')}"

    lines = [head]
    if terms:
        lines.append(" · ".join(terms))
    lines.append(source)

    if v.matched:
        shown = ", ".join(esc(m) for m in v.matched[:5])
        more = len(v.matched) - 5
        lines.append(f"\n<b>Збіг:</b> {shown}" + (f" +{more}" if more > 0 else ""))
    if v.gaps:
        # Прогалина подається з заміною, а не голим фактом: саме так її
        # доведеться називати в супровідному листі.
        lines.append(f"<b>Бракує:</b> {esc(v.gaps[0])}")

    lines.append(f"\n{esc(v.url)}")
    return "\n".join(lines)


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


#  ─────────────────────────── зведене повідомлення ───────────────────────────
#
#  Шість окремих карток за один прогін — шість сповіщень на телефоні, і з
#  третього їх гортають не читаючи. Зведення дає ту саму інформацію одним
#  дотиком уваги, а кнопки лишаються по рядку на вакансію, тож дія нікуди
#  не зникає.

def digest_text(items: list[VacancyBrief], total: int, applied: int) -> str:
    """Список вакансій одним повідомленням.

    Кожна позиція коротша за окрему картку: без неї не обійтися при шести
    вакансіях у телефоні. Лишилось те, без чого рішення не ухвалити —
    сила збігу, умови, конкуренція і три головні збіги.
    """
    head = (f"<b>Нових вакансій: {len(items)}</b>\n"
            f"Усього в переліку {total}, подано на {applied}.")
    blocks = [head]

    for n, v in enumerate(items, start=1):
        terms = []
        if v.format:
            terms.append({"remote": "віддалено", "office": "офіс",
                          "hybrid": "гібрид"}.get(v.format, esc(v.format)))
        if v.years_required is not None:
            terms.append(f"{v.years_required} р.")
        if v.english:
            terms.append(_ENGLISH_NOT_NEEDED if v.english == "none"
                         else esc(v.english.upper()))
        terms.append(f"{v.replies} відгуків" if v.replies is not None
                     else "відгуки не видно")

        line = (f"\n<b>{n}. {_MARK.get(v.fit, '•')} {esc(v.company)}</b> — "
                f"{esc(v.title)}\n{' · '.join(terms)}")
        if v.matched:
            shown = ", ".join(esc(m) for m in v.matched[:3])
            more = len(v.matched) - 3
            line += f"\n{shown}" + (f" +{more}" if more > 0 else "")
        line += f"\n{esc(v.url)}"
        blocks.append(line)

    return "\n".join(blocks)


def digest_keyboard(items: list[VacancyBrief]) -> dict:
    """Клавіатура: рядок на вакансію, номер збігається з номером у тексті.

    Номер у підписі обов'язковий — без нього при шести рядках однакових
    кнопок неможливо зрозуміти, яка до чого.
    """
    rows = []
    for n, v in enumerate(items, start=1):
        rows.append([
            {"text": f"{n} ✅ подав", "callback_data": f"applied:{v.id}"},
            {"text": f"{n} 🚫 нецікаво", "callback_data": f"skip:{v.id}"},
        ])
    return {"inline_keyboard": rows}
