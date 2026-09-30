"""Create comment table for task collaboration.

Revision ID: 004_comments_table
Revises: 003_work_management_tables
Create Date: 2026-09-29 03:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "004_comments_table"
down_revision: str | None = "003_work_management_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "comment",
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("author_id", sa.Uuid(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["author_id"],
            ["user.id"],
            name=op.f("fk_comment_author_id_user"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["task.id"],
            name=op.f("fk_comment_task_id_task"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_comment")),
    )
    op.create_index(
        op.f("ix_comment_author_id"),
        "comment",
        ["author_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_comment_task_id"),
        "comment",
        ["task_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_comment_task_id"), table_name="comment")
    op.drop_index(op.f("ix_comment_author_id"), table_name="comment")
    op.drop_table("comment")
