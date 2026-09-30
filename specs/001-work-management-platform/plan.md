# Implementation Plan: Project & Work Management Platform REST API

**Branch**: `master` (`001-work-management-platform`) | **Date**: 2026-09-29 | **Spec**: [specs/001-work-management-platform/spec.md](./spec.md)

**Input**: Feature specification from `specs/001-work-management-platform/spec.md` with approved Clarifications from Session 2026-09-29.

---

## Summary

Build a production-grade, modular monolith REST API for a **Project & Work Management Platform** that acts as the reference application for a reusable commercial REST API boilerplate. The system implements OAuth 2.0 / JWT access token authentication with rotating refresh tokens and reuse detection, strict multi-tenant organization isolation with fixed RBAC (`Owner`, `Admin`, `Member`, `Viewer`), domain-oriented project and task workflows, child comment threading, async background notifications, and immutable audit logs. All relational persistence uses native SQLAlchemy 2.0 async with PostgreSQL and Alembic migrations.

---

## Technical Context

**Language/Version**: Python 3.12+ (modern typing, `type` statement, `StrEnum`)  
**Primary Dependencies**: FastAPI (>=0.115), Pydantic v2 (>=2.9), pydantic-settings (>=2.5), SQLAlchemy (>=2.0.35 async), asyncpg (>=0.29), Alembic (>=1.13), PyJWT (>=2.9), argon2-cffi (>=23.1), Uvicorn (>=0.30)  
**Storage**: PostgreSQL 16+ via async engine (`AsyncSession`), Redis 7+ (optional for distributed task queue / rate limit)  
**Testing**: `pytest`, `pytest-asyncio`, `httpx` (with `ASGITransport`)  
**Target Platform**: Docker / Linux containerized deployment, cross-platform local development (Windows / macOS / Linux)  
**Project Type**: Web service / REST API modular monolith  
**Performance Goals**: < 100ms p95 latency on authenticated CRUD endpoints; non-blocking background notification dispatch; bounded O(1) query counts for paginated task lists (zero N+1 queries)  
**Constraints**: Zero secrets in logs or code; UTC timezone-aware datetimes throughout; strict tenant isolation with zero cross-tenant leakage; no SQLModel; single background task framework  
**Scale/Scope**: Reusable commercial REST API foundation + 8 cohesive reference domain modules (Users, Auth, Organizations, Memberships, Projects, Tasks, Comments, Notifications, Audit)

---

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

| Principle | Requirement | Plan Alignment & Gate Status |
|---|---|---|
| **I. Production-Ready, Reusable Foundation** | Reusable backend foundation isolated from business domain | **PASS**: Architecture cleanly separates reusable infrastructure in `src/core/` from reference business domains in `src/domains/`. |
| **II. One Coherent Modular Monolith** | Single deployable monolith, no microservices | **PASS**: Modular monolith structure with explicit directional dependencies (`HTTP/API → Service → Data Access → Infrastructure`). |
| **III. Contract-Oriented Design** | REST-oriented, Pydantic v2 contracts, no ORM leaks | **PASS**: Full OpenAPI 3.1 contract defined in `contracts/openapi.yaml`. Pydantic schemas validate all I/O boundaries; ORM models never returned directly. |
| **IV. Secure by Default** | Argon2id, JWT validation, zero secrets, tenant isolation | **PASS**: Multi-device rotating refresh tokens with reuse detection; passwords hashed via Argon2id; secrets in `.env` validated on startup via `pydantic-settings`. |
| **V. Testability & Quality Gates** | Continuous automated tests across auth, RBAC, API | **PASS**: Test suite covers unit, integration, and contract tests with `pytest` and `httpx.AsyncClient` from day zero. |
| **VI. Separation of Concerns** | Thin routers, logic in service layer | **PASS**: Routers only handle HTTP transport; business rules encapsulated in domain service modules. |
| **VII. Database Integrity & Alembic** | SQLAlchemy 2.x async, PostgreSQL, no SQLModel, Alembic | **PASS**: Native SQLAlchemy 2.0 `AsyncSession`, declarative mapping, strict naming conventions, deterministic Alembic migrations. |
| **VIII. Environment-Driven Config** | Startup validated settings, sanitized `.env.example` | **PASS**: Domain-scoped and core `BaseSettings` via `pydantic-settings` with fail-fast validation. |
| **IX. Observability & Readiness** | Structured logs, request IDs, `/health`, `/ready` | **PASS**: Structured JSON logging, correlation IDs via middleware, operational health and DB readiness endpoints. |
| **X. Purpose-Driven Background Processing** | Single background framework, no gratuitous queues | **PASS**: In-process `BackgroundTasks` for lightweight dispatch; single async worker (ARQ) for durable task execution. |
| **XI. Dependency Discipline** | Every dependency justified, no duplicate libraries | **PASS**: Lean, modern stack; PyJWT chosen over unmaintained `python-jose`; no redundant ORMs or query builders. |
| **XII. Reusable vs Domain Separation** | Domain modules easily replaceable/pluggable | **PASS**: Reference domain entities grouped in `src/domains/work_management/` and `src/domains/auth/`. |
| **XIII. Documentation & Explainability** | Architectural decisions documented as ADRs | **PASS**: ADR foundations documented in `research.md`; contracts and data models comprehensively mapped. |
| **XIV. Simplicity & Complexity Budget** | Avoid unnecessary patterns, YAGNI | **PASS**: Fixed RBAC (no dynamic permission engines); single task assignee (no join-table fan-out); soft-delete via `deleted_at`. |

---

## Project Structure

### Documentation & Spec Kit Artifacts

```text
specs/001-work-management-platform/
├── spec.md              # Feature specification with ratified requirements
├── checklists/
│   └── requirements.md  # 16/16 quality checklist validation
├── plan.md              # Implementation plan (this file)
├── research.md          # Reference taxonomy & ADR foundations
├── data-model.md        # Relational schema, tables, constraints, state transitions
├── contracts/
│   └── openapi.yaml     # Full OpenAPI 3.1 contract specification
└── quickstart.md        # Runnable verification guide and validation flows
```

### Source Code Architecture (Modular Monolith)

```text
.
├── alembic.ini                  # Alembic configuration
├── pyproject.toml               # Python packaging, tool configs (ruff, mypy, pytest)
├── Dockerfile                   # Production container definition
├── docker-compose.yml           # PostgreSQL + Redis local orchestration
├── .env.example                 # Sanitized environment template
├── migrations/                  # Alembic async migration scripts
│   ├── env.py                   # Async Alembic environment
│   └── versions/                # Version migration scripts
├── src/
│   ├── main.py                  # FastAPI application factory & lifespan
│   ├── core/                    # Reusable Infrastructure Foundation
│   │   ├── config.py            # Global settings & environment validation
│   │   ├── database.py          # Async engine, sessionmaker, and get_db dependency
│   │   ├── security.py          # Password hashing (Argon2id) & JWT encode/decode
│   │   ├── middleware.py        # Request ID correlation & timing logging
│   │   ├── logging.py           # Structured logging configuration
│   │   ├── exceptions.py        # Global custom exceptions & HTTP exception handlers
│   │   ├── pagination.py        # Standardized pagination models & query helpers
│   │   └── tasks.py             # Single background task abstraction (in-process / ARQ)
│   ├── domains/                 # Domain-Oriented Modules
│   │   ├── auth/                # Authentication & Session Management
│   │   │   ├── router.py        # /auth/register, /auth/login, /auth/refresh, /auth/logout
│   │   │   ├── schemas.py       # Pydantic v2 schemas
│   │   │   ├── models.py        # User & RefreshToken SQLAlchemy models
│   │   │   ├── service.py       # User registration, token rotation, reuse detection
│   │   │   └── dependencies.py  # get_current_user, get_current_active_user
│   │   ├── organizations/       # Organizations, Memberships & RBAC
│   │   │   ├── router.py        # /orgs, /orgs/{org_id}/members
│   │   │   ├── schemas.py       # Organization & Membership schemas
│   │   │   ├── models.py        # Organization & OrganizationMembership models
│   │   │   ├── service.py       # Org creation, direct member add, role updates
│   │   │   └── dependencies.py  # require_org_member, require_org_role(RoleEnum)
│   │   ├── work_management/    # Projects, Tasks & Comments
│   │   │   ├── router.py        # /projects, /tasks, /comments
│   │   │   ├── schemas.py       # Project, Task, Comment schemas
│   │   │   ├── models.py        # Project, Task, Comment models
│   │   │   ├── service.py       # Work item lifecycle, state transitions, soft deletes
│   │   │   └── dependencies.py  # resolve_project, resolve_task
│   │   ├── notifications/       # Asynchronous User Notifications
│   │   │   ├── router.py        # /notifications, /notifications/{id}/read
│   │   │   ├── schemas.py       # Notification schemas
│   │   │   ├── models.py        # Notification SQLAlchemy model
│   │   │   └── service.py       # Async event handler & notification dispatcher
│   │   └── audit/               # Immutable Security & Activity Logging
│   │       ├── router.py        # /orgs/{org_id}/audit-logs
│   │       ├── schemas.py       # Audit log schemas
│   │       ├── models.py        # AuditLogEntry SQLAlchemy model
│   │       └── service.py       # Immutable audit event writer
└── tests/                       # Test Suite
    ├── conftest.py              # Test database, async engine, and client fixtures
    ├── unit/                    # Unit tests for domain logic and security utilities
    │   ├── test_security.py     # Password hashing and JWT claims validation
    │   └── test_token_rotation.py # Token rotation & reuse detection logic
    ├── integration/             # Integration tests against PostgreSQL
    │   ├── test_auth_api.py     # Registration, login, logout, refresh flow
    │   ├── test_tenant_isolation.py # Cross-organization access prevention
    │   ├── test_rbac.py         # Role permission gates (Owner, Admin, Member, Viewer)
    │   ├── test_work_flow.py    # Project, task, comment lifecycle
    │   └── test_soft_delete.py  # Soft delete and audit preservation
    └── contract/                # Contract tests validating OpenAPI schema conformance
        └── test_openapi_schema.py
```

**Structure Decision**: Option 1 (Modular Monolith) with strict boundary separation between `src/core/` (reusable boilerplate foundation) and `src/domains/` (modular business domains).

---

## Complexity Tracking

> Zero Constitution Check violations exist. All design decisions align strictly with Constitution Principles I through XIV.

| Component | Selected Approach | Simpler Alternative Rejected Because |
|---|---|---|
| Token Storage | DB-backed rotating refresh tokens with family tracking | Plain stateless refresh tokens cannot be revoked or detect token theft. |
| Background Dispatch | FastAPI BackgroundTasks + ARQ worker interface | Sync processing blocks HTTP request latency; Celery adds multi-process complexity. |
| Role Hierarchy | Fixed 4-tier enum (`Owner`, `Admin`, `Member`, `Viewer`) | Dynamic custom RBAC adds unnecessary runtime table joins and caching invalidation. |
| Task Assignment | Single optional assignee (`assignee_id`) | Many-to-many assignments add join table complexity without core reference value. |
| Resource Deletion | Soft deletion (`deleted_at`) | Hard deletion cascades break historical referential integrity in compliance audit logs. |
