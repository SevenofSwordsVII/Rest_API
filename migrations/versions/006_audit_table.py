"""Create audit_log_entry table for immutable audit history.

Revision ID: 006_audit_table
Revises: 005_notifications_table
Create Date: 2026-09-29 05:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "006_audit_table"
down_revision: str | None = "005_notifications_table"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "audit_log_entry",
        sa.Column("organization_id", sa.Uuid(), nullable=True),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("target_resource", sa.String(length=64), nullable=False),
        sa.Column(
            "metadata",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.Column("user_agent", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["user.id"],
            name=op.f("fk_audit_log_entry_actor_id_user"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organization.id"],
            name=op.f("fk_audit_log_entry_organization_id_organization"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_log_entry")),
    )
    op.create_index(
        op.f("ix_audit_log_entry_action"),
        "audit_log_entry",
        ["action"],
        unique=False,
    )
    op.create_index(
        op.f("ix_audit_log_entry_actor_id"),
        "audit_log_entry",
        ["actor_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_audit_log_entry_created_at"),
        "audit_log_entry",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_audit_log_entry_organization_id"),
        "audit_log_entry",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_audit_org_created",
        "audit_log_entry",
        ["organization_id", sa.text("created_at DESC")],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_audit_org_created", table_name="audit_log_entry")
    op.drop_index(op.f("ix_audit_log_entry_organization_id"), table_name="audit_log_entry")
    op.drop_index(op.f("ix_audit_log_entry_created_at"), table_name="audit_log_entry")
    op.drop_index(op.f("ix_audit_log_entry_actor_id"), table_name="audit_log_entry")
    op.drop_index(op.f("ix_audit_log_entry_action"), table_name="audit_log_entry")
    op.drop_table("audit_log_entry")
