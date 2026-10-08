"""Реєстр адаптерів.

Порядок тут значення НЕ має — на відміну від реєстру екстракторів у прогнозній
системі, де перемагає перший, чий `can_handle()` відповів «так». Причина
різниці проста: там файл приходить без імені каналу і його треба впізнати, а
тут канал названий у налаштуваннях прямо. Вгадувати нічого.

Додати канал — це рядок у цьому словнику плюс запис у таблиці `source`.
Ядро при цьому не змінюється: саме цього вимагав власник з першого дня.
"""

from __future__ import annotations

from typing import Callable

from app.sources.base import Source
from app.sources.djinni import DjinniSource

# kind → як зібрати адаптер із ключа та параметрів каналу.
BUILDERS: dict[str, Callable[[str, dict], Source]] = {
    "djinni": DjinniSource,
}


def build(kind: str, key: str, params: dict) -> Source:
    if kind not in BUILDERS:
        # Промах гучний: невідомий вид каналу — це помилка налаштування,
        # і мовчазне «нічого не зібрали» тут було б найгіршою реакцією.
        raise ValueError(
            f"невідомий вид каналу: {kind!r}. Відомі: {sorted(BUILDERS)}"
        )
    return BUILDERS[kind](key, params)
