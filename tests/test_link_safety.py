"""Посилання з чужих джерел не стають виконуваним кодом.

Знайдено фоновою перевіркою коміту 08.10.2026. Текстовий XSS не проходив
(autoescape увімкнено, а теги знімаються після розгортання сутностей), але
поруч була справжня діра: `href="{{ v.url }}"`. Екранування Jinja захищає від
лапок і НЕ забороняє схему — `javascript:alert(1)` у полі `<link>` фіду
лишився б клікабельним кодом на нашій сторінці.

Лікування в корені: схема перевіряється на ВХОДІ, а не фільтрується на виході.
"""

from __future__ import annotations

from app.sources.djinni import parse_listing
from app.sources.dou import parse_dou_feed
from app.sources.rss import is_safe_link, parse_feed


def test_only_http_schemes_pass():
    assert is_safe_link("https://jobs.dou.ua/x/")
    assert is_safe_link("http://example.org/x")
    for bad in ("javascript:alert(1)", "JaVaScRiPt:alert(1)", "data:text/html,x",
                "vbscript:x", "//evil.example/x", "", "   "):
        assert not is_safe_link(bad), bad


def test_feed_item_with_dangerous_link_is_dropped():
    """Запис не «чиститься», а відкидається: вакансія без робочої адреси
    все одно нічого не варта, а напівполагоджене посилання — пастка."""
    xml = ('<rss><channel><item><title>Вакансія</title>'
           '<link>javascript:alert(1)</link></item></channel></rss>')
    assert parse_feed(xml) == []
    assert parse_dou_feed(xml) == []


def test_djinni_accepts_only_relative_hrefs_of_the_site():
    """Чужий домен або протокольно-відносна адреса в переліку — не вакансія."""
    for href in ("//evil.example/jobs/1-x/", "https://evil.example/jobs/1-x/",
                 "javascript:alert(1)"):
        html = (f'<div id="job-item-1"><a class="job_item__header-link" href="{href}">'
                '<h2 class="job-item__position">Python Developer</h2></a></div>')
        assert parse_listing(html) == [], href


def test_normal_djinni_href_still_works():
    html = ('<div id="job-item-1">'
            '<a class="job_item__header-link" href="/jobs/1-python/">'
            '<h2 class="job-item__position">Python Developer</h2></a>'
            '<span class="small text-gray-800">Acme</span>'
            '<div id="job-description-1"><span class="js-original-text">'
            'опис вакансії достатньої довжини для перевірки</span></div></div>')
    rows = parse_listing(html)
    assert len(rows) == 1
    assert rows[0].url == "https://djinni.co/jobs/1-python/"


def test_escaped_script_does_not_survive_description_cleanup():
    """Подвійне розгортання сутностей безпечне, бо теги знімаються ПІСЛЯ нього."""
    from app.sources.rss import strip_html

    assert "<script>" not in strip_html("&amp;lt;script&amp;gt;alert(1)&amp;lt;/script&amp;gt;")
    assert strip_html("&amp;lt;script&amp;gt;alert(1)&amp;lt;/script&amp;gt;") == "alert(1)"


def test_templates_escape_by_default():
    """Сторож проти вимкнення autoescape у майбутньому."""
    from app.main import templates

    assert templates.env.autoescape is True
