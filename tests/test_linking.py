"""Зв'язування подачі із зібраною вакансією.

Прогалину помітив оператор 08.10.2026: у плані зв'язок був, у схемі — ні.
Через це не можна було відповісти на головні питання циклу — на яку з
придатних вакансій уже подано і яка була конкуренція на момент подачі.

Точний збіг адрес тут не працює: з восьми реальних подач він зводив ОДНУ.
Адреса несе сліди шляху, а номер вакансії — ні.
"""

from __future__ import annotations

from app.linking import link, vacancy_key


def test_query_tail_does_not_break_the_match():
    """Саме хвости розводили адреси: `?applied=ok` після кнопки подачі,
    `?sender=` з листа."""
    assert vacancy_key("https://djinni.co/jobs/778695-python-developer/?applied=ok") \
        == ("djinni", "778695")
    assert vacancy_key("https://jobs.dou.ua/companies/insart/vacancies/375671/?sender=x") \
        == ("dou", "375671")


def test_same_vacancy_with_and_without_tail_gives_one_key():
    bare = vacancy_key("https://djinni.co/jobs/849944-junior-python-full-stack-developer/")
    tailed = vacancy_key("https://djinni.co/jobs/849944-junior-python-full-stack-developer/?x=1")
    assert bare == tailed == ("djinni", "849944")


def test_inbox_page_is_not_a_vacancy():
    """Сторінка листування веде не на вакансію — зв'язати неможливо в принципі,
    і вигадувати зв'язок за назвою компанії небезпечно: у великої компанії
    одночасно відкрито кілька вакансій."""
    assert vacancy_key("https://djinni.co/my/inbox/26731485/") is None


def test_foreign_or_missing_url_is_not_an_error():
    """Подача могла прийти поштою або з LinkedIn — це звичайний стан."""
    assert vacancy_key("https://example.com/jobs/1") is None
    assert vacancy_key(None) is None
    assert vacancy_key("") is None


def test_dou_url_without_company_segment():
    assert vacancy_key("https://jobs.dou.ua/vacancies/375671/") == ("dou", "375671")


def test_link_pairs_only_what_it_knows():
    apps = [(1, "https://djinni.co/jobs/778695-x/?applied=ok"),
            (2, "https://djinni.co/my/inbox/999/"),
            (3, "https://djinni.co/jobs/111111-unknown/")]
    vacancies = [(10, "djinni", "778695"), (11, "dou", "375671")]
    assert link(apps, vacancies) == {1: 10}


def test_same_number_on_different_sites_does_not_collide():
    """Номер унікальний у межах майданчика, не між ними."""
    apps = [(1, "https://jobs.dou.ua/vacancies/778695/")]
    vacancies = [(10, "djinni", "778695")]
    assert link(apps, vacancies) == {}
