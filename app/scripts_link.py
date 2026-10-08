"""Разове зв'язування наявних подач із зібраними вакансіями.

Потрібне тому, що журнал подач існував раніше за збір вакансій: перші 34
записи заведено до того, як канали з'явилися. Надалі зв'язок ставиться при
створенні, і цей скрипт лишається як інструмент відновлення.

Запуск:  docker compose exec api python -m app.scripts_link
"""

from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.db import get_sessionmaker
from app.linking import link
from app.models import Application, Vacancy


async def main() -> None:
    async with get_sessionmaker()() as session:
        apps = [(a.id, a.url) for a in
                (await session.execute(select(Application))).scalars()]
        vacancies = [(v.id, v.source_key, v.external_id) for v in
                     (await session.execute(select(Vacancy))).scalars()]

        pairs = link(apps, vacancies)
        by_id = {a.id: a for a in
                 (await session.execute(select(Application))).scalars()}

        changed = 0
        for app_id, vacancy_id in pairs.items():
            app = by_id[app_id]
            if app.vacancy_id != vacancy_id:
                app.vacancy_id, changed = vacancy_id, changed + 1

        await session.commit()
        print(f"подач усього: {len(apps)}")
        print(f"зв'язано: {len(pairs)} (змінено цим запуском: {changed})")
        print(f"без зв'язку: {len(apps) - len(pairs)} — подачі поштою, з "
              f"LinkedIn або на вакансії, яких збір ще не бачив")


if __name__ == "__main__":
    asyncio.run(main())
