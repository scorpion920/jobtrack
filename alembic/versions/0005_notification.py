"""Журнал надісланих сповіщень

Один привід — одне повідомлення назавжди. Без цієї таблиці кожен прогін
збору надсилав би те саме знову: вакансія, яка висить тиждень, щогодини
виглядає однаково «новою».

Revision ID: 0005_notification
Revises: 0004_vacancies
"""
import sqlalchemy as sa
from alembic import op

revision = "0005_notification"
down_revision = "0004_vacancies"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notification",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(length=200), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("delivered", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key"),
    )
    op.create_index("ix_notification_created", "notification", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_notification_created", table_name="notification")
    op.drop_table("notification")
