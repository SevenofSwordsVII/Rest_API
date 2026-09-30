"""Create project and task tables for work management.

Revision ID: 003_work_management_tables
Revises: 002_organizations_tables
Create Date: 2026-09-29 02:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "003_work_management_tables"
down_revision: str | None = "002_organizations_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "project",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["user.id"],
            name=op.f("fk_project_created_by_user"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organization.id"],
            name=op.f("fk_project_organization_id_organization"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_project")),
    )
    op.create_index(
        op.f("ix_project_deleted_at"),
        "project",
        ["deleted_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_project_organization_id"),
        "project",
        ["organization_id"],
        unique=False,
    )

    op.create_table(
        "task",
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("priority", sa.String(length=32), nullable=False),
        sa.Column("due_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("assignee_id", sa.Uuid(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["assignee_id"],
            ["user.id"],
            name=op.f("fk_task_assignee_id_user"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["user.id"],
            name=op.f("fk_task_created_by_user"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["project.id"],
            name=op.f("fk_task_project_id_project"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_task")),
    )
    op.create_index(
        op.f("ix_task_assignee_id"),
        "task",
        ["assignee_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_task_deleted_at"),
        "task",
        ["deleted_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_task_project_id"),
        "task",
        ["project_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_task_project_id"), table_name="task")
    op.drop_index(op.f("ix_task_deleted_at"), table_name="task")
    op.drop_index(op.f("ix_task_assignee_id"), table_name="task")
    op.drop_table("task")
    op.drop_index(op.f("ix_project_organization_id"), table_name="project")
    op.drop_index(op.f("ix_project_deleted_at"), table_name="project")
    op.drop_table("project")
