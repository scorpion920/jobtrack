"""Журнал подач: application + application_event

Revision ID: 0001_journal
Revises:
Create Date: 2026-10-08
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001_journal"
down_revision = None
branch_labels = None
depends_on = None

# `create_type=False` — обов'язкове. Без нього SQLAlchemy створює тип ЩЕ РАЗ
# усередині `create_table`, уже після явного `.create(checkfirst=True)` нижче,
# і накат падає на `DuplicateObjectError`. Помилка проявляється лише на чистій
# базі, тому легко доїхати з нею до першого користувача.
CHANNEL = postgresql.ENUM("djinni", "dou", "telegram", "email", "linkedin",
                          "referral", "other", name="channel", create_type=False)
STATUS = postgresql.ENUM("sent", "viewed", "rejected", "invited", "interview",
                         "test_task", "offer", "withdrawn", "ghosted",
                         name="status", create_type=False)


def upgrade() -> None:
    bind = op.get_bind()
    CHANNEL.create(bind, checkfirst=True)
    STATUS.create(bind, checkfirst=True)


    op.create_table(
        "application",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("company", sa.String(200), nullable=False),
        sa.Column("position", sa.String(300), nullable=False),
        sa.Column("url", sa.String(1000)),
        sa.Column("channel", CHANNEL, nullable=False),
        sa.Column("applied_on", sa.Date, nullable=False),
        sa.Column("cv_version", sa.String(100)),
        sa.Column("cover_letter", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("salary_asked", sa.Integer),
        sa.Column("notes", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_application_applied_on", "application", ["applied_on"])
    op.create_index("ix_application_channel", "application", ["channel"])

    op.create_table(
        "application_event",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("application_id", sa.Integer,
                  sa.ForeignKey("application.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", STATUS, nullable=False),
        sa.Column("occurred_on", sa.Date, nullable=False),
        sa.Column("note", sa.Text),
        sa.Column("origin", sa.String(40), nullable=False, server_default="manual"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_event_application", "application_event",
                    ["application_id", "occurred_on"])


def downgrade() -> None:
    op.drop_table("application_event")
    op.drop_table("application")
    bind = op.get_bind()
    STATUS.drop(bind, checkfirst=True)
    CHANNEL.drop(bind, checkfirst=True)
