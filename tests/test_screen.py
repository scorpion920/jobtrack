"""Формальні перепони до подачі — три стани, а не два."""

from __future__ import annotations

from app.screen import Candidate, Profile, assess, find_alternative


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


def test_foreign_only_location_blocks():
    """Країна, де розглядають кандидатів, блокує подачу так само жорстко.

    Знайдено 08.10.2026 на вакансії N-iX 852170: Djinni не дав подати,
    бо компанія розглядає кандидатів із Польщі, а в профілі Україна.
    Дані для цієї перевірки система вже мала з першого збору
    (location='Польща') — бракувало самої перевірки, і вакансія стояла
    в переліку як придатна.
    """
    v = assess(format="remote", years_required=1, english="b2", location="Польща")
    assert v.blocked and "Польща" in v.reason


def test_ukraine_among_countries_is_fine():
    for loc in ("Україна", "Україна (Київ)", "Країни Європи та Україна"):
        assert assess(format="remote", years_required=1, english="b2",
                      location=loc).state == "ok", loc


def test_city_names_are_not_treated_as_foreign_countries():
    """DOU кладе в локацію МІСТА офісів, Djinni — країни кандидатів.

    Блокувати за назвою міста не можна: «Київ, Львів» перетворилося б на
    перепону там, де її немає.
    """
    for loc in ("Київ, Львів", "Дніпро", "за кордоном", None):
        assert not assess(format="remote", years_required=1, english="b2",
                          location=loc).blocked, loc


def _c(url, company="n ix", title="junior data engineer 6 month engagement",
       blocked=False):
    return Candidate(url=url, company_norm=company, title_norm=title, blocked=blocked)


def test_alternative_is_found_despite_suffix_in_title():
    """Варіанти однієї посади різняться суфіксом «(#5893)»."""
    blocked = _c("https://x/852170", blocked=True)
    ok = _c("https://x/851766", title="junior data engineer 6 month engagement 5893")
    assert find_alternative(blocked, [blocked, ok]) == "https://x/851766"


def test_no_alternative_when_the_other_variant_is_also_blocked():
    """Випадок N-iX, перевірений 08.10.2026.

    Польський варіант не бере кандидатів з України, український вимагає
    5 років замість 1. Обидва недоступні, і функція правильно НЕ пропонує
    нічого. Саме цю тишу легко прийняти за поломку й «полагодити»,
    зробивши підказку хибною.
    """
    a = _c("https://x/852170", blocked=True)
    b = _c("https://x/851766", title="junior data engineer 6 month engagement 5893",
           blocked=True)
    assert find_alternative(a, [a, b]) is None


def test_other_company_is_not_an_alternative():
    a = _c("https://x/1", blocked=True)
    b = _c("https://x/2", company="інша компанія")
    assert find_alternative(a, [a, b]) is None


def test_short_title_does_not_match_by_prefix():
    """«qa» всередині «qa automation engineer» — не та сама посада."""
    a = _c("https://x/1", title="qa", blocked=True)
    b = _c("https://x/2", title="qa automation engineer")
    assert find_alternative(a, [a, b]) is None


def test_suitable_vacancy_gets_no_alternative():
    a = _c("https://x/1")
    b = _c("https://x/2", title="junior data engineer 6 month engagement 5893")
    assert find_alternative(a, [a, b]) is None


def test_hybrid_does_not_satisfy_remote_only():
    """Гібрид — теж присутність в офісі, просто рідша.

    Знайдено на Intellica Consulting 08.10.2026: «Гібридний формат роботи»
    проходив як придатний, бо блокувався лише явний «Тільки офіс». Умова
    власника «тільки віддалено» незмінна з 08.10.2026.
    """
    v = assess(format="hybrid", years_required=1, english="b1")
    assert v.blocked and v.reason == "гібридний формат"


def test_remote_still_passes():
    assert assess(format="remote", years_required=1, english="b1").state == "ok"
