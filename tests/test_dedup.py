"""Перевипуски — та сама вакансія, опублікована майданчиком удруге."""

from __future__ import annotations

from datetime import datetime

from app.dedup import Publication, find_reposts


def _p(url, source="djinni", company="office kh ua",
       title="python developer django", posted=None):
    return Publication(url=url, source_key=source, company_norm=company,
                       title_norm=title, posted_at=posted)


def test_older_publication_points_to_the_newer_one():
    """Office.kh.ua, помічено оператором 08.10.2026: та сама вакансія стоїть
    двічі — 27.09 з 80 відгуками і 08.10 з трьома."""
    old = _p("u1", posted=datetime(2026, 9, 27))
    new = _p("u2", posted=datetime(2026, 10, 8))
    assert find_reposts([old, new]) == {"u1": "u2"}


def test_same_vacancy_on_another_site_is_not_a_repost():
    """Djinni і DOU — два канали однієї вакансії, а не перевипуск.

    Кількість відгуків у них непорівнянна: DOU її взагалі не повідомляє.
    """
    djinni = _p("u1", posted=datetime(2026, 9, 27))
    dou = _p("u2", source="dou", posted=datetime(2026, 10, 1))
    assert find_reposts([djinni, dou]) == {}


def test_different_titles_are_not_reposts():
    a = _p("u1", posted=datetime(2026, 10, 1))
    b = _p("u2", title="senior python developer", posted=datetime(2026, 10, 2))
    assert find_reposts([a, b]) == {}


def test_publication_without_a_date_never_wins():
    """Невідома дата не може ховати за собою свіжу публікацію."""
    unknown = _p("u1", posted=None)
    dated = _p("u2", posted=datetime(2026, 10, 8))
    assert find_reposts([unknown, dated]) == {"u1": "u2"}


def test_three_publications_all_point_to_the_newest():
    items = [_p("u1", posted=datetime(2026, 9, 1)),
             _p("u2", posted=datetime(2026, 9, 20)),
             _p("u3", posted=datetime(2026, 10, 8))]
    assert find_reposts(items) == {"u1": "u3", "u2": "u3"}


def test_single_publication_is_not_marked():
    assert find_reposts([_p("u1", posted=datetime(2026, 10, 8))]) == {}


def test_sorting_by_date_puts_undated_last():
    """Вакансія без дати йде вниз.

    Невідомо, коли вона вийшла, і ставити її поряд зі свіжими означало б
    вигадувати факт. Те саме правило, що й у перевипусках: без дати
    публікація ніколи не виграє.
    """
    from datetime import datetime

    class V:
        def __init__(self, posted, state="ok"):
            self.posted_at, self.state = posted, state

    _STATE = {"ok": 0, "unchecked": 1, "blocked": 2}
    rows = [V(None), V(datetime(2026, 10, 8)), V(datetime(2026, 9, 1))]
    rows.sort(key=lambda v: (v.posted_at is None,
                             -(v.posted_at.timestamp() if v.posted_at else 0),
                             _STATE[v.state]))
    assert [r.posted_at for r in rows] == [
        datetime(2026, 10, 8), datetime(2026, 9, 1), None]
