"""Тести воронки — чиста логіка, без БД і без мережі.

Головне, що тут перевіряється: відмова НЕ стирає факту перегляду. Якби воронка
рахувала поточний стан, а не досягнуті, то кожна відмова зменшувала б лічильник
переглядів — і відповіді на головне питання («чи доходить резюме до людини»)
не було б узагалі.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.funnel import build
from app.models import Application, ApplicationEvent, Channel, Status


def make(channel=Channel.djinni, cv="backend", day=date(2026, 10, 1), *statuses):
    app = Application(company="X", position="Y", channel=channel,
                      applied_on=day, cv_version=cv)
    app.events = [
        ApplicationEvent(id=i, status=s, occurred_on=day, application_id=0)
        for i, s in enumerate([Status.sent, *statuses], start=1)
    ]
    return app


def test_sent_only_counts_as_sent():
    rows = build([make()])
    assert (rows[0].sent, rows[0].viewed, rows[0].responded) == (1, 0, 0)


def test_rejection_still_counts_as_viewed():
    """Щоб відмовити, рекрутер спершу читає. Відмова — це доказ перегляду."""
    rows = build([make(Channel.djinni, "backend", date(2026, 10, 1), Status.rejected)])
    assert rows[0].viewed == 1
    assert rows[0].responded == 1


def test_viewed_without_answer_is_not_a_response():
    rows = build([make(Channel.djinni, "backend", date(2026, 10, 1), Status.viewed)])
    assert (rows[0].viewed, rows[0].responded) == (1, 0)


def test_ghosted_does_not_count_as_seen():
    """Мовчанка — не перегляд. Інакше найчастіший результат виглядав би успіхом."""
    rows = build([make(Channel.djinni, "backend", date(2026, 10, 1), Status.ghosted)])
    assert rows[0].viewed == 0


def test_offer_propagates_up_the_funnel():
    rows = build([make(Channel.djinni, "backend", date(2026, 10, 1),
                       Status.viewed, Status.interview, Status.offer)])
    r = rows[0]
    assert (r.sent, r.viewed, r.responded, r.interview, r.offer) == (1, 1, 1, 1, 1)


def test_rates_are_percentages():
    apps = [make(Channel.djinni, "backend", date(2026, 10, 1), Status.viewed),
            make(), make(), make()]
    rows = build(apps)
    assert rows[0].sent == 4
    assert rows[0].view_rate == 25.0


def test_split_by_cv_version():
    apps = [make(Channel.djinni, "backend", date(2026, 10, 1), Status.viewed),
            make(Channel.djinni, "ai-llm", date(2026, 10, 1))]
    rows = build(apps, key="cv_version")
    by = {r.bucket: r for r in rows}
    assert by["backend"].viewed == 1
    assert by["ai-llm"].viewed == 0


def test_split_by_week_uses_iso():
    rows = build([make(Channel.djinni, "backend", date(2026, 10, 8))], key="week")
    assert rows[0].bucket == "2026-W41"


def test_missing_cv_version_is_labelled_not_dropped():
    """Подачі без зазначеної версії не повинні зникати зі статистики —
    саме вони й становлять більшість у старих записах."""
    app = make()
    app.cv_version = None
    rows = build([app], key="cv_version")
    assert rows[0].sent == 1
    assert "не вказано" in rows[0].bucket


def test_unknown_split_fails_loudly():
    with pytest.raises(ValueError):
        build([make()], key="щось-вигадане")
