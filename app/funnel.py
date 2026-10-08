"""Воронка — головна (і спочатку єдина) аналітична поверхня системи.

Вона існує заради одного питання: подачі не переглядають, чи переглядають і не
відповідають? Перше означає, що винна воронка — вилка, стаж у профілі, ключові
слова, вибір вакансій. Друге означає, що винен сам документ. Доти, доки це
число невідоме, будь-яка переробка резюме — здогад.
"""

from __future__ import annotations

from collections.abc import Iterable

from app.models import Application, Status
from app.schemas import FunnelRow

#  Стани, досягнення яких означає, що рекрутер ПОБАЧИВ подачу. Відмова теж сюди
#  належить: щоб відмовити, треба спершу прочитати.
SEEN = {Status.viewed, Status.rejected, Status.invited,
        Status.interview, Status.test_task, Status.offer}
RESPONDED = {Status.rejected, Status.invited, Status.interview,
             Status.test_task, Status.offer}
INTERVIEW = {Status.interview, Status.test_task, Status.offer}


def build(applications: Iterable[Application], key: str = "channel") -> list[FunnelRow]:
    """Зводить подачі у рядки воронки.

    `key` — за чим різати: "channel", "cv_version" або "week". Порівняння
    каналів і версій резюме між собою і є тим, заради чого ведеться журнал.
    """
    buckets: dict[str, dict[str, int]] = {}

    for app in applications:
        bucket = _bucket(app, key)
        row = buckets.setdefault(
            bucket, {"sent": 0, "viewed": 0, "responded": 0, "interview": 0, "offer": 0}
        )
        reached = {e.status for e in app.events}

        row["sent"] += 1
        if reached & SEEN:
            row["viewed"] += 1
        if reached & RESPONDED:
            row["responded"] += 1
        if reached & INTERVIEW:
            row["interview"] += 1
        if Status.offer in reached:
            row["offer"] += 1

    return [FunnelRow(bucket=b, **v) for b, v in sorted(buckets.items())]


def _bucket(app: Application, key: str) -> str:
    if key == "channel":
        return app.channel.value
    if key == "cv_version":
        return app.cv_version or "— не вказано —"
    if key == "week":
        iso = app.applied_on.isocalendar()
        return f"{iso.year}-W{iso.week:02d}"
    raise ValueError(f"невідомий зріз: {key}")
