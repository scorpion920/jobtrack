"""Тести зіставлення — найтоншого місця системи.

Помилка тут або створює дубль, або дописує подію чужій подачі. Друге гірше:
воно мовчки псує саме те число, заради якого все будувалося.
"""

from __future__ import annotations

from datetime import date

from app.sync import (Candidate, SyncItem, find_match, normalize_name,
                      normalize_url, plan_sync)


class TestNormalizeUrl:
    def test_strips_tracking_parameters(self):
        a = normalize_url("https://djinni.co/jobs/123-python/?utm_source=mail&utm_medium=x")
        b = normalize_url("https://djinni.co/jobs/123-python/")
        assert a == b

    def test_keeps_meaningful_query(self):
        """Не всякий параметр — трекінг: у деяких сайтів id вакансії саме там."""
        assert normalize_url("https://x.com/job?id=7") == "https://x.com/job?id=7"

    def test_scheme_and_www_do_not_matter(self):
        assert (normalize_url("http://www.djinni.co/jobs/1/")
                == normalize_url("https://djinni.co/jobs/1"))

    def test_query_order_does_not_matter(self):
        assert normalize_url("https://x.com/j?b=2&a=1") == normalize_url("https://x.com/j?a=1&b=2")

    def test_empty_and_garbage_give_none(self):
        assert normalize_url(None) is None
        assert normalize_url("   ") is None
        assert normalize_url("не-посилання") is None


class TestNormalizeName:
    def test_legal_form_is_ignored(self):
        assert normalize_name("ТОВ «Вчасно»") == normalize_name("Вчасно")

    def test_case_and_punctuation_ignored(self):
        assert normalize_name("S-PRO, Inc.") == normalize_name("s pro")

    def test_empty_stays_empty(self):
        assert normalize_name(None) == ""


class TestFindMatch:
    def _cands(self):
        return [
            Candidate(1, "Вчасно", "Python Developer", "https://jobs.dou.ua/x/1/"),
            Candidate(2, "Вчасно", "Middle Python Developer", None),
            Candidate(3, "SCIMUS", "Full Stack Engineer", "https://jobs.dou.ua/y/2/"),
        ]

    def test_url_wins_even_if_names_differ(self):
        item = SyncItem(company="інакше написано", position="і позиція інша",
                        url="https://jobs.dou.ua/x/1/?utm_source=a")
        assert find_match(item, self._cands()).id == 1

    def test_falls_back_to_company_and_position(self):
        item = SyncItem(company="ТОВ Вчасно", position="middle python developer")
        assert find_match(item, self._cands()).id == 2

    def test_company_alone_is_not_enough(self):
        """В одну компанію подаються на кілька позицій. Зарахувати не тій —
        гірше, ніж не зарахувати нікому."""
        item = SyncItem(company="Вчасно", position="Data Engineer")
        assert find_match(item, self._cands()) is None

    def test_ambiguous_match_is_refused(self):
        """Два однакові кандидати означають дубль у журналі. Вибір навмання
        приховав би його."""
        cands = [Candidate(1, "X", "Dev", None), Candidate(2, "X", "Dev", None)]
        assert find_match(SyncItem(company="X", position="Dev"), cands) is None

    def test_no_match_returns_none(self):
        item = SyncItem(company="Невідома", position="Хтозна")
        assert find_match(item, self._cands()) is None

    def test_item_without_company_or_position_is_refused(self):
        assert find_match(SyncItem(company="", position="Dev"), self._cands()) is None
        assert find_match(SyncItem(company="Вчасно", position=""), self._cands()) is None

    def test_match_survives_tracking_and_trailing_slash(self):
        item = SyncItem(company="?", position="?",
                        url="http://www.jobs.dou.ua/y/2?fbclid=zzz")
        assert find_match(item, self._cands()).id == 3


class TestPlanSync:
    """Планування синхронізації — чиста функція, без БД.

    Винесена з ендпойнта після того, як перша редакція впала з MissingGreenlet:
    вона перевіряла наявні події через `target.events` на щойно створеному
    ORM-об'єкті, і SQLAlchemy пішов довантажувати зв'язок поза greenlet-контекстом.
    Помилка проявилась лише на справжньому записі — сухий прогін до тієї гілки
    не доходив, тому тест «сухий прогін працює» нічого не доводив.
    """

    TODAY = date(2026, 10, 8)

    def test_new_application_is_planned_with_sent_event(self):
        plan = plan_sync([SyncItem(company="X", position="Dev",
                                   applied_on=date(2026, 10, 1))],
                         [], {}, self.TODAY)
        assert len(plan.create) == 1
        assert [(e.status, e.occurred_on) for e in plan.events] == [("sent", date(2026, 10, 1))]

    def test_applied_on_defaults_to_today(self):
        plan = plan_sync([SyncItem(company="X", position="Dev")], [], {}, self.TODAY)
        assert plan.create[0].applied_on == self.TODAY

    def test_known_event_is_not_planned_again(self):
        """Серце ідемпотентності: повторна синхронізація тієї самої сторінки
        не має додати жодного рядка."""
        cands = [Candidate(7, "X", "Dev", None)]
        known = {7: {("viewed", date(2026, 10, 3))}}
        plan = plan_sync([SyncItem(company="X", position="Dev", status="viewed",
                                   status_on=date(2026, 10, 3))],
                         cands, known, self.TODAY)
        assert plan.create == []
        assert plan.events == []
        assert plan.matched == 1

    def test_new_status_on_known_application_is_planned(self):
        cands = [Candidate(7, "X", "Dev", None)]
        known = {7: {("viewed", date(2026, 10, 3))}}
        plan = plan_sync([SyncItem(company="X", position="Dev", status="rejected",
                                   status_on=date(2026, 10, 9))],
                         cands, known, self.TODAY)
        assert len(plan.events) == 1
        assert plan.events[0].application_id == 7

    def test_same_vacancy_twice_in_one_page_creates_one_application(self):
        """Сторінка може містити дубль. Друге входження має зіставитись із
        першим, а не створити другу подачу."""
        item = SyncItem(company="X", position="Dev", url="https://a.io/1")
        plan = plan_sync([item, item], [], {}, self.TODAY)
        assert len(plan.create) == 1
        assert plan.matched == 1

    def test_ambiguous_company_is_reported_not_created(self):
        cands = [Candidate(1, "X", "Dev", None), Candidate(2, "X", "QA", None)]
        plan = plan_sync([SyncItem(company="X", position="Data Engineer")],
                         cands, {}, self.TODAY)
        assert plan.create == []
        assert plan.ambiguous == ["X / Data Engineer"]

    def test_status_for_new_application_is_planned_without_id(self):
        """Події нової подачі не можуть нести id — його ще немає. Прив'язка
        йде через індекс рядка, і саме її застосовує ендпойнт після flush."""
        plan = plan_sync([SyncItem(company="X", position="Dev", status="viewed",
                                   status_on=date(2026, 10, 5))],
                         [], {}, self.TODAY)
        statuses = [(e.application_id, e.status, e.item_index) for e in plan.events]
        assert statuses == [(None, "sent", 0), (None, "viewed", 0)]

    def test_nothing_touches_orm(self):
        """Сторож проти повернення вади: планувальник не повинен знати про ORM."""
        import inspect

        import app.sync as module
        src = inspect.getsource(module)
        for forbidden in ("selectinload", "session", "AsyncSession", "await "):
            assert forbidden not in src, f"у планувальник просочився {forbidden!r}"


class TestCvVersionCarriesThrough:
    """Версія резюме мусить доїхати до створеної подачі.

    Це єдине поле, за яким воронка вміє порівняти варіанти резюме між собою —
    тобто відповісти, чи взагалі щось дає адаптація під вакансію. DOU дає його
    як ім'я файлу, Djinni не дає взагалі. Загубити його означає втратити
    половину сенсу журналу, і загубити тихо: ніде нічого не впаде.
    """

    def test_version_reaches_planned_application(self):
        plan = plan_sync([SyncItem(company="ARTJOKER", position="Python Developer",
                                   cv_version="CV_ARTJOKER")],
                         [], {}, date(2026, 10, 8))
        assert plan.create[0].cv_version == "CV_ARTJOKER"

    def test_absent_version_is_none_not_empty_string(self):
        """None означає «невідомо», порожній рядок — «відомо, що порожнє».
        У воронці це різні відра, і плутати їх не можна."""
        plan = plan_sync([SyncItem(company="X", position="Dev")], [], {},
                         date(2026, 10, 8))
        assert plan.create[0].cv_version is None


class TestFillEmptyNeverOverwrite:
    """Правило злиття: доповнюємо порожнє, не затираємо заповнене.

    Знадобилось одразу: перший прогін DOU не зчитав імені файлу резюме через
    хибно визначений контейнер рядка. Без цього правила виправлення збирача
    нічого б не дало — 17 зіставлених подач лишились би назавжди без версії,
    бо зіставлення саме по собі полів не оновлює.
    """

    TODAY = date(2026, 10, 8)

    def test_missing_version_is_filled_on_match(self):
        cands = [Candidate(7, "X", "Dev", "https://a.io/1", None)]
        plan = plan_sync([SyncItem(company="X", position="Dev", url="https://a.io/1",
                                   cv_version="CV_X")], cands, {}, self.TODAY)
        assert plan.fill_cv == {7: "CV_X"}

    def test_existing_version_is_never_overwritten(self):
        """Інакше повторна синхронізація з гіршого джерела псувала б дані."""
        cands = [Candidate(7, "X", "Dev", "https://a.io/1", "CV_OLD")]
        plan = plan_sync([SyncItem(company="X", position="Dev", url="https://a.io/1",
                                   cv_version="CV_NEW")], cands, {}, self.TODAY)
        assert plan.fill_cv == {}

    def test_nothing_to_fill_when_item_has_no_version(self):
        cands = [Candidate(7, "X", "Dev", "https://a.io/1", None)]
        plan = plan_sync([SyncItem(company="X", position="Dev", url="https://a.io/1")],
                         cands, {}, self.TODAY)
        assert plan.fill_cv == {}
