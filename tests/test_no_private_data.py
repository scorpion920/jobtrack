"""Сторож проти персональних даних у публічному репозиторії.

Рішення зробити проєкт публічним дає жорстке обмеження: у git не може бути
ні контактів, ні тексту резюме, ні збережених куків. Це не лише вимога
безпеки — воно робить проєкт КРАЩИМ портфоліо: виходить узагальнений
інструмент, а не «резюме Сергія», і він працює в будь-кого після
`docker compose up`.

Перевірка механічна навмисно. Домовленість «не комітити зайвого» тримається
рівно доти, доки про неї пам'ятають, а файл із контактами додають не зі злого
наміру, а поспіхом.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

#  Зразки персональних даних. Перелік описує КЛАС, а не конкретну людину:
#  той самий сторож має спрацювати і в наступного власника форка.
PATTERNS = {
    "телефон": re.compile(r"\+?380\d{9}|\+?\d{1,3}[\s-]?\(?\d{2,3}\)?[\s-]?\d{3}[\s-]?\d{2}[\s-]?\d{2}\b"),
    "особиста пошта": re.compile(r"[\w.+-]+@(?:gmail|ukr|yahoo|outlook|icloud|proton)\.[a-z]{2,}", re.I),
    # Нік шукаємо в КОНТЕКСТІ, а не за самим символом @: перша редакція
    # ловила кожен `@dataclass` і `@property`. Сторож, що кричить на
    # декоратори, вимикають у перший же день — а з ним зникає й перевірка,
    # заради якої він писався.
    "телеграм-нік": re.compile(
        r"(?:t\.me/|telegram\s*[:：]\s*@?)([a-z_][\w_]{4,31})", re.I),
}

#  Де шукати не треба: приклад конфігурації пояснює формат, фікстури — це
#  публічні оголошення вакансій як вони є на майданчику.
SKIP = {".env.example"}
SKIP_DIRS = {"tests/fixtures"}


def _tracked_files() -> list[Path]:
    out = subprocess.run(["git", "ls-files"], cwd=ROOT,
                         capture_output=True, text=True, check=True)
    return [ROOT / line for line in out.stdout.splitlines() if line]


def test_no_personal_data_in_tracked_files():
    offenders: list[str] = []

    for path in _tracked_files():
        rel = path.relative_to(ROOT).as_posix()
        if rel in SKIP or any(rel.startswith(d) for d in SKIP_DIRS):
            continue
        if not path.exists() or path.suffix in {".png", ".jpg", ".pdf", ".ico"}:
            continue

        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue

        for name, pattern in PATTERNS.items():
            for found in pattern.findall(text):
                offenders.append(f"{rel}: {name} — {found}")

    assert not offenders, "персональні дані у git:\n" + "\n".join(offenders)


def test_env_is_not_tracked():
    """Сам файл із секретами не повинен потрапити в історію ніколи."""
    out = subprocess.run(["git", "ls-files", ".env"], cwd=ROOT,
                         capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "", ".env у git — токени стали публічними"


def test_gitignore_covers_the_private_set():
    ignored = (ROOT / ".gitignore").read_text(encoding="utf-8")
    for needed in (".env", "data/", "*.pdf"):
        assert needed in ignored, f"{needed} не під ігнором"
