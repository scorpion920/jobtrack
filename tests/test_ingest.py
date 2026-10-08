"""Рішення про прийом вакансій — без БД і без мережі."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from app.ingest import KnownVacancy, plan_ingest
from app.sources.base import RawVacancy
from app.sources.djinni import parse_listing

NOW = datetime(2026, 10, 8, 22, 0)
FIXTURE = Path(__file__).parent / "fixtures" / "djinni_jobs_2026-10-08.html"


@pytest.fixture(scope="module")
def rows():
    return parse_listing(FIXTURE.read_text(encoding="utf-8"))


def test_first_run_creates_everything(rows):
    plan = plan_ingest(rows, [], NOW)
    assert len(plan.create) == 15
    assert plan.refresh == []


def test_second_run_creates_nothing(rows):
    """Головна властивість: збір іде за розкладом і бачить те саме."""
    known = [KnownVacancy(id=i, source_key=r.source_key, external_id=r.external_id,
                          company_norm="", title_norm="",
                          replies=r.payload["replies"])
             for i, r in enumerate(rows, start=1)]
    plan = plan_ingest(rows, known, NOW)
    assert plan.create == []
    assert len(plan.refresh) == 15
    # Нічого не змінилось — отже й приріст конкуренції нульовий.
    assert all(r.replies_delta == 0 for r in plan.refresh)


def test_growing_competition_is_measured():
    """Приріст відгуків важливіший за їх кількість: він показує розігрів."""
    raw = RawVacancy(source_key="djinni", external_id="1", url="u", title="t",
                     company="c", payload={"replies": 120, "views": 500})
    known = [KnownVacancy(id=7, source_key="djinni", external_id="1",
                          company_norm="c", title_norm="t", replies=98)]
    plan = plan_ingest([raw], known, NOW)
    assert plan.refresh[0].replies_delta == 22
    assert plan.refresh[0].vacancy_id == 7


def test_unknown_previous_count_is_not_zero_delta():
    """Нема з чим порівнювати — це None, а не «не змінилось»."""
    raw = RawVacancy(source_key="djinni", external_id="1", url="u", title="t",
                     company="c", payload={"replies": 120})
    known = [KnownVacancy(id=7, source_key="djinni", external_id="1",
                          company_norm="c", title_norm="t", replies=None)]
    assert plan_ingest([raw], known, NOW).refresh[0].replies_delta is None


def test_duplicate_within_one_page_is_noise_not_update(rows):
    """Та сама вакансія двічі в одній видачі — шум, а не дві події."""
    plan = plan_ingest(rows + rows, [], NOW)
    assert len(plan.create) == 15


def test_same_vacancy_from_another_channel_is_reported_not_merged():
    """Підозра показується, запис створюється. Автоматичне злиття за схожістю
    назв сховало б дві різні вакансії однієї компанії під одним записом."""
    raw = RawVacancy(source_key="dou", external_id="xx", url="https://dou/1",
                     title="Python Developer", company="ТОВ VCHASNO GROUP")
    known = [KnownVacancy(id=3, source_key="djinni", external_id="778695",
                          company_norm="vchasno group", title_norm="python developer")]
    plan = plan_ingest([raw], known, NOW)
    assert plan.cross_channel == [("https://dou/1", "djinni")]
    assert len(plan.create) == 1


def test_facts_are_interpreted_on_create(rows):
    plan = plan_ingest(rows, [], NOW)
    first = next(c for c in plan.create if c.raw.external_id == "848707")
    assert first.format == "remote"
    assert first.years_required == 1
    assert first.english == "a2"
    assert first.company_norm == "trident media"


def test_nothing_touches_orm():
    """Сторож: у чистому ядрі не має бути ані сесії, ані моделей.

    Той самий сторож, що й у sync.py. Причина не теоретична: саме звернення
    до ORM у шарі рішень дало MissingGreenlet на першому ж реальному записі.
    """
    text = Path(__file__).parent.parent.joinpath("app", "ingest.py").read_text(encoding="utf-8")
    for forbidden in ("from app.models", "AsyncSession", "session.", "select("):
        assert forbidden not in text, f"ORM протік у чисте ядро: {forbidden}"
