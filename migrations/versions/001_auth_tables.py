"""Create user and refresh_token tables for authentication.

Revision ID: 001_auth_tables
Revises:
Create Date: 2026-09-29 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "001_auth_tables"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user",
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=128), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("is_superuser", sa.Boolean(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user")),
    )
    op.create_index(op.f("ix_user_email"), "user", ["email"], unique=True)

    op.create_table(
        "refresh_token",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("family_id", sa.Uuid(), nullable=False),
        sa.Column("is_consumed", sa.Boolean(), nullable=False),
        sa.Column("is_revoked", sa.Boolean(), nullable=False),
        sa.Column("user_agent", sa.String(length=255), nullable=True),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["user.id"],
            name=op.f("fk_refresh_token_user_id_user"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_refresh_token")),
    )
    op.create_index(
        op.f("ix_refresh_token_expires_at"),
        "refresh_token",
        ["expires_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_refresh_token_family_id"),
        "refresh_token",
        ["family_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_refresh_token_is_consumed"),
        "refresh_token",
        ["is_consumed"],
        unique=False,
    )
    op.create_index(
        op.f("ix_refresh_token_is_revoked"),
        "refresh_token",
        ["is_revoked"],
        unique=False,
    )
    op.create_index(
        op.f("ix_refresh_token_token_hash"),
        "refresh_token",
        ["token_hash"],
        unique=True,
    )
    op.create_index(
        op.f("ix_refresh_token_user_id"),
        "refresh_token",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_refresh_token_user_id"), table_name="refresh_token")
    op.drop_index(op.f("ix_refresh_token_token_hash"), table_name="refresh_token")
    op.drop_index(op.f("ix_refresh_token_is_revoked"), table_name="refresh_token")
    op.drop_index(op.f("ix_refresh_token_is_consumed"), table_name="refresh_token")
    op.drop_index(op.f("ix_refresh_token_family_id"), table_name="refresh_token")
    op.drop_index(op.f("ix_refresh_token_expires_at"), table_name="refresh_token")
    op.drop_table("refresh_token")
    op.drop_index(op.f("ix_user_email"), table_name="user")
    op.drop_table("user")
