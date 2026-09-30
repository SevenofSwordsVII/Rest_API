"""Database seed script for local development, demonstration, and quickstart walkthrough."""

import asyncio
import logging
import sys

from sqlalchemy import select

from src.core.database import async_session_factory
from src.core.security import hash_password
from src.domains.audit.models import AuditLogEntry
from src.domains.auth.models import User
from src.domains.notifications.models import Notification
from src.domains.organizations.models import Organization, OrganizationMembership, RoleEnum
from src.domains.work_management.models import (
    Comment,
    Project,
    ProjectStatus,
    Task,
    TaskPriority,
    TaskStatus,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("seed")


async def seed() -> None:
    """Idempotently seed development data into the database."""
    default_password = hash_password("SecurePassword123!")

    async with async_session_factory() as session:
        # Check if already seeded
        existing_alice = (
            await session.execute(select(User).where(User.email == "alice@example.com"))
        ).scalar_one_or_none()

        if existing_alice is not None:
            logger.info("Development data already exists in database. Skipping seeding.")
            return

        logger.info("Seeding development users...")
        alice = User(
            email="alice@example.com",
            hashed_password=default_password,
            full_name="Alice Smith",
            is_active=True,
        )
        bob = User(
            email="bob@example.com",
            hashed_password=default_password,
            full_name="Bob Jones",
            is_active=True,
        )
        charlie = User(
            email="charlie@example.com",
            hashed_password=default_password,
            full_name="Charlie Brown",
            is_active=True,
        )
        eve = User(
            email="eve@example.com",
            hashed_password=default_password,
            full_name="Eve Mallory",
            is_active=True,
        )
        session.add_all([alice, bob, charlie, eve])
        await session.flush()

        logger.info("Seeding organizations and memberships...")
        acme_org = Organization(
            name="Acme Corp",
            slug="acme-corp",
        )
        evil_org = Organization(
            name="Evil Corp",
            slug="evil-corp",
        )
        session.add_all([acme_org, evil_org])
        await session.flush()

        memberships = [
            OrganizationMembership(
                organization_id=acme_org.id,
                user_id=alice.id,
                role=RoleEnum.OWNER,
            ),
            OrganizationMembership(
                organization_id=acme_org.id,
                user_id=bob.id,
                role=RoleEnum.MEMBER,
            ),
            OrganizationMembership(
                organization_id=acme_org.id,
                user_id=charlie.id,
                role=RoleEnum.VIEWER,
            ),
            OrganizationMembership(
                organization_id=evil_org.id,
                user_id=eve.id,
                role=RoleEnum.OWNER,
            ),
        ]
        session.add_all(memberships)
        await session.flush()

        logger.info("Seeding projects...")
        project_alpha = Project(
            organization_id=acme_org.id,
            name="Project Alpha",
            description="Core product initiative for scalable work management",
            status=ProjectStatus.ACTIVE,
            created_by=alice.id,
        )
        project_beta = Project(
            organization_id=acme_org.id,
            name="Project Beta",
            description="Infrastructure upgrade and observability pipeline",
            status=ProjectStatus.ACTIVE,
            created_by=alice.id,
        )
        session.add_all([project_alpha, project_beta])
        await session.flush()

        logger.info("Seeding tasks...")
        task_auth = Task(
            project_id=project_alpha.id,
            title="Implement OAuth2 & JWT Refresh Token Rotation",
            description="Deliver secure token pair lifecycle with reuse detection",
            status=TaskStatus.IN_PROGRESS,
            priority=TaskPriority.HIGH,
            created_by=alice.id,
            assignee_id=bob.id,
        )
        task_db = Task(
            project_id=project_alpha.id,
            title="Configure PostgreSQL 16 & Asyncpg Connection Pool",
            description="Establish robust database engine with health checks",
            status=TaskStatus.DONE,
            priority=TaskPriority.MEDIUM,
            created_by=alice.id,
            assignee_id=alice.id,
        )
        task_audit = Task(
            project_id=project_alpha.id,
            title="Implement Immutable Audit Logging",
            description="Capture security-critical mutations into audit_log_entry table",
            status=TaskStatus.TODO,
            priority=TaskPriority.LOW,
            created_by=alice.id,
            assignee_id=None,
        )
        session.add_all([task_auth, task_db, task_audit])
        await session.flush()

        logger.info("Seeding task comments...")
        comment_1 = Comment(
            task_id=task_auth.id,
            author_id=alice.id,
            content="Bob, please make sure token families are revoked upon replay detection.",
        )
        comment_2 = Comment(
            task_id=task_auth.id,
            author_id=bob.id,
            content="Working on initial schemas and atomic row-level update now.",
        )
        session.add_all([comment_1, comment_2])
        await session.flush()

        logger.info("Seeding notifications...")
        notification_bob = Notification(
            user_id=bob.id,
            event_type="task.assigned",
            payload={
                "task_id": str(task_auth.id),
                "title": task_auth.title,
                "project_id": str(project_alpha.id),
                "actor_id": str(alice.id),
            },
            is_read=False,
        )
        session.add(notification_bob)

        logger.info("Seeding audit log entries...")
        audit_entries = [
            AuditLogEntry(
                organization_id=acme_org.id,
                actor_id=alice.id,
                action="org.created",
                target_resource=f"org:{acme_org.id}",
                metadata_={"name": acme_org.name, "slug": acme_org.slug},
            ),
            AuditLogEntry(
                organization_id=acme_org.id,
                actor_id=alice.id,
                action="org.member_added",
                target_resource=f"user:{bob.id}",
                metadata_={"role": RoleEnum.MEMBER.value, "email": bob.email},
            ),
            AuditLogEntry(
                organization_id=acme_org.id,
                actor_id=alice.id,
                action="project.created",
                target_resource=f"project:{project_alpha.id}",
                metadata_={"name": project_alpha.name},
            ),
        ]
        session.add_all(audit_entries)

        await session.commit()
        logger.info("Database seeding completed successfully.")
        logger.info("Accounts created (password for all: SecurePassword123!):")
        logger.info("  Alice (Owner):   alice@example.com")
        logger.info("  Bob (Member):    bob@example.com")
        logger.info("  Charlie (Viewer): charlie@example.com")
        logger.info("  Eve (Evil Org):  eve@example.com")


def main() -> None:
    """CLI entrypoint."""
    try:
        asyncio.run(seed())
    except Exception as exc:
        logger.error("Seeding failed: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
