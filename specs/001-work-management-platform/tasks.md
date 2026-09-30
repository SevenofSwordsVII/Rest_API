---
description: "Comprehensive implementation task breakdown for Project & Work Management Platform REST API"
---

# Tasks: Project & Work Management Platform REST API

**Input**: Design documents from `specs/001-work-management-platform/` (`spec.md`, `plan.md`, `research.md`, `data-model.md`, `contracts/openapi.yaml`, `quickstart.md`)  
**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/openapi.yaml`  
**Tests**: Automated tests are mandatory per Constitution Principle V and Specification Section 25.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project packaging, dependencies, environment, and development tooling.

- [x] T001 Create project directories per plan: `src/core/`, `src/domains/`, `migrations/versions/`, `tests/unit/`, `tests/integration/`, `tests/contract/`
- [x] T002 [P] Initialize `pyproject.toml` with Python >=3.12, FastAPI >=0.115.0, Pydantic >=2.9.0, pydantic-settings >=2.5.0, SQLAlchemy >=2.0.35, asyncpg >=0.29.0, Alembic >=1.13.3, PyJWT >=2.9.0, argon2-cffi >=23.1.0, uvicorn >=0.30.0, ruff >=0.6.8, mypy >=1.11.0, pytest >=8.3.0, pytest-asyncio >=0.24.0, httpx >=0.27.2
- [x] T003 [P] Configure code quality rules in `pyproject.toml` (Ruff line length 100, target python 3.12, import sorting; Mypy strict mode with `disallow_untyped_defs=True`)
- [x] T004 [P] Create `.env.example` defining `ENVIRONMENT=local`, `DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/rest_db`, `SECRET_KEY=change_me_to_a_secure_random_string_32_chars`, `ALGORITHM=HS256`, `ACCESS_TOKEN_EXPIRE_MINUTES=15`, `REFRESH_TOKEN_EXPIRE_DAYS=7`
- [x] T005 [P] Create `docker-compose.yml` defining PostgreSQL 16 Alpine container with healthcheck and persistent volume mapping

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core architectural infrastructure that MUST be completed before any domain story begins.

- [x] T006 Implement configuration loader in `src/core/config.py` using `pydantic-settings.BaseSettings` with strict env validation and database URL parser
- [x] T007 Implement async database engine, session factory (`expire_on_commit=False`), metadata naming convention, and `get_db()` async dependency in `src/core/database.py`
- [x] T008 Configure Alembic environment for async SQLAlchemy in `alembic.ini` and `migrations/env.py` using target metadata
- [x] T009 [P] Implement password hashing utilities (Argon2id hashing and verification) and JWT helpers (`encode_jwt`, `decode_jwt` with PyJWT) in `src/core/security.py`
- [x] T010 [P] Implement structured logging configuration and custom correlation ID middleware in `src/core/middleware.py` and `src/core/logging.py`
- [x] T011 [P] Implement global error handling, custom domain exceptions, and uniform error response envelope serializer in `src/core/exceptions.py`
- [x] T012 [P] Implement standardized pagination schemas (`PaginationMeta`, `PaginatedResponse[T]`) and query pagination helper in `src/core/pagination.py`
- [x] T012a [P] Implement rate limiting dependency in `src/core/rate_limit.py` (sliding window / IP and user rate limiting with 429 response envelope)
- [x] T012b [P] Implement background task dispatcher abstraction in `src/core/tasks.py` supporting FastAPI BackgroundTasks with future worker compatibility
- [x] T013 Create FastAPI application factory with middleware, exception handlers, rate limiter, lifespan management, and `/health` and `/ready` endpoints in `src/main.py`
- [x] T014 Create base test fixtures (`async_engine`, test database session rollbacks, and `httpx.AsyncClient` with `ASGITransport`) in `tests/conftest.py`

**Checkpoint**: Foundation ready - verify test client and database session fixtures pass against local test DB before starting domain user stories.

---

## Phase 3: User Story 1 - Account Registration, Authentication & Token Lifecycle (Priority: P1) 🎯 MVP

**Goal**: Deliver local user registration, credential authentication, rotating JWT access/refresh token lifecycle with reuse detection, and session logout.  
**Independent Test**: Register a user, authenticate to receive token pair, access `/auth/me`, rotate refresh token via `/auth/refresh`, verify old refresh token reuse triggers revocation, and verify logout revokes the session.

### Tests for User Story 1
- [x] T015 [P] [US1] Unit test password hashing and JWT token issuance/verification in `tests/unit/test_security.py`
- [x] T016 [P] [US1] Contract test for `/auth/register`, `/auth/login`, `/auth/refresh`, `/auth/logout`, and `/auth/change-password` against `contracts/openapi.yaml` in `tests/contract/test_auth_contract.py`
- [x] T017 [P] [US1] Integration test for complete auth flow, atomic token rotation with row-level lock, concurrent refresh race condition safety, reuse family revocation, and global revocation on password change in `tests/integration/test_auth_flow.py`

### Implementation for User Story 1
- [x] T018 [P] [US1] Create `User` (`id: UUID`, `email: VARCHAR(255) unique lowercase`, `hashed_password: VARCHAR(255)`, `full_name: VARCHAR(128) nullable`, `is_active: bool default True`, `is_superuser: bool default False`, `created_at/updated_at: TIMESTAMPTZ`) in `src/domains/auth/models.py`
- [x] T019 [P] [US1] Create `RefreshToken` (`id: UUID`, `user_id: UUID FK`, `token_hash: VARCHAR(64) unique`, `family_id: UUID`, `is_consumed: bool default False`, `is_revoked: bool default False`, `expires_at: TIMESTAMPTZ`, `created_at: TIMESTAMPTZ`) in `src/domains/auth/models.py`
- [x] T020 [P] [US1] Create Pydantic v2 schemas (`UserRegisterRequest`, `LoginRequest`, `RefreshTokenRequest`, `PasswordChangeRequest`, `TokenPairResponse`, `UserResponse`) in `src/domains/auth/schemas.py`
- [x] T021 [US1] Implement `AuthService` in `src/domains/auth/service.py` (registration with unique email check, password authentication, token pair generation, atomic single-use token rotation with row-level lock `SELECT ... FOR UPDATE`, token family revocation upon reuse, password change with global session revocation, and single-session logout)
- [x] T022 [US1] Implement `get_current_user` and `get_current_active_user` FastAPI dependencies with PyJWT validation in `src/domains/auth/dependencies.py`
- [x] T023 [US1] Implement authentication endpoints (`POST /auth/register`, `POST /auth/login`, `POST /auth/refresh`, `POST /auth/logout`, `POST /auth/change-password`, `GET /auth/me`) with rate limiting in `src/domains/auth/router.py`
- [x] T024 [US1] Register auth router into `src/main.py` and generate initial Alembic migration in `migrations/versions/001_auth_tables.py`

**Checkpoint**: At this point, User Story 1 (MVP) is fully functional and independently testable via `pytest tests/integration/test_auth_flow.py`.

---

## Phase 4: User Story 2 - Organization Tenant Isolation & Membership Administration (Priority: P1)

**Goal**: Deliver multi-tenant organization boundaries, owner creation, direct member addition via email/ID, fixed RBAC role assignments, and strict tenant isolation.  
**Independent Test**: User A creates Org 1; User B creates Org 2; User A adds User C to Org 1 as Member; verify User B receives 403 Forbidden attempting to access Org 1 resources.

### Tests for User Story 2
- [x] T025 [P] [US2] Contract test for `/orgs` and `/orgs/{org_id}/members` against `contracts/openapi.yaml` in `tests/contract/test_orgs_contract.py`
- [x] T026 [P] [US2] Integration test for tenant isolation, member role enforcement, and sole Owner protection (cannot demote/remove last active Owner) in `tests/integration/test_tenant_isolation.py`

### Implementation for User Story 2
- [x] T027 [P] [US2] Create `Organization` (`id: UUID`, `name: VARCHAR(128)`, `slug: VARCHAR(64) unique`, `deleted_at: TIMESTAMPTZ nullable`, `created_at/updated_at: TIMESTAMPTZ`) in `src/domains/organizations/models.py`
- [x] T028 [P] [US2] Create `OrganizationMembership` (`id: UUID`, `user_id: UUID FK`, `organization_id: UUID FK`, `role: Enum('OWNER','ADMIN','MEMBER','VIEWER')`, `unique(organization_id, user_id)`, `created_at/updated_at: TIMESTAMPTZ`) in `src/domains/organizations/models.py`
- [x] T029 [P] [US2] Create Pydantic schemas (`OrganizationCreateRequest`, `OrganizationUpdateRequest`, `OrganizationResponse`, `AddMemberRequest`, `UpdateRoleRequest`, `OrganizationMemberResponse`) in `src/domains/organizations/schemas.py`
- [x] T030 [US2] Implement `OrganizationService` in `src/domains/organizations/service.py` (organization creation assigning creator as Owner, soft deletion, direct member addition by email/ID, role modification, member removal, and strict enforcement of at least one active Owner)
- [x] T031 [US2] Implement organization membership dependencies (`require_org_member`, `require_org_role(min_role: RoleEnum)`) in `src/domains/organizations/dependencies.py`
- [x] T032 [US2] Implement organization and membership endpoints (`POST /orgs`, `GET /orgs`, `GET /orgs/{org_id}`, `PATCH /orgs/{org_id}`, `DELETE /orgs/{org_id}`, `GET /orgs/{org_id}/members`, `POST /orgs/{org_id}/members`, `PATCH /orgs/{org_id}/members/{user_id}`, `DELETE /orgs/{org_id}/members/{user_id}`) in `src/domains/organizations/router.py`
- [x] T033 [US2] Register organization router in `src/main.py` and generate Alembic migration in `migrations/versions/002_organizations_tables.py`

**Checkpoint**: At this point, User Stories 1 AND 2 are fully integrated and independently verified.

---

## Phase 5: User Story 3 - Project & Task Lifecycle Management (Priority: P2)

**Goal**: Deliver projects and tasks with single optional assignee (`assignee_id`), status/priority state transitions, soft deletes (`deleted_at`), and filtered pagination without N+1 queries.  
**Independent Test**: Create project under an organization; create tasks with priorities and single assignee; query task list with status/assignee filters and pagination; verify viewer role cannot modify tasks.

### Tests for User Story 3
- [x] T034 [P] [US3] Contract test for `/orgs/{org_id}/projects` and `.../tasks` against `contracts/openapi.yaml` in `tests/contract/test_work_management_contract.py`
- [x] T035 [P] [US3] Integration test for project & task CRUD, status transitions, single assignee assignment with cross-tenant organization membership invariant validation, archived/deleted project task modification freeze, and RBAC permission checks in `tests/integration/test_work_management.py`

### Implementation for User Story 3
- [x] T036 [P] [US3] Create `Project` (`id: UUID`, `organization_id: UUID FK`, `name: VARCHAR(128)`, `description: TEXT nullable`, `status: Enum('ACTIVE','ARCHIVED','COMPLETED') default ACTIVE`, `created_by: UUID FK`, `deleted_at: TIMESTAMPTZ nullable`, `created_at/updated_at: TIMESTAMPTZ`) in `src/domains/work_management/models.py`
- [x] T037 [P] [US3] Create `Task` (`id: UUID`, `project_id: UUID FK`, `title: VARCHAR(255)`, `description: TEXT nullable`, `status: Enum('TODO','IN_PROGRESS','IN_REVIEW','DONE') default TODO`, `priority: Enum('LOW','MEDIUM','HIGH','URGENT') default MEDIUM`, `due_date: TIMESTAMPTZ nullable`, `created_by: UUID FK`, `assignee_id: UUID FK nullable`, `deleted_at: TIMESTAMPTZ nullable`, `created_at/updated_at: TIMESTAMPTZ`) in `src/domains/work_management/models.py`
- [x] T038 [P] [US3] Create Pydantic schemas (`ProjectCreateRequest`, `ProjectUpdateRequest`, `ProjectResponse`, `TaskCreateRequest`, `TaskUpdateRequest`, `TaskResponse`, `TaskFilterParams`) in `src/domains/work_management/schemas.py`
- [x] T039 [US3] Implement `WorkManagementService` in `src/domains/work_management/service.py` (project creation, task creation with optional single assignee enforcing that assignee is an active member of the parent organization, archived/deleted project task modification freeze, status transitions, soft deletes filtering via `deleted_at IS NULL`, and optimized joins avoiding N+1 queries)
- [x] T040 [US3] Implement project and task route dependencies (`resolve_project_in_org`, `resolve_task_in_project`) in `src/domains/work_management/dependencies.py`
- [x] T041 [US3] Implement project and task endpoints in `src/domains/work_management/router.py`
- [x] T042 [US3] Register work management router in `src/main.py` and generate Alembic migration in `migrations/versions/003_work_management_tables.py`

**Checkpoint**: Core domain work management (US1 + US2 + US3) is operational with full relational integrity and RBAC gates.

---

## Phase 6: User Story 4 - Task Collaboration via Comments (Priority: P2)

**Goal**: Deliver task commenting, author-only editing, author/admin deletion, and chronological pagination.  
**Independent Test**: Post comment as User A; verify User B can view comment; verify User B cannot edit User A's comment (403); verify Org Admin can moderate/delete comment.

### Tests for User Story 4
- [x] T043 [P] [US4] Contract test for task comments in `tests/contract/test_comments_contract.py`
- [x] T044 [P] [US4] Integration test for comment ownership, editing permissions, and moderation in `tests/integration/test_comments.py`

### Implementation for User Story 4
- [x] T045 [P] [US4] Create `Comment` (`id: UUID`, `task_id: UUID FK`, `author_id: UUID FK`, `content: TEXT`, `created_at/updated_at: TIMESTAMPTZ`) in `src/domains/work_management/models.py`
- [x] T046 [P] [US4] Create Pydantic schemas (`CommentCreateRequest`, `CommentUpdateRequest`, `CommentResponse`) in `src/domains/work_management/schemas.py`
- [x] T047 [US4] Implement comment service methods (create, list paginated, update author-only check, delete author-or-admin check) in `src/domains/work_management/service.py`
- [x] T048 [US4] Implement comment endpoints (`POST`, `GET`, `PATCH`, `DELETE` under `/orgs/{org_id}/projects/{project_id}/tasks/{task_id}/comments`) in `src/domains/work_management/router.py`
- [x] T049 [US4] Generate Alembic migration for comments in `migrations/versions/004_comments_table.py`

---

## Phase 7: User Story 5 - Asynchronous Notifications for Work Events (Priority: P3)

**Goal**: Deliver non-blocking in-app notifications for task assignments and comment mentions with read/unread tracking.  
**Independent Test**: Assign task to User B; verify API returns immediately; query `/notifications` as User B to verify unread notification was recorded asynchronously; mark as read.

### Tests for User Story 5
- [x] T050 [P] [US5] Integration test for async notification dispatch (task assignment, status change, comment creation) and read-state transitions in `tests/integration/test_notifications.py`

### Implementation for User Story 5
- [x] T051 [P] [US5] Create `Notification` (`id: UUID`, `user_id: UUID FK`, `event_type: VARCHAR(64)`, `is_read: bool default False`, `payload: JSONB`, `created_at: TIMESTAMPTZ`) in `src/domains/notifications/models.py`
- [x] T052 [P] [US5] Create Pydantic schemas (`NotificationResponse`, `PaginatedNotificationsResponse`) in `src/domains/notifications/schemas.py`
- [x] T053 [US5] Implement `NotificationService` with async dispatch via `BackgroundTasks` (through `src/core/tasks.py` abstraction) in `src/domains/notifications/service.py`
- [x] T054 [US5] Implement notification endpoints (`GET /notifications`, `POST /notifications/{id}/read`) in `src/domains/notifications/router.py`
- [x] T055 [US5] Integrate notification event dispatch into `WorkManagementService` on task assignment, task status transition, and comment creation
- [x] T056 [US5] Register notification router in `src/main.py` and generate Alembic migration in `migrations/versions/005_notifications_table.py`

---

## Phase 8: User Story 6 - Audit History and Security Logging (Priority: P3)

**Goal**: Deliver immutable audit logging for security-sensitive operations (login failures, token revocations, role changes, soft deletes).  
**Independent Test**: Perform role update and project soft delete; query `/orgs/{org_id}/audit-logs` as Admin; verify immutable audit records contain actor UUID, action, and timestamp.

### Tests for User Story 6
- [x] T057 [P] [US6] Integration test for immutable audit log generation and admin-only query access in `tests/integration/test_audit.py`

### Implementation for User Story 6
- [x] T058 [P] [US6] Create `AuditLogEntry` (`id: UUID`, `organization_id: UUID nullable FK`, `actor_id: UUID nullable FK`, `action: VARCHAR(64)`, `target_resource: VARCHAR(64)`, `metadata: JSONB default {}`, `ip_address: VARCHAR(45) nullable`, `user_agent: VARCHAR(255) nullable`, `created_at: TIMESTAMPTZ`) in `src/domains/audit/models.py`
- [x] T059 [P] [US6] Create Pydantic schemas (`AuditLogResponse`, `PaginatedAuditLogsResponse`) in `src/domains/audit/schemas.py`
- [x] T060 [US6] Implement `AuditService` with immutable append-only record creation in `src/domains/audit/service.py`
- [x] T061 [US6] Implement audit log query endpoint (`GET /orgs/{org_id}/audit-logs` with Admin/Owner role check) in `src/domains/audit/router.py`
- [x] T062 [US6] Hook audit event recording into `AuthService` (login failures, password changes, token family revocations), `OrganizationService` (role changes, member removals, org soft deletes), and `WorkManagementService` (project/task soft deletes)
- [x] T063 [US6] Register audit router in `src/main.py` and generate Alembic migration in `migrations/versions/006_audit_table.py`

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: End-to-end verification, documentation, and quality gates.

- [x] T064 [P] Run full OpenAPI contract validation test in `tests/contract/test_openapi_schema.py`
- [x] T065 [P] Create initial database seed script for local development and demonstration in `scripts/seed_dev_data.py`
- [x] T066 Execute complete `quickstart.md` walkthrough scenario against running server
- [x] T067 Run Ruff linting and formatting across `src/` and `tests/`: `ruff check --fix` and `ruff format`
- [x] T068 Run Mypy static type checking across `src/`: `mypy src`
- [x] T069 Run full test suite with coverage reporting: `pytest --cov=src --cov-report=term-missing tests/`
- [x] T070 Update root `README.md` with architecture summary, quickstart references, and interview presentation notes

---

## Dependencies & Execution Order

### Phase Dependencies
- **Phase 1 (Setup)**: No dependencies.
- **Phase 2 (Foundational)**: Depends on Phase 1 completion. **Blocks all User Stories.**
- **Phase 3 (US1 - Auth)**: Depends on Phase 2. MVP core.
- **Phase 4 (US2 - Orgs & RBAC)**: Depends on Phase 3 (needs authenticated user).
- **Phase 5 (US3 - Projects & Tasks)**: Depends on Phase 4 (needs organization context and RBAC).
- **Phase 6 (US4 - Comments)**: Depends on Phase 5 (needs tasks).
- **Phase 7 (US5 - Notifications)**: Depends on Phase 5 and Phase 6 (hooks into task and comment events).
- **Phase 8 (US6 - Audit)**: Depends on Phase 4 and Phase 5 (hooks into admin and work actions).
- **Phase 9 (Polish)**: Depends on all user stories being complete.

---

## Implementation Strategy: MVP First

1. **Step 1**: Complete Phase 1 (Setup: T001–T005) & Phase 2 (Foundational: T006–T014).
2. **Step 2**: Implement Phase 3 (US1 - Auth MVP: T015–T024). Run `pytest tests/integration/test_auth_flow.py`.
3. **Step 3**: Deliver Phase 4 (US2 - Orgs & RBAC: T025–T033). Run `pytest tests/integration/test_tenant_isolation.py`.
4. **Step 4**: Deliver Phase 5 (US3 - Work Management: T034–T042). Run `pytest tests/integration/test_work_management.py`.
5. **Step 5**: Deliver Phase 6 (US4), Phase 7 (US5), and Phase 8 (US6).
6. **Step 6**: Execute Phase 9 Polish & Quality Gates (Ruff, Mypy, full test coverage).
