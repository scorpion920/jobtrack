"""Змістовна відповідність — на справжніх формулюваннях вакансій.

Усі зразки взято з текстів, які власник прочитав і оцінив САМ 08.10.2026.
Це головна перевірка модуля: скринер має відтворювати рішення людини, а не
власну логіку. Там, де він розійдеться з нею, помиляється він.
"""

from __future__ import annotations

from app.screening import screen

#  PrivatBank, Data Scientist — відхилено власником: «ноукодера хоче».
PRIVATBANK = """Data Scientist (Business Analytics)
Побудова математичних і статистичних моделей із використанням
Low-code/No-code AI/ML платформ, інструментів аналітики та технологій
Business Intelligence (BI). Проведення А/Б тестувань."""

#  Artellence, Strong junior ML engineer — відхилено власником:
#  «джуна з сильнішими теоретичними знаннями, ніж в мене».
ARTELLENCE = """Strong junior Machine learning engineer
Математичний бекграунд: вища математична освіта (КПІ ІПСА, МехМат Шевченко
тощо), бажано олімпіадний досвід. Глибокі теоретичні та практичні знання
машинного та глибокого навчання. Високий рівень володіння Python."""

#  KaaIoT, Junior SRE/DevOps — Java тут лише як додатки, збірку яких
#  підтримують; сама позиція вимагає Python.
KAAIOT = """Junior SRE / DevOps Engineer
Work with Jenkins pipelines. Support Java application build processes using
Maven. Python scripting, Docker, Linux, PostgreSQL, Grafana, Prometheus,
моніторинг, asyncio."""


def test_no_code_platform_is_a_stop_signal():
    m = screen(PRIVATBANK)
    assert m.fit == "weak"
    assert any("No-code" in c for c in m.concerns)


def test_academic_math_requirement_is_a_stop_signal():
    m = screen(ARTELLENCE)
    assert m.fit == "weak"
    assert any("математичної освіти" in c for c in m.concerns)


def test_mention_of_another_language_is_not_a_stop_when_python_is_required():
    """Згадка мови ≠ мова позиції.

    KaaIoT згадує Java як додатки, збірку яких підтримує DevOps, і при цьому
    сам вимагає Python. Перша редакція правила відсіювала цю вакансію — а
    вона була найменш заповненою серед доступних (16 відгуків).
    """
    m = screen(KAAIOT)
    assert "основна мова — не Python" not in m.concerns
    assert m.fit == "strong"


def test_another_language_without_python_is_a_stop():
    m = screen("Senior .NET Developer. C#, ASP.NET, MS SQL.")
    assert "основна мова — не Python" in m.concerns


def test_short_description_is_not_punished_for_brevity():
    """Broscorp, куди подано 08.10.2026, має опис на 1190 символів.

    Коротке оголошення фізично не дасть багато збігів. Вимагати їх означало б
    відсіювати вакансії за небагатослівністю рекрутера.
    """
    m = screen("Python Integration Engineer. Інтеграції, REST API.")
    assert m.fit == "possible"
    assert 2 <= len(m.matched) <= 3


def test_strong_fit_needs_real_overlap():
    m = screen("""Python, FastAPI, PostgreSQL, Celery, Docker, ETL пайплайни,
               прогнозування часових рядів, детекція аномалій""")
    assert m.fit == "strong"
    assert "Celery" in m.matched and "ETL / пайплайни" in m.matched


def test_gaps_are_named_with_a_replacement():
    """Прогалина, названа прямо, читається інакше, ніж замовчана."""
    m = screen("Потрібен досвід Airflow і Kubernetes")
    assert any("Airflow" in g and "Celery" in g for g in m.gaps)
    assert any("Kubernetes" in g for g in m.gaps)


def test_leadership_role_is_a_stop():
    assert "керівна позиція" in " ".join(screen("Team Lead Python").concerns)


def test_empty_text_is_weak_not_an_error():
    assert screen("").fit == "weak"
    assert screen(None).matched == []


def test_infrastructure_overlap_without_python_is_not_a_fit():
    """Вакансія «Node.js Developer» набирала ШІСТЬ збігів і ставала `strong`.

    Усі шість — PostgreSQL, Docker, REST API, async/await, інтеграції,
    TypeScript — інфраструктура, спільна для будь-якої backend-вакансії.
    Жоден не свідчить про придатність, коли основної мови немає.
    """
    node = """Node.js Developer. Комерційний досвід з Node.js, Express, NestJS
    і TypeScript. PostgreSQL та GraphQL. Розуміння асинхронності: event loop,
    Promise, async/await. Досвід інтеграцій зі сторонніми API. Docker."""
    m = screen(node)
    assert m.fit == "weak"
    assert any("немає Python" in c for c in m.concerns)
    # Збіги при цьому нікуди не зникають — вони просто нічого не доводять.
    assert len(m.matched) >= 4


def test_python_vacancy_keeps_its_fit():
    m = screen("""Python Developer. FastAPI, PostgreSQL, Docker, Celery,
               ETL пайплайни, інтеграції з API.""")
    assert m.fit == "strong"
    assert not m.concerns
