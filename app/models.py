"""Модель предметної області.

Ядро системи — ДВІ таблиці: `application` (що я надіслав) і `application_event`
(що з цим сталося). Усе інше — збір вакансій, скринер, сповіщення — добудовується
навколо них і без них не має сенсу.

Чому історія статусів окремою таблицею, а не полем `status` у подачі:
поле зберігає лише останній стан і стирає найцінніше — КОЛИ саме рекрутер
переглянув відгук і скільки він мовчав до цього. Саме ці інтервали й відповідають
на питання «резюме не доходить до людини» проти «доходить і не чіпляє».
"""

from __future__ import annotations

import enum
from datetime import date, datetime

from sqlalchemy import (
    Date, DateTime, Enum, ForeignKey, Index, Integer, String, Text, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Channel(str, enum.Enum):
    """Яким каналом подано. Канал — частина воронки: та сама вакансія,
    подана через сайт і через пряме письмо, має різну долю."""

    djinni = "djinni"
    dou = "dou"
    telegram = "telegram"
    email = "email"
    linkedin = "linkedin"
    referral = "referral"
    other = "other"


#  Канали, які СЕРЕД СЕБЕ повідомляють про долю подачі.
#
#  Djinni показує, чи відгук переглянули й чи відмовили. DOU не показує нічого —
#  лише факт подачі. Це не дрібниця інтерфейсу: без цього розрізнення журнал
#  виводив «29 днів тиші» для подач на DOU, і виглядало це як ігнорування
#  рекрутером, хоча насправді там просто НЕМАЄ механізму, який міг би щось
#  повідомити.
#
#  Плутати «нам не відповіли» з «канал не вміє відповідати» — рівно та помилка,
#  проти якої побудована решта системи: мовчання мусить означати одне й те саме
#  скрізь, де його рахують.
REPORTS_STATUS: frozenset[str] = frozenset({"djinni"})


class Status(str, enum.Enum):
    """Стани подачі.

    `ghosted` — не окремий стан, а відсутність будь-чого після `sent`; ставиться
    вручну або автоматично за таймаутом, щоб мовчанка була ВИДИМОЮ, а не просто
    відсутністю рядків. Саме мовчанка і є типовим результатом, тому вона мусить
    потрапляти в статистику, а не випадати з неї.
    """

    sent = "sent"
    # Автовідповідь: доводить, що лист дійшов і його обробила автоматика —
    # і НЕ доводить, що його бачила людина. Окремий стан, бо ховати подію
    # під «надіслано» означає втрачати інформацію, а зараховувати як
    # «переглянуто» — брехати у воронці. Djinni ставить під такими
    # повідомленнями позначку «Це автоматична відповідь».
    auto_reply = "auto_reply"
    viewed = "viewed"
    rejected = "rejected"
    invited = "invited"
    interview = "interview"
    test_task = "test_task"
    offer = "offer"
    withdrawn = "withdrawn"
    ghosted = "ghosted"


# Наскільки далеко стан просунув подачу. Потрібно для випадку, коли кілька
# подій мають ОДНУ дату: на Djinni вік показано з точністю до місяця, тож
# «надіслано» і «відмовлено» нерідко отримують однакове число. Без цієї шкали
# переможцем ставав запис із більшим id — тобто порядок вставки, — і подача
# з відмовою показувалась як «надіслано». Журнал тоді бреше саме там, де він
# найпотрібніший.
_ADVANCE: dict[str, int] = {
    "ghosted": -1,
    "sent": 0,
    "auto_reply": 1,
    "viewed": 2,
    "test_task": 3,
    "invited": 4,
    "interview": 5,
    # Кінцеві стани переважають усе: далі подача не рухається.
    "withdrawn": 8,
    "rejected": 9,
    "offer": 10,
}


class Application(Base):
    __tablename__ = "application"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    company: Mapped[str] = mapped_column(String(200))
    position: Mapped[str] = mapped_column(String(300))
    url: Mapped[str | None] = mapped_column(String(1000))

    channel: Mapped[Channel] = mapped_column(Enum(Channel, name="channel"))
    applied_on: Mapped[date] = mapped_column(Date)

    # Яка саме версія резюме пішла. Без цього неможливо порівняти варіанти —
    # а порівняти їх і є сенс усієї вправи.
    cv_version: Mapped[str | None] = mapped_column(String(100))
    cover_letter: Mapped[bool] = mapped_column(default=False)

    salary_asked: Mapped[int | None] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    events: Mapped[list["ApplicationEvent"]] = relationship(
        back_populates="application",
        cascade="all, delete-orphan",
        order_by="ApplicationEvent.occurred_on",
    )

    __table_args__ = (
        Index("ix_application_applied_on", "applied_on"),
        Index("ix_application_channel", "channel"),
    )

    @property
    def current_status(self) -> Status:
        """Останній стан за датою події. Без подій подача вважається надісланою."""
        if not self.events:
            return Status.sent
        return max(
            self.events,
            key=lambda e: (e.occurred_on, _ADVANCE.get(e.status.value, 0), e.id or 0),
        ).status

    @property
    def silence_is_meaningful(self) -> bool:
        """Чи має сенс рахувати тишу по цій подачі.

        Має, якщо канал сам повідомляє про долю відгуку (Djinni), АБО якщо
        по подачі вже є хоч одна подія понад «надіслано» — тобто зворотний
        зв'язок звідкись надходить, хай і внесений руками.
        """
        if self.channel.value in REPORTS_STATUS:
            return True
        return any(e.status is not Status.sent for e in self.events)

    @property
    def days_silent(self) -> int | None:
        """Скільки днів минуло від останньої події.

        `None` означає не «нуль днів», а «питання не має сенсу»: канал мовчить
        не тому, що про вас забули, а тому, що говорити він не вміє.
        """
        if not self.silence_is_meaningful:
            return None
        if not self.events:
            return (date.today() - self.applied_on).days
        last = max(e.occurred_on for e in self.events)
        return (date.today() - last).days


class ApplicationEvent(Base):
    __tablename__ = "application_event"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    application_id: Mapped[int] = mapped_column(
        ForeignKey("application.id", ondelete="CASCADE")
    )

    status: Mapped[Status] = mapped_column(Enum(Status, name="status"))
    occurred_on: Mapped[date] = mapped_column(Date)
    note: Mapped[str | None] = mapped_column(Text)

    # Звідки взято подію: "manual" або "browser-sync". Потрібне, щоб відрізняти
    # те, що власник вписав по пам'яті, від того, що прочитано зі сторінки.
    origin: Mapped[str] = mapped_column(String(40), default="manual")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    application: Mapped[Application] = relationship(back_populates="events")

    __table_args__ = (Index("ix_event_application", "application_id", "occurred_on"),)
