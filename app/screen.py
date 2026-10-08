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
    blocked: bool
    reason: str = ""


def assess(*, format: str | None, years_required: int | None, english: str | None,
           profile: Profile = DEFAULT_PROFILE) -> Verdict:
    reasons: list[str] = []

    if profile.remote_only and format == "office":
        reasons.append("тільки офіс")

    if years_required is not None and years_required > profile.years:
        # Саме цей пункт і блокує кнопку на майданчику — тому він перший
        # серед причин не витрачати час на супровідний лист.
        reasons.append(f"потрібно {years_required} р. досвіду")

    level = ENGLISH_LEVELS.get(english or "", None)
    if level is not None and level > profile.english_level:
        reasons.append(f"англійська {english.upper()}")

    return Verdict(blocked=bool(reasons), reason=", ".join(reasons))
