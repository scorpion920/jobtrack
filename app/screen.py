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

from dataclasses import dataclass

from app.vacancy_facts import ENGLISH_LEVELS


@dataclass(frozen=True)
class Profile:
    """Незмінні умови. Переїде в БД разом зі скринером (E3)."""

    years: int = 1
    english: str = "b2"
    remote_only: bool = True

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

    level = ENGLISH_LEVELS.get(english or "", None)
    if level is not None and level > profile.english_level:
        reasons.append(f"англійська {english.upper()}")
    elif english is None:
        unchecked.append("англійська")

    return Verdict(blocked=bool(reasons), reason=", ".join(reasons),
                   unchecked=tuple(unchecked))
