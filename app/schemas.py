"""Схеми запитів і відповідей API."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field

from app.models import Channel, Status


class EventIn(BaseModel):
    status: Status
    occurred_on: date
    note: str | None = None
    origin: str = "manual"


class EventOut(EventIn):
    model_config = ConfigDict(from_attributes=True)
    id: int


class ApplicationIn(BaseModel):
    company: str = Field(min_length=1, max_length=200)
    position: str = Field(min_length=1, max_length=300)
    url: str | None = None
    channel: Channel
    applied_on: date
    cv_version: str | None = None
    cover_letter: bool = False
    salary_asked: int | None = None
    notes: str | None = None


class ApplicationOut(ApplicationIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    events: list[EventOut] = []
    current_status: Status
    days_silent: int | None


class FunnelRow(BaseModel):
    """Один зріз воронки. `reached_*` — скільки подач ДОСЯГЛИ стану хоч раз,
    а не скільки в ньому зараз: інакше відмова після перегляду «з'їдала» б
    факт перегляду, і головне питання лишилося б без відповіді."""

    bucket: str
    sent: int
    viewed: int
    responded: int
    interview: int
    offer: int

    @property
    def view_rate(self) -> float:
        return round(self.viewed / self.sent * 100, 1) if self.sent else 0.0

    @property
    def response_rate(self) -> float:
        return round(self.responded / self.sent * 100, 1) if self.sent else 0.0
