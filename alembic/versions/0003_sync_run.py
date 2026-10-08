"""Журнал прогонів збирача статусів

Знадобився одразу після встановлення userscript 08.10.2026: скрипт віддано
браузеру (видно в логах), а даних немає — і неможливо сказати, чи він не
запускався, чи запустився й нічого не побачив. Обидва стани виглядали як
тиша, тому шукати поламку не було де.

Таблиця робить ці два стани різними: порожній прогін теж пишеться.

Revision ID: 0003_sync_run
Revises: 0002_auto_reply
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003_sync_run"
down_revision = "0002_auto_reply"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sync_run",
        sa.Column("id", sa.Integer(), nullable=False),
        # create_type=False — тип `channel` уже створено міграцією 0001.
        # Без цього прапорця SQLAlchemy випускає власний CREATE TYPE і накат
        # падає на «type already exists»; урок із 0001, закріплений тестом
        # app/tests/test_migration_enum.py.
        sa.Column("source", postgresql.ENUM(name="channel", create_type=False), nullable=False),
        sa.Column("received", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("events_added", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("origin", sa.String(length=40), nullable=False, server_default="unknown"),
        sa.Column("dry_run", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sync_run_at", "sync_run", ["at"])


def downgrade() -> None:
    op.drop_index("ix_sync_run_at", table_name="sync_run")
    op.drop_table("sync_run")
