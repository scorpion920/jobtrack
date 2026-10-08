"""Одноразове прибирання: ім'я рекрутера, що потрапило в назву компанії.

Перший прогін збирача 08.10 записав «Insiders · Khrystyna» як назву компанії —
посилання на Djinni містить і те, і те. Збирач виправлено, але вже записані
рядки він не перепише: зіставлення йде за URL і назву не чіпає (і правильно,
бо мовчки правити наявні дані небезпечніше за неточність у них).

Запуск: docker compose exec api python -m app.scripts_cleanup
"""

from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.db import get_sessionmaker
from app.models import Application


async def main() -> None:
    async with get_sessionmaker()() as session:
        rows = list((await session.execute(select(Application))).scalars())
        fixed = 0
        for row in rows:
            if "·" not in row.company:
                continue
            clean = row.company.split("·")[0].strip()
            if clean and clean != row.company:
                print(f"  {row.company!r} → {clean!r}")
                row.company = clean
                fixed += 1
        await session.commit()
        print(f"виправлено назв: {fixed} із {len(rows)}")


if __name__ == "__main__":
    asyncio.run(main())
