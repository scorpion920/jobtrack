"""Підготовка подачі: трек резюме, мова листа, на що звернути увагу.

Еталон перевірки — рішення, ухвалені руками 08.10.2026 по шести реальних
вакансіях. Там, де система розходиться з ними, помиляється система.
"""

from __future__ import annotations

from app.draft import TRACKS, detect_language, pick_track, prepare


def test_track_comes_from_the_job_title():
    """Суть у назві посади, інструменти — в тексті.

    Перша редакція рахувала збіги і помилилась там, де рішення вже були:
    INSART («ML Engineer/Data Scientist») і CrewRed («Junior Python
    Full-Stack Developer») обидві отримали ai-llm, бо згадують LLM в
    обов'язках і в бонусах. Одна згадка LLM не робить вакансію
    LLM-вакансією.
    """
    llm = ["LLM / агенти", "RAG / embeddings"]
    assert pick_track("ML Engineer/Data Scientist", llm) == "data-ml"
    assert pick_track("Junior Python Full-Stack Developer", llm) == "backend"
    assert pick_track("Python Developer", llm) == "backend"
    assert pick_track("AI Integration Specialist / LLM Engineer", llm) == "ai-llm"
    assert pick_track("Junior Data Engineer", []) == "data-ml"


def test_both_in_title_is_resolved_by_the_text():
    """«Senior AI/ML Engineer» — назва каже обидва, вирішує склад тексту."""
    ai_heavy = ["LLM / агенти", "RAG / embeddings"]
    ml_heavy = ["прогнозування часових рядів", "градієнтний бустинг",
                "детекція аномалій"]
    assert pick_track("Senior AI/ML Engineer", ai_heavy) == "ai-llm"
    assert pick_track("Senior AI/ML Engineer", ml_heavy) == "data-ml"


def test_language_of_the_letter_follows_the_posting():
    """CrewRed має англійський опис і англійські питання рекрутера;
    український лист там програв би на першому погляді. Зворотне теж
    правда: англійський лист українській компанії виглядає як розсилка."""
    assert detect_language(
        "We partner with startups and enterprises to build products") == "en"
    assert detect_language(
        "Шукаємо Python розробника у команду, досвід з FastAPI") == "uk"


def test_english_tech_names_do_not_make_a_ukrainian_posting_english():
    """Назви технологій латиницею є в кожному українському оголошенні."""
    text = ("Шукаємо розробника: Python, FastAPI, PostgreSQL, Docker, "
            "Celery, Redis, досвід з REST API та мікросервісами")
    assert detect_language(text) == "uk"


def test_empty_text_defaults_to_ukrainian():
    assert detect_language("") == "uk"


def test_notes_point_at_what_changes_the_letter():
    low = prepare(title="Python Developer", raw_text="Шукаємо", matched=[],
                  gaps=[], replies=3)
    assert any("не завтра" in n for n in low.notes)

    crowded = prepare(title="Python Developer", raw_text="Шукаємо", matched=[],
                      gaps=[], replies=300)
    assert any("перших двох речень" in n for n in crowded.notes)

    english = prepare(title="Python Developer", raw_text="We are looking for",
                      matched=[], gaps=[], replies=None)
    assert any("англійською" in n for n in english.notes)

    above = prepare(title="Python Developer", raw_text="Шукаємо", matched=[],
                    gaps=[], english="c1")
    assert any("C1" in n for n in above.notes)


def test_cv_file_matches_the_track():
    d = prepare(title="ML Engineer", raw_text="Шукаємо", matched=[], gaps=[])
    assert d.cv_file == TRACKS["data-ml"]
    assert d.cv_file.endswith(".pdf")


def test_level_named_by_word_is_a_note_not_a_blocker():
    """«Strong Middle» — вище за профіль, але не блокер.

    На межі такі вакансії беруть сильного junior, і відсіювати їх означало б
    втрачати саме ті, де шанс існує. Знайдено на Dedicatted 09.10.2026:
    «We're looking for a Strong Middle Data Scientist / AI Engineer», при
    цьому явної вимоги «X років» у тексті немає зовсім — скринер мовчав
    справедливо, і мовчання тут було гіршим за попередження.
    """
    d = prepare(title="Data Scientist/AI Engineer",
                raw_text="We're looking for a Strong Middle Data Scientist",
                matched=["Python"], gaps=[])
    assert any("Strong Middle" in n for n in d.notes)
    assert any("перших двох реченнях" in n for n in d.notes)


def test_plain_middle_is_not_flagged():
    """Звичайний Middle — досяжний рівень, попереджати нема про що."""
    d = prepare(title="Middle Python Developer",
                raw_text="Шукаємо Middle розробника", matched=["Python"], gaps=[])
    assert not any("рівень вищий" in n for n in d.notes)
