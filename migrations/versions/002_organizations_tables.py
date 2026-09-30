"""Create organization and organization_membership tables for multi-tenancy.

Revision ID: 002_organizations_tables
Revises: 001_auth_tables
Create Date: 2026-09-29 01:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "002_organizations_tables"
down_revision: str | None = "001_auth_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "organization",
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_organization")),
    )
    op.create_index(
        op.f("ix_organization_deleted_at"),
        "organization",
        ["deleted_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_organization_slug"),
        "organization",
        ["slug"],
        unique=True,
    )

    op.create_table(
        "organization_membership",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organization.id"],
            name=op.f("fk_organization_membership_organization_id_organization"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["user.id"],
            name=op.f("fk_organization_membership_user_id_user"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_organization_membership")),
        sa.UniqueConstraint(
            "organization_id",
            "user_id",
            name="uq_organization_membership_user_org",
        ),
    )
    op.create_index(
        op.f("ix_organization_membership_organization_id"),
        "organization_membership",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_organization_membership_user_id"),
        "organization_membership",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_organization_membership_user_id"),
        table_name="organization_membership",
    )
    op.drop_index(
        op.f("ix_organization_membership_organization_id"),
        table_name="organization_membership",
    )
    op.drop_table("organization_membership")
    op.drop_index(op.f("ix_organization_slug"), table_name="organization")
    op.drop_index(op.f("ix_organization_deleted_at"), table_name="organization")
    op.drop_table("organization")
