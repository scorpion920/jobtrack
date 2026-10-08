"""Кнопки дій у сповіщеннях: стан опитування і позначка «не цікавить»

Кожна відмова оператора ставала правилом скринера — за один вечір 08.10.2026
так з'явилось п'ять: no-code, академічна математика, DevOps, Oracle, гібрид.
Досі це коштувало окремої розмови; кнопка робить це дотиком.

Revision ID: 0007_bot_actions
Revises: 0006_application_vacancy
"""
import sqlalchemy as sa
from alembic import op

revision = "0007_bot_actions"
down_revision = "0006_application_vacancy"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("vacancy", sa.Column("dismissed", sa.Boolean(), nullable=False,
                                       server_default=sa.false()))
    op.create_table(
        "bot_state",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("update_offset", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("bot_state")
    op.drop_column("vacancy", "dismissed")
