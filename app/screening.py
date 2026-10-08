"""Відповідність вакансії за ЗМІСТОМ, а не за формальними полями.

Формальні перепони (`screen.py`) відповідають на питання «чи дадуть податись».
Цей модуль — на інше: «чи має сенс». Різниця виявилась дорогою 08.10.2026:
PrivatBank і Artellence пройшли всі чотири формальні умови — формат, роки,
англійська, країна — і обидві не підійшли за суттю. Перша шукає людину під
Low-code/No-code платформи, друга — джуна з академічною математичною базою.

Сигнали взято з ТЕКСТІВ цих вакансій, а не вигадано:

    «Побудова моделей із використанням Low-code/No-code AI/ML платформ»
    «Математичний бекграунд: вища математична освіта (КПІ ІПСА, МехМат
     Шевченко тощо), бажано олімпіадний досвід»

Вердикт тут М'ЯКШИЙ за формальний: текст вакансії читається по-різному, і
хибна відмова дорожча за хибне «подивись». Відкинуту вакансію більше ніколи
не покажуть, а зайвий перегляд коштує хвилину.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

#  ЩО ВМІЮ — ключ і способи, якими це називають у вакансіях.
#  Перелік відображає реальний досвід, а не бажаний: кожен рядок має
#  відповідати чомусь, про що можна говорити на співбесіді годину.
HAVE: dict[str, tuple[str, ...]] = {
    "Python": ("python", "пайтон"),
    "FastAPI": ("fastapi", "fast api"),
    "SQLAlchemy": ("sqlalchemy", "sql alchemy"),
    "Celery": ("celery",),
    "asyncio": ("asyncio", "async/await", "асинхрон"),
    "PostgreSQL": ("postgresql", "postgres", "постгре"),
    "Redis": ("redis",),
    "REST API": ("rest api", "restful", "api design", "проєктування api"),
    "ETL / пайплайни": ("etl", "elt", "data pipeline", "пайплайн", "конвеєр даних",
                        "data ingestion", "інжест"),
    "парсинг і інтеграції": ("парсинг", "parsing", "scraping", "скрапінг",
                             "інтеграці", "integration"),
    "pandas / NumPy": ("pandas", "numpy"),
    "прогнозування часових рядів": ("time series", "часових ряд", "часові ряди",
                                    "forecasting", "прогнозуван", "arima", "prophet"),
    "градієнтний бустинг": ("lightgbm", "xgboost", "catboost", "gradient boosting",
                            "градієнтний бустинг"),
    "детекція аномалій": ("anomaly", "аномал", "outlier"),
    "feature engineering": ("feature engineering", "ознак"),
    "LLM / агенти": ("llm", "gpt", "openai", "агент", "agent", "prompt"),
    "RAG / embeddings": ("rag", "retrieval augmented", "embedding", "векторн",
                         "vector search", "semantic search", "pgvector"),
    "Docker": ("docker", "контейнер"),
    "Linux": ("linux", "bash"),
    "React / TypeScript": ("react", "typescript"),
    "Grafana / Prometheus": ("grafana", "prometheus", "моніторинг"),
    "SQL-оптимізація": ("оптимізаці запит", "query optimization", "індекс", "index",
                        "window function", "віконн"),
}

#  ЧОГО НЕМАЄ — і чим це замінено. Текст пояснення потрібен не скринеру, а
#  супровідному листу: прогалину, названу прямо, читають інакше, ніж
#  замовчану й виявлену на співбесіді.
GAPS: dict[str, str] = {
    "AWS": "хмар не використовував — усе на власних серверах, Docker Compose",
    "Azure": "хмар не використовував",
    "GCP": "хмар не використовував",
    "Kubernetes": "оркестрацію робив на Docker Compose, 57 контейнерів у проді",
    "Terraform": "інфраструктуру описував у compose-файлах, не в Terraform",
    "Airflow": "оркестрацію робив на Celery + Beat: 131 періодична задача, "
               "ланцюги, ретраї, backfill — поняття ті самі, інструмент інший",
    "dbt": "трансформації робив SQL і materialized views",
    "Spark": "великих обсягів не ганяв через Spark — PostgreSQL і pandas",
    "Kafka": "черги на Celery + Redis",
    "LangChain": "агентів будував своєю архітектурою на MCP, не на LangChain",
    "MS SQL": "лише PostgreSQL",
    "Power BI": "дашборди на React і Grafana",
    "Tableau": "дашборди на React і Grafana",
    "Django": "працював на FastAPI; Django не використовував",
}

#  ЗА ЩО НЕ БРАТИСЬ — сигнали змістовної невідповідності.
#  Кожен узято з тексту справжньої вакансії, яку власник відхилив сам.
STOP_PATTERNS: tuple[tuple[str, str], ...] = (
    # PrivatBank, Data Scientist (08.10.2026): «Побудова математичних і
    # статистичних моделей із використанням Low-code/No-code AI/ML платформ».
    # Робота в конструкторі, а не в коді — інша професія, попри ту саму назву.
    (r"low[\s-]?code|no[\s-]?code|нокод|лоукод",
     "робота в No-code/Low-code платформі, а не в коді"),

    # Artellence, Strong junior ML engineer (08.10.2026): «Математичний
    # бекграунд: вища математична освіта (КПІ ІПСА, МехМат Шевченко тощо),
    # бажано олімпіадний досвід».
    (r"математичн\w*\s+(освіт|бекграунд|підготовк|фак)|мехмат|іпса|"
     r"прикладн\w+\s+математик",
     "вимагає профільної математичної освіти"),
    (r"олімпіад|kaggle\s+(змагань|competitions|medal)|"
     r"глибок\w+\s+теоретичн\w+\s+знанн",
     "вимагає академічної/олімпіадної підготовки"),

    # Класи, перевірені раніше при ручному доборі.
    (r"\bphd\b|кандидат наук|докторськ", "вимагає наукового ступеня"),
    # ⚠ Цей сигнал застосовується лише тоді, коли Python у тексті ВІДСУТНІЙ.
    # Інакше він ловить згадку, а не вимогу: KaaIoT (SRE/DevOps) згадує Java
    # як додатки, збірку яких треба підтримувати, — і сам при цьому вимагає
    # Python. Згадка мови ≠ мова позиції.
    (r"\.net\b|c#|\bjava\b(?!script)|\bphp\b|\bruby\b|golang",
     "основна мова — не Python"),
    (r"1c|1с|бітрікс|bitrix|wordpress|битрикс", "платформа, з якою не працював"),
    (r"team\s*lead|тимлід|керівник\s+команди|engineering\s+manager",
     "керівна позиція: 1 рік комерційного досвіду сюди не стане"),
)


#  ЧИМ ЦЕ НЕ Є — сигнали, які читаються з НАЗВИ ПОСАДИ, а не з тексту.
#
#  Розділення принципове. «Docker», «CI/CD», «моніторинг» згадує половина
#  вакансій розробника, і шукати за ними в тексті означає плутати інструмент
#  із професією. Назва посади ж називає професію прямо.
#
#  Знайдено 08.10.2026: KaaIoT «Junior SRE / DevOps Engineer» отримав strong
#  із шістьма збігами (Python, Docker, Linux, PostgreSQL, моніторинг,
#  asyncio) — усі справжні, і все одно це не та робота. Власник пише код,
#  а не супроводжує чужий.
TITLE_STOP_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"devops|\bsre\b|site reliability|infrastructure engineer|системний адмін|sysadmin",
     "DevOps/SRE, а не розробка"),
    (r"\bqa\b|test automation|автоматизац\w* тестуван|тестувальник|quality assurance",
     "тестування, а не розробка"),
    (r"support|helpdesk|технічн\w* підтримк|service desk",
     "підтримка, а не розробка"),
    (r"project manager|product manager|scrum|product owner|бізнес.?аналітик",
     "менеджмент, а не розробка"),
    (r"designer|дизайнер|motion|ux|ui\b", "дизайн"),
    (r"recruiter|sourcer|рекрутер|talent", "рекрутинг"),
    (r"sales|media buyer|маркетолог|smm|affiliate", "продажі/маркетинг"),
)


@dataclass
class Match:
    """Оцінка змістовної відповідності."""

    matched: list[str] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    concerns: list[str] = field(default_factory=list)

    @property
    def fit(self) -> str:
        """`strong` / `possible` / `weak`.

        Поріг навмисно поблажливий: хибна відмова дорожча за хибне «подивись».
        Відкинуту вакансію більше ніколи не покажуть, а зайвий перегляд
        коштує хвилину.
        """
        if self.concerns:
            return "weak"
        if len(self.matched) >= 5:
            return "strong"
        # Поріг у два збіги, а не в три: Broscorp, куди подано 08.10.2026, має
        # опис на 1190 символів і дає рівно два. Коротке оголошення фізично не
        # може дати багато збігів, і карати його за це означало б відсіювати
        # вакансії за багатослівністю рекрутера.
        return "possible" if len(self.matched) >= 2 else "weak"


def screen(text: str, title: str | None = None) -> Match:
    """Оцінити вакансію за її текстом і назвою посади.

    `title` окремим параметром навмисно: частина сигналів має сенс лише в
    назві. Професія названа в заголовку, а в тексті лежать інструменти —
    і вони в розробника й у DevOps-інженера значною мірою ті самі.
    """
    low = (text or "").lower()
    result = Match()

    for pattern, why in TITLE_STOP_PATTERNS:
        if re.search(pattern, (title or "").lower(), re.I):
            result.concerns.append(why)

    for name, variants in HAVE.items():
        if any(v in low for v in variants):
            result.matched.append(name)

    for name, note in GAPS.items():
        if name.lower() in low:
            result.gaps.append(f"{name}: {note}")

    has_python = any(v in low for v in HAVE["Python"])

    # Відсутність Python — не дрібниця, а зміна професії.
    #
    # Знайдено 08.10.2026 на вакансії «Node.js Developer», яка набрала ШІСТЬ
    # збігів і стала `strong`: PostgreSQL, Docker, REST API, async/await,
    # інтеграції, TypeScript. Усі шість — інфраструктура, спільна для будь-якої
    # backend-вакансії; жоден не свідчить про придатність, коли основної мови
    # немає. Рахувати їх без Python означало б пропонувати будь-який backend.
    if not has_python:
        result.concerns.append("у тексті немає Python — інша мова позиції")

    for pattern, why in STOP_PATTERNS:
        if why == "основна мова — не Python" and has_python:
            # Вакансія вимагає Python і згадує іншу мову — це контекст
            # (суміжні системи, збірка, legacy), а не заміна мови позиції.
            continue
        if re.search(pattern, low, re.I):
            result.concerns.append(why)

    return result
