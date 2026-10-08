"""Зв'язок подачі із зібраною вакансією

Прогалина, помічена оператором 08.10.2026: у плані зв'язок був, у схемі — ні.
Через це неможливо відповісти на головні питання циклу: на яку з придатних
вакансій уже подано, і яка конкуренція була на момент подачі.

Зв'язок nullable назавжди: подача могла прийти поштою або бути внесеною до
того, як з'явився канал збору.

Revision ID: 0006_application_vacancy
Revises: 0005_notification
"""
import sqlalchemy as sa
from alembic import op

revision = "0006_application_vacancy"
down_revision = "0005_notification"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("application", sa.Column("vacancy_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_application_vacancy", "application", "vacancy",
                          ["vacancy_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_application_vacancy", "application", ["vacancy_id"])


def downgrade() -> None:
    op.drop_index("ix_application_vacancy", table_name="application")
    op.drop_constraint("fk_application_vacancy", "application", type_="foreignkey")
    op.drop_column("application", "vacancy_id")
