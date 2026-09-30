# Research & Architectural Decision Foundations: Project & Work Management Platform

**Date**: 2026-09-29  
**Branch**: `master` (`001-work-management-platform`)  
**Status**: Completed (Phase 0)

---

## 1. Reference Repository Analysis & Taxonomy

In accordance with Section 6 of the Master Prompt and Section 30 of the Feature Specification, all architectural patterns evaluated from workspace reference repositories are classified into:
- **ADOPT**: Use essentially as-is.
- **ADAPT**: Modify to fit our domain-oriented modular monolith architecture.
- **REIMPLEMENT**: Reproduce the useful concept independently with clean, modernized code.
- **REJECT**: Intentionally avoid due to architectural violations or over-complexity.

| Source Repository | Pattern / Component | Decision | Rationale |
|---|---|---|---|
| `fastapi-best-practices-master` | Domain-oriented package structure (`src/{domain}/`) | **ADOPT** | Matches Constitution Principle VIII (Domain-Oriented Modular Architecture). Organizes by business domain rather than technical layer. |
| `fastapi-best-practices-master` | `Annotated[T, Depends(...)]` dependency chaining | **ADOPT** | Clean, idiomatic FastAPI 0.115+ dependency injection with per-request caching. |
| `fastapi-best-practices-master` | SQLAlchemy 2.0 Async (`AsyncSession`, naming conventions) | **ADOPT** | Complies with Constitution Principle IV & VII; avoids blocking I/O and ensures standard constraint naming. |
| `fastapi-best-practices-master` | PyJWT over `python-jose` | **ADOPT** | `python-jose` is unmaintained; PyJWT 2.9+ is modern, actively maintained, and memory-safe. |
| `full-stack-fastapi-template-master` | SQLModel ORM models | **REJECT** | **Explicitly prohibited** by Constitution Principle IV ("SQLModel MUST NOT be used"). Combines schemas and ORM in an anti-pattern that couples DB models to API contracts. |
| `full-stack-fastapi-template-master` | Global `crud.py` and `models.py` in single horizontal directory | **REJECT** | Violates Constitution Principle VIII (Domain-oriented modular structure). Does not scale across business domains. |
| `FastAPI-boilerplate-main` | Infrastructure vs Module separation (`src/infrastructure/` + `src/modules/`) | **ADAPT** | Adopt the clean separation between reusable foundation (`src/core/`) and domain modules (`src/modules/` or `src/domains/`), but simplify dependency injection and eliminate over-abstracted generic base repositories. |
| `FastAPI-boilerplate-main` | Taskiq / Memcached / Multi-broker caching | **REJECT** | Violates Constitution Principle XIV & XV (Simplicity, Single background worker). Premature infrastructure complexity. |
| `fastapi-best-architecture-master` | Complex multi-tier RBAC with dynamic menus & data rules | **REJECT** | Clarification Q2 explicitly standardized on fixed predefined roles (`Owner`, `Admin`, `Member`, `Viewer`). Dynamic rules introduce runtime database lookups and query rewriting complexity. |

---

## 2. Core Architectural Decisions (ADR Foundations)

### ADR-001: Async SQLAlchemy 2.x & Database Layer Architecture
- **Decision**: Use native SQLAlchemy 2.0+ `AsyncSession` with `asyncpg` driver, `async_sessionmaker(expire_on_commit=False)`, and declarative mapping using `Mapped[...]` and `mapped_column(...)`.
- **Rationale**: Mandated by Constitution Principle IV. Provides high-throughput non-blocking I/O for PostgreSQL.
- **Alternatives Considered**:
  - *SQLModel*: Rejected per Constitution (tightly couples Pydantic validation to DB schemas, lacks full SQLAlchemy 2.0 async feature set).
  - *Tortoise-ORM / Peewee*: Rejected (non-standard in enterprise Python, smaller ecosystem, lacks Alembic migration tooling).
- **Complexity / Simplicity**: Minimalist session lifecycle managed strictly via FastAPI dependency `get_db_session()`. No generic repository wrappers or Unit-of-Work metaclass abstractions.

### ADR-002: Authentication & Token Lifecycle (OAuth 2.0 Bearer + JWT + Rotating Refresh Tokens)
- **Decision**:
  - Access Token: Short-lived (15 minutes), stateless JWT signed with HMAC-SHA256 (HS256) or Ed25519 (configurable via settings), containing `sub` (User UUID), `jti` (Token UUID), `type="access"`, and `exp`.
  - Refresh Token: Long-lived (7 days), stored hashed (SHA-256) in the database with family tracking UUID (`family_id`). Rotating on every use: a new refresh token is issued and the old one marked consumed. If a consumed token is reused, the entire token family is immediately revoked (compromise detection).
  - Session Revocation: Single session revocation on `/api/v1/auth/logout`; global revocation of all user token families on password change or security events.
- **Rationale**: Fulfills Specification FR-005 through FR-010 and Clarification Q1. Balances stateless access token validation speed with stateful, revocable refresh tokens and multi-device support.
- **Alternatives Considered**:
  - *Stateless refresh tokens*: Insecure; impossible to revoke or detect reuse without a central blacklist.
  - *Server-side session cookies (Redis/DB on every request)*: Adds latency and database bottlenecks to every single API request, violating stateless REST principles.

### ADR-003: Multi-Tenant Organization Boundary & Layered RBAC
- **Decision**:
  - Hierarchical relationship: `User` → `OrganizationMembership` (Role: `Owner`, `Admin`, `Member`, `Viewer`) → `Organization` → `Project` → `Task`.
  - Organization Context: Passed via URL path `/api/v1/orgs/{org_id}/...` or resolved via route dependency.
  - Multi-tier Authorization:
    1. Authentication Dependency: Validates JWT access token, resolves `current_user`.
    2. Tenant Membership Dependency: Validates `current_user` belongs to `{org_id}` and resolves active `role`.
    3. Permission/RBAC Dependency: Validates `role` meets required action threshold (e.g., `RequireRole("Admin")`).
    4. Resource Authorization: Service layer validates resource ownership or project/task belonging to `{org_id}`.
- **Rationale**: Satisfies Constitution Principle II, Master Prompt Section 10 & 11, and Clarification Q2 & Q3. Ensures zero cross-tenant leakage.
- **Alternatives Considered**:
  - *Dynamic custom permissions/roles*: Rejected in Clarification Q2 (avoids dynamic permission evaluation tables and caching complexity).
  - *Row-Level Security (Postgres RLS)*: Adds database-level session context configuration and makes testing with connection pools brittle; application-level tenant filtering in service/query layer is explicit, testable, and standard.

### ADR-004: Asynchronous Processing & Notifications Architecture
- **Decision**:
  - Dual-tier strategy:
    1. For immediate fire-and-forget in-process background tasks (e.g. audit log writing, lightweight email stubbing): Use FastAPI `BackgroundTasks`.
    2. For durable asynchronous task dispatch (retries, scheduled jobs, heavy processing): Provide an abstracted `TaskQueue` interface backed by **ARQ** (Async Redis Queue) or native asyncio worker when Redis is omitted.
  - Initial Reference Boilerplate implementation: In-process async event dispatch with fallback to Redis-backed ARQ when Redis is enabled.
- **Rationale**: Complies with Constitution Principle X & XV ("Only one background task framework may be selected"). Keeps operational footprint tiny for simple deployments while remaining production-grade.
- **Alternatives Considered**:
  - *Celery*: Over-engineered for an async Python monolith; requires multi-process workers, RabbitMQ/Redis, and is primarily sync-blocking unless gevent/eventlet are used.
  - *Taskiq*: Modern, but has heavier broker dependencies than ARQ.

### ADR-005: Soft Deletion, Archival & Audit Immutability
- **Decision**:
  - Organizations, Projects, and Tasks include `deleted_at: datetime | None = None`. Default queries automatically filter `deleted_at IS NULL`.
  - Child resources of soft-deleted or archived projects become read-only and are excluded from active task queries.
  - `AuditLogEntry` records are strictly immutable. Audit records store actor UUID, target resource type, target resource UUID, action string, client metadata (IP/User-Agent), and sanitized JSON payload. Database foreign keys to deleted resources are nullable or decoupled (`ON DELETE SET NULL`) to ensure audit records survive entity deletion.
- **Rationale**: Fulfills Clarification Q5. Preserves referential integrity and compliance history without complex database cascade errors.

### ADR-006: Pagination, Filtering & Error Handling Standard
- **Decision**:
  - **Pagination**: Deterministic limit/offset pagination with standard query params `page: int = 1`, `per_page: int = 20` (clamped to max 100), returning metadata: `total_items`, `page`, `per_page`, `total_pages`. Cursor-based support reserved for append-only audit log queries if needed.
  - **Filtering**: Explicit typed Pydantic filter schemas per resource (e.g., `status: TaskStatus | None`, `priority: TaskPriority | None`, `assignee_id: UUID | None`) translated directly into SQLAlchemy query clauses. No arbitrary/raw query string parsers.
  - **Error Model**: Unified error envelope:
    ```json
    {
      "error": {
        "code": "RESOURCE_NOT_FOUND",
        "message": "Task with ID ... not found",
        "details": []
      },
      "request_id": "c1a2b3..."
    }
    ```
- **Rationale**: Complies with Constitution Principle III & Technical Standards, ensuring contract stability for frontend/API clients.

---

## 3. Technology Stack & Pinned Versions

| Component | Library / Tool | Version | Purpose |
|---|---|---|---|
| Language | Python | 3.12+ | Type system, performance, native `type` statement |
| Web Framework | FastAPI | >=0.115.0 | ASGI web framework with OpenAPI generation |
| ASGI Server | Uvicorn (standard) | >=0.30.0 | High-performance ASGI runtime |
| ORM & SQL | SQLAlchemy | >=2.0.35 | Async ORM and typed SQL queries |
| DB Driver | asyncpg | >=0.29.0 | High-speed PostgreSQL async driver |
| Migrations | Alembic | >=1.13.3 | Database migration management |
| Data Validation | Pydantic | >=2.9.0 | Boundary validation and serialization |
| Settings | pydantic-settings | >=2.5.0 | Environment-driven typed configuration |
| JWT Tokens | PyJWT | >=2.9.0 | JWT generation, decoding, and validation |
| Password Hashing | argon2-cffi | >=23.1.0 | Modern memory-hard password hashing (Argon2id) |
| Async HTTP / Test | httpx | >=0.27.2 | Async HTTP client with `ASGITransport` |
| Test Runner | pytest + pytest-asyncio | >=8.3.0 | Async test suite execution |
| Linter & Formatter | Ruff | >=0.6.8 | Extreme speed linting and formatting |
| Type Checker | mypy | >=1.11.0 | Static type analysis |
| Background / Queue | ARQ | >=0.26.0 | Lightweight async task queue (Redis-backed) |
