"""Збір вакансій: канали, вакансії, сире тіло

Друга половина вимірювання. Журнал подач відповідає на питання «що сталося з
тим, що я надіслав»; цей шар — на питання «а що взагалі є і чи варто було».

Три таблиці, а не одна:
  source      — канал живе в БД, щоб додати його можна було записом, а не релізом
  vacancy     — нормалізоване, бо за ознаками ФІЛЬТРУЮТЬ, а фільтр по JSON
                означає або індекс на кожен ключ, або повний перебір
  vacancy_raw — сире, щоб виправлений розбір проганявся по збереженому, а не
                по тому, що майданчик показує сьогодні

Revision ID: 0004_vacancies
Revises: 0003_sync_run
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004_vacancies"
down_revision = "0003_sync_run"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "source",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(length=80), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("label", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("params", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_found", sa.Integer(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key"),
    )

    op.create_table(
        "vacancy",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source_key", sa.String(length=80), nullable=False),
        sa.Column("external_id", sa.String(length=80), nullable=False),
        sa.Column("url", sa.String(length=600), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("company", sa.String(length=200), nullable=False),
        sa.Column("company_norm", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("title_norm", sa.String(length=300), nullable=False, server_default=""),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("format", sa.String(length=20), nullable=True),
        sa.Column("years_required", sa.Integer(), nullable=True),
        sa.Column("english", sa.String(length=20), nullable=True),
        sa.Column("part_time", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("location", sa.String(length=200), nullable=True),
        sa.Column("replies", sa.Integer(), nullable=True),
        sa.Column("views", sa.Integer(), nullable=True),
        sa.Column("salary_tier", sa.Integer(), nullable=True),
        sa.Column("raw_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("first_seen", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("last_seen", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    # Перший рівень дедуплікації тримає СХЕМА, а не код: помилка в адаптері
    # не повинна мати можливості завести ту саму вакансію двічі.
    op.create_index("uq_vacancy_source_external", "vacancy",
                    ["source_key", "external_id"], unique=True)
    op.create_index("ix_vacancy_posted", "vacancy", ["posted_at"])
    op.create_index("ix_vacancy_dedup", "vacancy", ["company_norm", "title_norm"])

    op.create_table(
        "vacancy_raw",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("vacancy_id", sa.Integer(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("fetched_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["vacancy_id"], ["vacancy.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("vacancy_id"),
    )


def downgrade() -> None:
    op.drop_table("vacancy_raw")
    op.drop_index("ix_vacancy_dedup", table_name="vacancy")
    op.drop_index("ix_vacancy_posted", table_name="vacancy")
    op.drop_index("uq_vacancy_source_external", table_name="vacancy")
    op.drop_table("vacancy")
    op.drop_table("source")
