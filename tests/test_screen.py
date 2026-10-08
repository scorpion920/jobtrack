"""Формальні перепони до подачі — три стани, а не два."""

from __future__ import annotations

from app.screen import Profile, assess


def test_everything_known_and_suitable():
    v = assess(format="remote", years_required=1, english="b1")
    assert v.state == "ok" and not v.blocked and v.unchecked == ()


def test_office_is_blocked_for_remote_only_profile():
    assert assess(format="office", years_required=1, english="b1").state == "blocked"


def test_years_threshold_is_the_first_reason():
    """Саме поріг років робить кнопку подачі неактивною на майданчику."""
    v = assess(format="remote", years_required=3, english="b1")
    assert v.blocked and v.reason.startswith("потрібно 3")


def test_english_above_profile_blocks():
    v = assess(format="remote", years_required=1, english="c1")
    assert v.blocked and "C1" in v.reason


def test_english_not_required_is_not_a_blocker():
    assert assess(format="remote", years_required=1, english="none").state == "ok"


def test_channel_that_reports_nothing_yields_unchecked_not_ok():
    """DOU не повідомляє років і англійської.

    Якби такі вакансії зараховувались до придатних, перелік із 87 рядків
    показував би 80 придатних, з яких більшість не перевірена взагалі.
    """
    v = assess(format="remote", years_required=None, english=None)
    assert v.state == "unchecked"
    assert not v.blocked
    assert v.unchecked == ("роки", "англійська")


def test_missing_format_is_unchecked_not_suitable():
    """Precoro у переліку без мітки формату, а насправді офіс."""
    v = assess(format=None, years_required=1, english="b1")
    assert v.state == "unchecked" and "формат" in v.unchecked


def test_blocked_wins_over_unchecked():
    """Відома перепона важливіша за невідомі ознаки."""
    v = assess(format="office", years_required=None, english=None)
    assert v.state == "blocked"


def test_profile_is_a_parameter_not_a_constant():
    strict = Profile(years=5, english="c1", remote_only=False)
    assert assess(format="office", years_required=3, english="c1",
                  profile=strict).state == "ok"
