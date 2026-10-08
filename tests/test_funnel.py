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


class TestAutoReplyIsNotEvidence:
    """Автовідповідь не є доказом того, що подачу переглянула людина.

    Знайдено 08.10 на першій же подачі: відповідь за три хвилини з позначкою
    Djinni «Це автоматична відповідь». Якби збирач зараховував такі як
    «переглянуто», воронка показувала б перегляди там, де їх не було — і
    єдине число, заради якого ведеться журнал, стало б неправдивим.

    Механізм не випадковий: з жовтня 2024 Djinni не дає перепублікувати
    вакансію, не розібравши непрочитані відгуки, тож масова автоматична
    відмова теж іде в їхню статистику як відповідь.
    """

    def test_sent_without_events_is_not_seen(self):
        rows = build([make()])
        assert rows[0].viewed == 0

    def test_explicit_rejection_still_counts_as_seen(self):
        """Межа: відмова, написана людиною, доказом лишається."""
        rows = build([make(Channel.djinni, "backend", date(2026, 10, 1), Status.rejected)])
        assert rows[0].viewed == 1

    def test_collector_has_auto_reply_guard(self):
        """Сторож проти повернення вади: правило живе в collect.js."""
        from pathlib import Path
        js = (Path(__file__).resolve().parent.parent / "app" / "static"
              / "collect.js").read_text(encoding="utf-8")
        assert "автоматична відповідь" in js, "збирач не розпізнає автовідповіді"
        assert "AUTO.test(blob)" in js, "перевірка AUTO не застосовується"


class TestAutoReplyIsItsOwnState:
    """Автовідповідь — окремий стан, видимий у журналі й НЕ зарахований у воронці.

    Два простіші рішення обидва були гіршими:
      • зарахувати як «переглянуто» — воронка рахувала б роботів як людей, і
        зробила б це непомітно, бо число виросло б, а не впало;
      • лишити «надіслано» — подія сталася, а журнал показує, ніби нічого.
    """

    DAY = date(2026, 10, 8)

    def test_auto_reply_is_not_a_view(self):
        rows = build([make(Channel.djinni, "backend", self.DAY, Status.auto_reply)])
        assert rows[0].viewed == 0, "автовідповідь не доводить, що хтось дивився"
        assert rows[0].responded == 0

    def test_auto_reply_still_counts_as_sent(self):
        rows = build([make(Channel.djinni, "backend", self.DAY, Status.auto_reply)])
        assert rows[0].sent == 1

    def test_auto_reply_is_visible_as_current_state(self):
        """У журналі подача має показувати, що реакція була — хай і машинна."""
        from app.models import Application, ApplicationEvent
        app = Application(company="X", position="Y", channel=Channel.djinni,
                          applied_on=self.DAY)
        app.events = [
            ApplicationEvent(id=1, status=Status.sent, occurred_on=self.DAY, application_id=0),
            ApplicationEvent(id=2, status=Status.auto_reply, occurred_on=self.DAY, application_id=0),
        ]
        assert app.current_status is Status.auto_reply

    def test_real_reply_beats_auto_reply_on_the_same_day(self):
        from app.models import Application, ApplicationEvent
        app = Application(company="X", position="Y", channel=Channel.djinni,
                          applied_on=self.DAY)
        app.events = [
            ApplicationEvent(id=1, status=Status.viewed, occurred_on=self.DAY, application_id=0),
            ApplicationEvent(id=2, status=Status.auto_reply, occurred_on=self.DAY, application_id=0),
        ]
        assert app.current_status is Status.viewed
