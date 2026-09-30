# Data Model: Project & Work Management Platform

**Date**: 2026-09-29  
**Branch**: `master` (`001-work-management-platform`)  
**Status**: Completed (Phase 1)

---

## 1. Relational Schema & Entity Specifications

All tables follow PostgreSQL snake_case conventions, singular naming, and use the standardized metadata constraint naming convention:
- Primary Keys: `UUID` generated via `uuid4()` on server/database.
- Timestamps: Timezone-aware UTC `DateTime(timezone=True)`.
- Soft Deletion: Nullable `deleted_at: DateTime(timezone=True)`.

### Entity Diagram (ASCII)

```text
+-------------------+       1..*       +------------------------------------+
|       User        | <--------------+ |       OrganizationMembership       |
| id: UUID (PK)     |                  | id: UUID (PK)                      |
| email: str (UQ)   |                  | user_id: UUID (FK -> User)         |
| hashed_password   |                  | organization_id: UUID (FK -> Org)  |
| is_active: bool   |                  | role: RoleEnum (Owner/Admin/...)   |
| created_at (UTC)  |                  | created_at / updated_at (UTC)      |
| updated_at (UTC)  |                  +------------------------------------+
+-------------------+                                     ^
          ^                                               | 1..*
          | 1                                             |
          |                                    +--------------------+
          +-------------+                      |    Organization    |
          |             |                      | id: UUID (PK)      |
          | 1..*        | 1..*                 | name: str          |
+-------------------+ +-------------------+    | slug: str (UQ)     |
|   RefreshToken    | |   AuditLogEntry   |    | deleted_at (UTC)   |
| id: UUID (PK)     | | id: UUID (PK)     |    | created_at (UTC)   |
| user_id: UUID(FK) | | actor_id: UUID    |    | updated_at (UTC)   |
| token_hash: str   | | org_id: UUID      |    +--------------------+
| family_id: UUID   | | action: str       |               |
| is_consumed: bool | | target_id: UUID   |               | 1..*
| expires_at (UTC)  | | metadata: JSONB   |               v
| created_at (UTC)  | | ip_address: str   |    +--------------------+
+-------------------+ | created_at (UTC)  |    |      Project       |
                      +-------------------+    | id: UUID (PK)      |
                                               | org_id: UUID (FK)  |
                                               | name: str          |
                                               | description: str   |
                                               | status: Enum       |
                                               | created_by: UUID   |
                                               | deleted_at (UTC)   |
                                               | created_at (UTC)   |
                                               | updated_at (UTC)   |
                                               +--------------------+
                                                          |
                                                          | 1..*
                                                          v
                                               +--------------------+
                                               |        Task        |
                                               | id: UUID (PK)      |
                                               | project_id: UUID   |
                                               | title: str         |
                                               | description: str   |
                                               | status: Enum       |
                                               | priority: Enum     |
                                               | due_date (UTC)     |
                                               | created_by: UUID   |
                                               | assignee_id: UUID  |
                                               | deleted_at (UTC)   |
                                               | created_at (UTC)   |
                                               | updated_at (UTC)   |
                                               +--------------------+
                                                      |        |
                                               1..*   |        | 1..*
                                      +---------------+        +---------------+
                                      v                                        v
                            +--------------------+                   +--------------------+
                            |      Comment       |                   |    Notification    |
                            | id: UUID (PK)      |                   | id: UUID (PK)      |
                            | task_id: UUID (FK) |                   | user_id: UUID (FK) |
                            | author_id: UUID(FK)|                   | event_type: str    |
                            | content: text      |                   | is_read: bool      |
                            | created_at (UTC)   |                   | payload: JSONB     |
                            | updated_at (UTC)   |                   | created_at (UTC)   |
                            +--------------------+                   +--------------------+
```

---

## 2. Table Definitions & Constraints

### 2.1 `user`
Represents registered users in the platform.

| Column | Type | Nullable | Constraints & Defaults | Description |
|---|---|---|---|---|
| `id` | `UUID` | No | Primary Key, `default=uuid4` | Unique user identifier |
| `email` | `VARCHAR(255)` | No | Unique, Index, Lowercase | User email used for authentication |
| `hashed_password` | `VARCHAR(255)` | No | — | Argon2id password hash |
| `full_name` | `VARCHAR(128)` | Yes | — | Optional user display name |
| `is_active` | `BOOLEAN` | No | `default=True` | Active status (account lockout flag) |
| `is_superuser` | `BOOLEAN` | No | `default=False` | System-wide administrative access |
| `created_at` | `TIMESTAMPTZ` | No | `default=utcnow` | Registration timestamp |
| `updated_at` | `TIMESTAMPTZ` | No | `default=utcnow, onupdate=utcnow` | Last profile update timestamp |

### 2.2 `refresh_token`
Stores active and consumed refresh token states for multi-device concurrent sessions and token rotation.

| Column | Type | Nullable | Constraints & Defaults | Description |
|---|---|---|---|---|
| `id` | `UUID` | No | Primary Key, `default=uuid4` | Unique record ID |
| `user_id` | `UUID` | No | FK → `user.id` ON DELETE CASCADE, Index | Owning user |
| `token_hash` | `VARCHAR(64)` | No | Unique, Index | SHA-256 hash of plaintext refresh token |
| `family_id` | `UUID` | No | Index | Token family identifier for rotation tracking |
| `is_consumed` | `BOOLEAN` | No | `default=False`, Index | True once exchanged for a new token pair |
| `is_revoked` | `BOOLEAN` | No | `default=False`, Index | True if session explicitly logged out |
| `user_agent` | `VARCHAR(255)` | Yes | — | Client User-Agent for session management |
| `ip_address` | `VARCHAR(45)` | Yes | — | Client IP at token generation |
| `expires_at` | `TIMESTAMPTZ` | No | Index | Refresh token expiration timestamp (e.g. +7 days) |
| `created_at` | `TIMESTAMPTZ` | No | `default=utcnow` | Issuance timestamp |

### 2.3 `organization`
Top-level multi-tenant isolation container.

| Column | Type | Nullable | Constraints & Defaults | Description |
|---|---|---|---|---|
| `id` | `UUID` | No | Primary Key, `default=uuid4` | Organization unique ID |
| `name` | `VARCHAR(128)` | No | — | Display name |
| `slug` | `VARCHAR(64)` | No | Unique, Index | URL-safe identifier (e.g., `acme-corp`) |
| `deleted_at` | `TIMESTAMPTZ` | Yes | Index | Soft deletion timestamp |
| `created_at` | `TIMESTAMPTZ` | No | `default=utcnow` | Creation timestamp |
| `updated_at` | `TIMESTAMPTZ` | No | `default=utcnow, onupdate=utcnow` | Update timestamp |

### 2.4 `organization_membership`
Associates users with organizations and assigns fixed RBAC roles.

| Column | Type | Nullable | Constraints & Defaults | Description |
|---|---|---|---|---|
| `id` | `UUID` | No | Primary Key, `default=uuid4` | Membership record ID |
| `user_id` | `UUID` | No | FK → `user.id` ON DELETE CASCADE, Index | Associated user |
| `organization_id`| `UUID` | No | FK → `organization.id` ON DELETE CASCADE, Index | Associated organization |
| `role` | `VARCHAR(32)` | No | Enum: `OWNER`, `ADMIN`, `MEMBER`, `VIEWER` | Assigned RBAC role |
| `created_at` | `TIMESTAMPTZ` | No | `default=utcnow` | Membership start timestamp |
| `updated_at` | `TIMESTAMPTZ` | No | `default=utcnow, onupdate=utcnow` | Role change timestamp |

- **Unique Constraint**: `uq_org_membership_user_org` (`organization_id`, `user_id`).

### 2.5 `project`
Workspace project belonging to an organization.

| Column | Type | Nullable | Constraints & Defaults | Description |
|---|---|---|---|---|
| `id` | `UUID` | No | Primary Key, `default=uuid4` | Project unique ID |
| `organization_id`| `UUID` | No | FK → `organization.id` ON DELETE CASCADE, Index | Parent organization |
| `name` | `VARCHAR(128)` | No | — | Project title |
| `description` | `TEXT` | Yes | — | Markdown/plain text description |
| `status` | `VARCHAR(32)` | No | Enum: `ACTIVE`, `ARCHIVED`, `COMPLETED`, `default=ACTIVE` | Project lifecycle status |
| `created_by` | `UUID` | No | FK → `user.id` ON DELETE RESTRICT | Project creator |
| `deleted_at` | `TIMESTAMPTZ` | Yes | Index | Soft deletion timestamp |
| `created_at` | `TIMESTAMPTZ` | No | `default=utcnow` | Creation timestamp |
| `updated_at` | `TIMESTAMPTZ` | No | `default=utcnow, onupdate=utcnow` | Update timestamp |

- **Index**: `ix_project_org_status` (`organization_id`, `status`) where `deleted_at IS NULL`.

### 2.6 `task`
Actionable work item inside a project.

| Column | Type | Nullable | Constraints & Defaults | Description |
|---|---|---|---|---|
| `id` | `UUID` | No | Primary Key, `default=uuid4` | Task unique ID |
| `project_id` | `UUID` | No | FK → `project.id` ON DELETE CASCADE, Index | Parent project |
| `title` | `VARCHAR(255)` | No | — | Task title |
| `description` | `TEXT` | Yes | — | Markdown/plain text details |
| `status` | `VARCHAR(32)` | No | Enum: `TODO`, `IN_PROGRESS`, `IN_REVIEW`, `DONE`, `default=TODO` | Task state |
| `priority` | `VARCHAR(32)` | No | Enum: `LOW`, `MEDIUM`, `HIGH`, `URGENT`, `default=MEDIUM` | Urgency tier |
| `due_date` | `TIMESTAMPTZ` | Yes | Index | Optional deadline |
| `created_by` | `UUID` | No | FK → `user.id` ON DELETE RESTRICT | Task creator |
| `assignee_id` | `UUID` | Yes | FK → `user.id` ON DELETE SET NULL, Index | Assigned member (0 or 1) |
| `deleted_at` | `TIMESTAMPTZ` | Yes | Index | Soft deletion timestamp |
| `created_at` | `TIMESTAMPTZ` | No | `default=utcnow` | Creation timestamp |
| `updated_at` | `TIMESTAMPTZ` | No | `default=utcnow, onupdate=utcnow` | Update timestamp |

- **Composite Indexes**:
  - `ix_task_project_status` (`project_id`, `status`) where `deleted_at IS NULL`.
  - `ix_task_project_assignee` (`project_id`, `assignee_id`) where `deleted_at IS NULL`.

### 2.7 `comment`
Discussion entry linked to a task.

| Column | Type | Nullable | Constraints & Defaults | Description |
|---|---|---|---|---|
| `id` | `UUID` | No | Primary Key, `default=uuid4` | Comment unique ID |
| `task_id` | `UUID` | No | FK → `task.id` ON DELETE CASCADE, Index | Parent task |
| `author_id` | `UUID` | No | FK → `user.id` ON DELETE RESTRICT, Index | Comment author |
| `content` | `TEXT` | No | — | Message content |
| `created_at` | `TIMESTAMPTZ` | No | `default=utcnow` | Post timestamp |
| `updated_at` | `TIMESTAMPTZ` | No | `default=utcnow, onupdate=utcnow` | Edit timestamp |

- **Index**: `ix_comment_task_created` (`task_id`, `created_at ASC`).

### 2.8 `notification`
In-app user notification records.

| Column | Type | Nullable | Constraints & Defaults | Description |
|---|---|---|---|---|
| `id` | `UUID` | No | Primary Key, `default=uuid4` | Notification ID |
| `user_id` | `UUID` | No | FK → `user.id` ON DELETE CASCADE, Index | Target user recipient |
| `event_type` | `VARCHAR(64)` | No | Index | Event slug (e.g. `task.assigned`, `comment.created`) |
| `is_read` | `BOOLEAN` | No | `default=False`, Index | Read/unread flag |
| `payload` | `JSONB` | No | `default={}` | Context metadata (task title, author name, link) |
| `created_at` | `TIMESTAMPTZ` | No | `default=utcnow`, Index | Event timestamp |

- **Index**: `ix_notification_user_unread` (`user_id`, `is_read`, `created_at DESC`).

### 2.9 `audit_log_entry`
Immutable historical log of security and administrative operations.

| Column | Type | Nullable | Constraints & Defaults | Description |
|---|---|---|---|---|
| `id` | `UUID` | No | Primary Key, `default=uuid4` | Immutable log entry ID |
| `organization_id`| `UUID` | Yes | Index | Associated organization (nullable for auth events) |
| `actor_id` | `UUID` | Yes | Index | Performing user (nullable for unauth/system actions)|
| `action` | `VARCHAR(64)` | No | Index | Operation code (`auth.login_failed`, `auth.password_changed`, `task.deleted`)|
| `target_resource`| `VARCHAR(64)` | No | — | Format: `<resource_type>:<uuid>` |
| `metadata` | `JSONB` | No | `default={}` | Sanitized audit context (no secrets/passwords) |
| `ip_address` | `VARCHAR(45)` | Yes | — | Client IP |
| `user_agent` | `VARCHAR(255)` | Yes | — | Client User-Agent |
| `created_at` | `TIMESTAMPTZ` | No | `default=utcnow`, Index | Immutable occurrence timestamp |

- **Index**: `ix_audit_org_created` (`organization_id`, `created_at DESC`).

---

## 3. State Machines & Enums

### 3.1 Role Hierarchy & Permissions
```text
           [OWNER]   --> Full org control + ownership transfer + org deletion
              |
           [ADMIN]   --> Member management, project creation/deletion, task management
              |
          [MEMBER]   --> Project creation, task creation/editing, comment posting
              |
          [VIEWER]   --> Read-only access to organization projects, tasks, comments
```

### 3.2 Task Lifecycle State Transitions
```text
 +--------+    assign / start     +-------------+    submit review    +-----------+    complete    +--------+
 |  TODO  | --------------------> | IN_PROGRESS | ------------------> | IN_REVIEW | -------------> |  DONE  |
 +--------+                       +-------------+                     +-----------+                +--------+
     ^                                   |                                  |                           |
     |                                   | reopen                           | request changes           | reopen
     +-----------------------------------+----------------------------------+---------------------------+
```
- Reopening is allowed from `DONE` back to `TODO` or `IN_PROGRESS` by `MEMBER`, `ADMIN`, or `OWNER`.
- Archiving/Soft deleting a task can occur from any state.
