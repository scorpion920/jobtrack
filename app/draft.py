"""Підготовка подачі: який трек резюме брати і про що писати.

Те, що за вечір 08.10.2026 робилося руками по шість разів. Кожного разу
послідовність була та сама: прочитати вакансію, вирішити, який варіант
резюме ближчий, вибрати мову листа, виписати збіги й назвати прогалину.
Три з цих чотирьох кроків механічні.

Четвертий — сам текст листа — лишається людині. Система дає каркас із
перевірених фактів; перетворити його на звернення до конкретної компанії
без розуміння, чому саме туди, неможливо, і підробляти це не варто.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

#  Трек визначає НАЗВА ПОСАДИ, а не збіги в тексті.
#
#  Перша редакція рахувала збіги — і помилилась рівно там, де рішення вже
#  були ухвалені руками 08.10.2026: INSART («ML Engineer/Data Scientist»)
#  і CrewRed («Junior Python Full-Stack Developer») обидві отримали ai-llm,
#  бо згадують LLM в обов'язках і в бонусах відповідно. Але одна згадка LLM
#  не робить вакансію LLM-вакансією: у першій ядро — класичний ML, у другій
#  LLM узагалі в «extra points».
#
#  Той самий урок, що з професією: назва називає СУТЬ, текст містить
#  ІНСТРУМЕНТИ, і плутати їх — найкоротший шлях надіслати не те резюме.
_AI_TITLE = re.compile(r"\b(ai|llm|genai|prompt)\b|generative", re.I)
_ML_TITLE = re.compile(r"\bml\b|machine learning|data scientist|data engineer|"
                       r"data analyst|mlops|computer vision|\bnlp\b", re.I)

#  Збіги лишаються ДОПОМІЖНИМИ: вони розрізняють ai-llm і data-ml там, де
#  назва каже обидва («AI/ML Engineer»).
_AI_SIGNS = {"LLM / агенти", "RAG / embeddings"}
_ML_SIGNS = {"прогнозування часових рядів", "градієнтний бустинг",
             "детекція аномалій", "feature engineering", "pandas / NumPy"}

TRACKS = {
    "ai-llm": "Pedchenko_Serhii_CV_ai-llm.pdf",
    "data-ml": "Pedchenko_Serhii_CV_data-ml.pdf",
    "backend": "Pedchenko_Serhii_CV_backend.pdf",
}

_CYRILLIC = re.compile(r"[а-щьюяєіїґ]", re.I)
_LATIN = re.compile(r"[a-z]", re.I)


def detect_language(text: str) -> str:
    """`uk` або `en` — якою мовою писати лист.

    Питання не стилістичне. CrewRed 08.10.2026 має англійський опис і
    англійські питання рекрутера; український лист там програв би на
    першому погляді. Зворотне теж правда: англійський лист українській
    компанії виглядає як масова розсилка.

    Рахуємо частку кирилиці в ТІЛІ оголошення. Окремі англійські назви
    технологій є в будь-якому українському тексті, тому поріг не на нулі.
    """
    body = text or ""
    cyrillic = len(_CYRILLIC.findall(body))
    latin = len(_LATIN.findall(body))
    if cyrillic + latin == 0:
        return "uk"
    return "uk" if cyrillic / (cyrillic + latin) > 0.2 else "en"


def pick_track(title: str, matched: list[str]) -> str:
    """Який варіант резюме ближчий до вакансії.

    Вирішує назва посади. Збіги в тексті лише розрізняють ai-llm і data-ml
    там, де назва каже обидва — «Senior AI/ML Engineer».
    """
    found = set(matched)
    ai_in_title = bool(_AI_TITLE.search(title or ""))
    ml_in_title = bool(_ML_TITLE.search(title or ""))

    if ai_in_title and ml_in_title:
        # «AI/ML Engineer» — дивимось, чого в тексті більше.
        return "ai-llm" if len(found & _AI_SIGNS) > len(found & _ML_SIGNS) else "data-ml"
    if ai_in_title:
        return "ai-llm"
    if ml_in_title:
        return "data-ml"
    return "backend"


@dataclass
class Draft:
    """Чернетка подачі."""

    track: str
    cv_file: str
    language: str
    strengths: list[str] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def prepare(*, title: str, raw_text: str, matched: list[str], gaps: list[str],
            replies: int | None = None, english: str | None = None) -> Draft:
    """Зібрати все, що потрібне перед написанням листа."""
    track = pick_track(title, matched)
    language = detect_language(raw_text)

    notes: list[str] = []
    if language == "en":
        notes.append("Опис англійською — лист і резюме теж англійською")
    if replies is not None and replies > 150:
        notes.append(f"{replies} відгуків: лист має спрацювати з перших двох речень")
    elif replies is not None and replies < 20:
        notes.append(f"лише {replies} відгуків — подаватись сьогодні, не завтра")
    if english in {"c1", "c2"}:
        notes.append("вимога C1+ вища за профіль B2 — назвати прямо, не обходити")

    return Draft(track=track, cv_file=TRACKS[track], language=language,
                 strengths=list(matched), gaps=list(gaps), notes=notes)
