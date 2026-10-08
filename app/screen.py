"""Формальні перепони до подачі.

Це НЕ скринер відповідності — той приїде окремо разом із `match.py`. Тут лише
те, що робить подачу НЕМОЖЛИВОЮ або безглуздою, і перевірено на практиці:

* **поріг років** Djinni застосовує жорстко: якщо у профілі менше років, ніж
  вимагає вакансія, кнопка подачі неактивна. Виявлено 08.10.2026 на двох
  підготовлених листах, які не було куди надіслати;
* **формат** — незмінна умова власника (тільки віддалено), заявлена в профілі;
* **англійська** вище заявленого рівня — відмова на першій же розмові.

Відсутність ознаки НЕ є підставою блокувати. «Майданчик не повідомив» і
«не підходить» — різні стани, і зливати їх означало б ховати придатні
вакансії: Precoro у переліку стоїть без позначки формату, а насправді офіс,
тож перевіряти такі треба руками, а не викреслювати наосліп.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.vacancy_facts import ENGLISH_LEVELS

# Країни, згадка яких БЕЗ згадки України означає, що кандидатів звідси не
# розглядають. Перелік консервативний навмисно: у Djinni локація — це
# «країни, де розглядаємо кандидатів», а в DOU — міста офісів. Блокувати за
# самою лише назвою міста не можна, інакше «Київ, Львів» стало б перепоною.
_FOREIGN_ONLY = re.compile(
    r"польщ|німеччин|сша|велика британ|кіпр|португал|іспан|естон|чехі|"
    r"румун|болгар|грузі|казахстан|молдов|словач|литв|латві|угорщин|"
    r"нідерланд|канад|ізраїл|туреччин", re.I)
_UKRAINE = re.compile(r"україн", re.I)


@dataclass(frozen=True)
class Profile:
    """Незмінні умови. Переїде в БД разом зі скринером (E3)."""

    years: int = 1
    english: str = "b2"
    remote_only: bool = True
    country: str = "Україна"

    @property
    def english_level(self) -> int:
        return ENGLISH_LEVELS[self.english]


DEFAULT_PROFILE = Profile()


@dataclass(frozen=True)
class Verdict:
    """Три стани, а не два.

    «Перепон не знайдено» і «перевірити не було чим» — різні речі, і зливати
    їх означало б давати хибну впевненість. DOU не повідомляє ані років, ані
    рівня англійської: якби його вакансії потрапляли в «придатні» нарівні з
    перевіреними, перелік із 87 рядків показував би 80 придатних, з яких
    половина не перевірена взагалі.
    """

    blocked: bool
    reason: str = ""
    # Чого бракувало, щоб винести вердикт. Непорожній перелік означає
    # «відкрити й подивитись самому», а не «підходить».
    unchecked: tuple[str, ...] = ()

    @property
    def state(self) -> str:
        if self.blocked:
            return "blocked"
        return "unchecked" if self.unchecked else "ok"


def assess(*, format: str | None, years_required: int | None, english: str | None,
           location: str | None = None,
           profile: Profile = DEFAULT_PROFILE) -> Verdict:
    reasons: list[str] = []
    unchecked: list[str] = []

    if profile.remote_only and format == "office":
        reasons.append("тільки офіс")
    elif profile.remote_only and format is None:
        unchecked.append("формат")

    if years_required is not None and years_required > profile.years:
        # Саме цей пункт і блокує кнопку на майданчику — тому він перший
        # серед причин не витрачати час на супровідний лист.
        reasons.append(f"потрібно {years_required} р. досвіду")
    elif years_required is None:
        unchecked.append("роки")

    # Країна, де розглядають кандидатів. Djinni блокує подачу так само
    # жорстко, як і за порогом років — перевірено 08.10.2026 на вакансії
    # N-iX 852170 («Польща», у профілі Україна). Дані для цієї перевірки у
    # нас БУЛИ з першого збору; бракувало самої перевірки.
    if location and _FOREIGN_ONLY.search(location) and not _UKRAINE.search(location):
        reasons.append(f"кандидати з: {location}")

    level = ENGLISH_LEVELS.get(english or "", None)
    if level is not None and level > profile.english_level:
        reasons.append(f"англійська {english.upper()}")
    elif english is None:
        unchecked.append("англійська")

    return Verdict(blocked=bool(reasons), reason=", ".join(reasons),
                   unchecked=tuple(unchecked))


@dataclass(frozen=True)
class Candidate:
    """Мінімум, потрібний, щоб упізнати варіанти однієї вакансії."""

    url: str
    company_norm: str
    title_norm: str
    blocked: bool


def find_alternative(target: Candidate, others: list[Candidate]) -> str | None:
    """Доступний варіант тієї самої вакансії, якщо він є.

    Компанії публікують одну посаду кількома оголошеннями — під різні країни
    чи рівні. Коли одне заблоковане, а інше ні, показати друге корисніше за
    будь-яку підказку.

    Зіставлення нечітке навмисно: варіанти різняться суфіксом
    («Junior Data Engineer (6-Month Engagement)» проти того самого з
    «(#5893)»), і точний збіг нормалізованих назв їх не бачить.

    Перевірено на N-iX 08.10.2026, і перевірка виявилась важливішою за
    підказку: другий варіант там теж недоступний — польський не бере
    кандидатів з України, український вимагає 5 років замість 1. Функція
    правильно НЕ пропонує нічого. Саме цю різницю легко прийняти за поломку
    і «полагодити», зробивши підказку хибною.
    """
    if not target.blocked:
        return None

    for other in others:
        if other.blocked or other.url == target.url:
            continue
        if other.company_norm != target.company_norm:
            continue
        short, long = sorted((other.title_norm, target.title_norm), key=len)
        # Поріг довжини відсікає випадкові збіги на кшталт «qa» всередині
        # «qa automation engineer»: надто коротка назва не доводить, що це
        # та сама посада.
        if len(short) >= 15 and long.startswith(short):
            return other.url
    return None
