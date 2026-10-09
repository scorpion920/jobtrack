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


def test_devops_is_recognised_by_the_job_title_not_the_tools():
    """KaaIoT «Junior SRE / DevOps Engineer» отримував strong із шістьма
    збігами — Python, Docker, Linux, PostgreSQL, моніторинг, asyncio.

    Усі шість справжні, і все одно це не та робота: власник пише код, а не
    супроводжує чужий. Сигнал мусить читатися з НАЗВИ, бо «Docker» і «CI/CD»
    згадує половина вакансій розробника.
    """
    tools = """Python scripting, Docker, Linux, PostgreSQL, Grafana,
    Prometheus, моніторинг, asyncio, CI/CD pipelines"""
    assert screen(tools, "Junior SRE / DevOps Engineer").fit == "weak"
    assert "DevOps/SRE, а не розробка" in screen(tools, "Junior SRE / DevOps Engineer").concerns
    # Той самий текст під назвою розробника — придатний.
    assert screen(tools, "Python Developer").fit == "strong"


def test_devops_tools_in_a_developer_vacancy_are_not_a_stop():
    """Розробник теж користується Docker і CI/CD — це інструмент, не професія."""
    m = screen("Python, FastAPI, Docker, CI/CD, Kubernetes, моніторинг",
               "Backend Python Developer")
    assert not any("DevOps" in c for c in m.concerns)


def test_other_professions_are_recognised_by_title():
    tools = "Python, SQL, Docker, PostgreSQL, REST API"
    cases = {
        "QA Automation Engineer": "тестування",
        "Technical Support Specialist": "підтримка",
        "Product Manager": "менеджмент",
        "Motion Designer": "дизайн",
        "Talent Sourcer": "рекрутинг",
        "Media Buyer": "продажі",
    }
    for title, expected in cases.items():
        concerns = " ".join(screen(tools, title).concerns)
        assert expected in concerns, f"{title}: {concerns}"


def test_title_is_optional():
    """Без назви модуль працює як раніше — канал може її не дати."""
    assert screen("Python, FastAPI, PostgreSQL, Docker, Celery, ETL").fit == "strong"


def test_single_mention_of_a_vendor_platform_is_not_a_stop():
    """«PostgreSQL або Oracle» — звичайний рядок вимог, де друга СУБД опційна."""
    m = screen("Досвід роботи з PostgreSQL або Oracle. Python, FastAPI, Docker, ETL",
               "Python Developer")
    assert not any("Oracle" in c for c in m.concerns)


def test_vacancy_built_around_a_vendor_platform_is_a_stop():
    """Intellica Consulting, 08.10.2026.

    Djinni показував заголовок «Junior Data Platform Engineer», а в тексті
    вакансія називається «Junior Oracle Platform Engineer» і згадує Oracle
    ШІСТЬ разів. Заголовок приховував суть — саме тому рахується текст.
    """
    text = """Запрошуємо Junior Oracle Platform Engineer. Робота з
    корпоративними платформами на базі Oracle Technologies. Oracle Database,
    Oracle Cloud, сертифікація Oracle. Python, SQL."""
    m = screen(text, "Junior Data Platform Engineer")
    assert m.fit == "weak"
    assert any("Oracle" in c for c in m.concerns)


def test_experience_threshold_is_read_from_the_text():
    """DOU не повідомляє років окремим полем.

    Із 80 зібраних вакансій 46 потрапили в «потребує перегляду» саме через
    це. DOIT Software вимагає «3–5 years of professional experience» прямо
    в тексті — без цього правила вакансія виглядала б придатною.
    """
    for text in ("3–5 years of professional experience in data science",
                 "5+ years of experience with Python",
                 "досвід роботи від 3 років"):
        concerns = screen(text, "Python Developer").concerns
        assert any("3+ років" in c for c in concerns), text


def test_one_or_two_years_is_not_a_threshold():
    """«1 рік» збігається з профілем, «2 роки» — межа, яку пишуть про запас."""
    for text in ("1+ рік комерційного досвіду", "2 роки досвіду",
                 "Досвід DS/MLE від 1 року"):
        concerns = screen(text, "Python Developer").concerns
        assert not any("років досвіду" in c for c in concerns), text


def test_screening_is_linear_on_hostile_input():
    """Сторож проти ReDoS. Текст вакансії приходить із чужого майданчика.

    Перша редакція правила про роки мала три `\\s*` поспіль, і рушій
    перебирав усі способи розділити між ними пробіли. Вимір 08.10.2026:
    200 пробілів — 25 мс, 400 — 190 мс, 800 — 1,5 с, 1600 — 12 с. Подвоєння
    входу давало ріст у вісім разів, тож одного оголошення з довгим рядком
    пробілів вистачило б, щоб підвісити збір.

    Поріг у тесті з великим запасом: після виправлення 20 000 пробілів
    опрацьовуються за частки мілісекунди.
    """
    import time

    hostile = "3" + " " * 20000 + "x " + "a" * 5000 + " " * 10000 + "років"
    start = time.perf_counter()
    screen(hostile, "Python Developer")
    assert time.perf_counter() - start < 1.0


def test_threshold_rule_still_works_after_bounding():
    """Межі на повтореннях не змінили того, що правило ловить."""
    assert any("3+ років" in c
               for c in screen("3–5 years of professional experience",
                               "Python Developer").concerns)
    assert any("3+ років" in c
               for c in screen("5+ years of experience", "Python Developer").concerns)
    assert not any("3+ років" in c
                   for c in screen("1 рік досвіду", "Python Developer").concerns)


def test_rules_work_through_non_breaking_spaces():
    """Правило перестало ловити на СПРАВЖНІХ текстах, лишаючись зеленим.

    Знайдено вранці 09.10.2026 по шуму в каналі: у канал пішли сімнадцять
    вакансій, серед них DOIT Software з вимогою «3–5 years of professional
    experience», яку скринер відсіював напередодні.

    Причина — ланцюг із двох кроків, кожен сам по собі правильний:
      1. HTML рясніє `&nbsp;`, і після зняття розмітки вони лишаються
         як U+00A0 — у DOIT це `of\\xa0professional`;
      2. виправляючи ReDoS, довелося замінити `\\s*` на явний `[ \\t]{0,3}`,
         а цей клас нерозривного пробілу не ловить.

    Тест на звичайних пробілах лишався зеленим — саме тому він і не
    спіймав: перевіряв те, чого в реальних даних не буває.
    """
    nbsp = "3–5 years of professional experience in data science"
    concerns = screen(nbsp, "Data Scientist").concerns
    assert any("3+ років" in c for c in concerns), concerns

    # Інші невидимі пробіли з тієї ж родини.
    for space in (" ", " "):
        text = f"5+ years of{space}experience with Python"
        assert any("3+ років" in c for c in screen(text, "Developer").concerns), space


def test_zero_width_characters_do_not_hide_keywords():
    """Символи нульової ширини розривають слово, не змінюючи вигляду."""
    from app.screening import normalize_spaces

    assert normalize_spaces("Py​thon") == "Python"
    assert normalize_spaces(None) == ""


def test_seniority_in_title_blocks_the_vacancy():
    """Один рік комерційного досвіду не робить Senior-вакансію доступною,
    хай як збігається стек.

    Усі шість із нічного шуму мали рівень у НАЗВІ: Ciklum «Expert», PLANEKS
    і Django Stars «Senior», Group107, YozmaTech, Xenoss. DOU не повідомляє
    років, а в тексті вимога трапляється не завжди — назва ж каже рівень
    прямо, так само як вона каже професію.
    """
    stack = "Python, FastAPI, PostgreSQL, Docker, ETL, Celery"
    for title in ("Expert Full Stack Engineer", "Senior Applied AI Engineer",
                  "Staff Engineer", "Principal Developer", "Head of Data"):
        assert screen(stack, title).fit == "weak", title


def test_strong_junior_is_not_senior():
    """«Strong Junior» містить слово Strong, а не Senior."""
    stack = "Python, FastAPI, PostgreSQL, Docker, ETL, Celery"
    for title in ("Strong Junior Python Engineer", "Junior Data Engineer",
                  "Middle Backend Developer", "Python Developer"):
        assert screen(stack, title).fit == "strong", title


def test_seniority_named_only_in_the_body_is_caught():
    """GT Protocol: у заголовку рівня немає, у тексті є.

    «Full Stack Engineer (Python / React / Web3)» — і нижче «We are looking
    for a Senior Full Stack Engineer». З семи вакансій, що називають рівень
    у тексті, шість повторюють його в назві; ця одна — ні, і саме вона
    проскочила в канал 09.10.2026.
    """
    text = ("We are looking for a Senior Full Stack Engineer who embraces "
            "AI-assisted development. Python, React, PostgreSQL, Docker.")
    m = screen(text, "Full Stack Engineer (Python / React / Web3)")
    assert m.fit == "weak"
    assert any("названо в тексті" in c for c in m.concerns)


def test_ordinary_mention_of_seniors_is_not_a_stop():
    """«Працюватимете поруч із senior-інженерами» — не вимога до рівня.

    Саме такою фразою CrewRed описує команду, і вона не повинна відсіювати
    junior-вакансію.
    """
    text = ("Work alongside experienced senior engineers who'll help you "
            "level up. Python, FastAPI, PostgreSQL, React, Docker, ETL.")
    m = screen(text, "Junior Python Full-Stack Developer")
    assert not any("рівень вищий" in c for c in m.concerns)
    assert m.fit == "strong"
