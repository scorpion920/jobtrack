"""Тести похідних властивостей моделі."""

from __future__ import annotations

from datetime import date, timedelta

from app.models import Application, ApplicationEvent, Channel, Status


def _app(applied: date, events: list[tuple[Status, date]]) -> Application:
    app = Application(company="X", position="Y", channel=Channel.djinni, applied_on=applied)
    app.events = [ApplicationEvent(id=i, status=s, occurred_on=d, application_id=0)
                  for i, (s, d) in enumerate(events, start=1)]
    return app


def test_status_without_events_is_sent():
    assert _app(date(2026, 10, 1), []).current_status is Status.sent


def test_latest_event_wins_by_date():
    app = _app(date(2026, 10, 1), [(Status.sent, date(2026, 10, 1)),
                                   (Status.viewed, date(2026, 10, 5))])
    assert app.current_status is Status.viewed


def test_same_day_events_resolved_by_id():
    """Дві події однією датою — звичайна річ при синхронізації з браузера.
    Переможцем має бути пізніше ДОДАНА, інакше стан стрибатиме випадково."""
    app = _app(date(2026, 10, 1), [(Status.viewed, date(2026, 10, 5)),
                                   (Status.rejected, date(2026, 10, 5))])
    assert app.current_status is Status.rejected


def test_silence_counted_from_application_when_no_events():
    app = _app(date.today() - timedelta(days=7), [])
    assert app.days_silent == 7


def test_silence_counted_from_last_event():
    app = _app(date.today() - timedelta(days=30),
               [(Status.viewed, date.today() - timedelta(days=3))])
    assert app.days_silent == 3


class TestSameDayOrdering:
    """Дві події одним днем — звичайна річ: Djinni показує вік із точністю до
    місяця, тож «надіслано» і «відмовлено» отримують однакову дату.

    До 08.10 переможцем ставав запис із більшим id, тобто порядок вставки.
    У журналі це дало дві подачі зі станом «надіслано», хоча насправді там
    була відмова — журнал брехав саме там, де він найпотрібніший.
    """

    def test_rejection_beats_sent_on_the_same_day(self):
        app = _app(date(2026, 2, 8), [(Status.rejected, date(2026, 2, 8)),
                                      (Status.sent, date(2026, 2, 8))])
        assert app.current_status is Status.rejected

    def test_insertion_order_does_not_matter(self):
        a = _app(date(2026, 2, 8), [(Status.sent, date(2026, 2, 8)),
                                    (Status.rejected, date(2026, 2, 8))])
        b = _app(date(2026, 2, 8), [(Status.rejected, date(2026, 2, 8)),
                                    (Status.sent, date(2026, 2, 8))])
        assert a.current_status is b.current_status is Status.rejected

    def test_offer_beats_rejection_on_the_same_day(self):
        app = _app(date(2026, 2, 8), [(Status.rejected, date(2026, 2, 8)),
                                      (Status.offer, date(2026, 2, 8))])
        assert app.current_status is Status.offer

    def test_later_date_still_wins_over_more_advanced_status(self):
        """Шкала — лише для нічиєї за датою. Пізніша подія завжди сильніша:
        відмова через тиждень після запрошення скасовує запрошення."""
        app = _app(date(2026, 2, 1), [(Status.invited, date(2026, 2, 1)),
                                      (Status.rejected, date(2026, 2, 8))])
        assert app.current_status is Status.rejected

    def test_viewed_beats_sent_on_the_same_day(self):
        app = _app(date(2026, 2, 8), [(Status.viewed, date(2026, 2, 8)),
                                      (Status.sent, date(2026, 2, 8))])
        assert app.current_status is Status.viewed


class TestSilenceOnlyWhereChannelSpeaks:
    """Мовчання мусить означати одне й те саме скрізь, де його рахують.

    DOU не показує стану відгуку взагалі — лише факт подачі. До 08.10 журнал
    виводив для таких подач «29 днів тиші», і це читалося як ігнорування
    рекрутером, хоча механізму, який міг би щось повідомити, там просто немає.
    """

    def test_djinni_silence_is_counted(self):
        app = _app(date.today() - timedelta(days=10), [])
        app.channel = Channel.djinni
        assert app.days_silent == 10

    def test_dou_silence_is_not_counted(self):
        app = _app(date.today() - timedelta(days=29), [])
        app.channel = Channel.dou
        assert app.days_silent is None, "DOU статусів не звітує — тиша неінформативна"

    def test_dou_with_manual_feedback_starts_counting(self):
        """Якщо відповідь надійшла іншим шляхом і внесена руками — зворотний
        зв'язок звідкись є, і далі тишу вже має сенс рахувати."""
        app = _app(date.today() - timedelta(days=29),
                   [(Status.viewed, date.today() - timedelta(days=5))])
        app.channel = Channel.dou
        assert app.days_silent == 5

    def test_none_is_not_zero(self):
        """None означає «питання не має сенсу», а не «нуль днів».
        Сплутати їх — зіпсувати саме те число, заради якого ведеться журнал."""
        app = _app(date.today(), [])
        app.channel = Channel.dou
        assert app.days_silent is None
        app.channel = Channel.djinni
        assert app.days_silent == 0
