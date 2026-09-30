"""Create notification table for work events.

Revision ID: 005_notifications_table
Revises: 004_comments_table
Create Date: 2026-09-29 04:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "005_notifications_table"
down_revision: str | None = "004_comments_table"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "notification",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "payload",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["user.id"],
            name=op.f("fk_notification_user_id_user"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notification")),
    )
    op.create_index(
        op.f("ix_notification_created_at"),
        "notification",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_notification_event_type"),
        "notification",
        ["event_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_notification_is_read"),
        "notification",
        ["is_read"],
        unique=False,
    )
    op.create_index(
        op.f("ix_notification_user_id"),
        "notification",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_notification_user_unread",
        "notification",
        ["user_id", "is_read", sa.text("created_at DESC")],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_notification_user_unread", table_name="notification")
    op.drop_index(op.f("ix_notification_user_id"), table_name="notification")
    op.drop_index(op.f("ix_notification_is_read"), table_name="notification")
    op.drop_index(op.f("ix_notification_event_type"), table_name="notification")
    op.drop_index(op.f("ix_notification_created_at"), table_name="notification")
    op.drop_table("notification")
