# Production-Grade REST API Modular Monolith Boilerplate

A production-grade, commercially reusable REST API boilerplate and reference platform built with **FastAPI**, **SQLAlchemy 2.0 Async**, **PostgreSQL 16**, **Alembic**, **Pydantic v2**, **PyJWT**, and **Argon2id**.

---

## 1. Reference Application Domain: Work Management Platform

The boilerplate implements a complete, real-world **Project & Work Management Platform** featuring:
- **Authentication & Security**: Argon2id password hashing, short-lived JWT access tokens, database-backed rotating refresh tokens with automatic reuse detection and session family revocation, sliding-window rate limiting on sensitive endpoints.
- **Multi-Tenant Organizations & RBAC**: Hierarchical multi-tenancy with 4-tier role hierarchy (`OWNER` > `ADMIN` > `MEMBER` > `VIEWER`). Strict single-owner invariant with atomic owner transfer and isolation across all queries.
- **Projects & Tasks**: Project lifecycles, soft deletion, role-guarded task creation and updates, state machine status transitions, organization membership validation for task assignees.
- **Comments & Collaboration**: Contextual task comments with author-only editing and author/admin deletion rights.
- **Asynchronous Notifications**: Decoupled, non-blocking notification dispatch via `TaskDispatcher` background tasks for task assignments, status changes, and comments, with read/unread tracking.
- **Immutable Audit Logging**: Append-only security audit trail recording actor UUIDs, target resources, client IP addresses, user agents, and structured JSONB metadata for critical actions.

---

## 2. Architectural Highlights & Design Decisions

### Modular Monolith Architecture
```
Rest/
├── src/
│   ├── core/                    # Domain-agnostic infrastructure & cross-cutting concerns
│   │   ├── config.py            # Pydantic Settings management (.env validated)
│   │   ├── database.py          # SQLAlchemy 2.0 Async engine, Base model, session factory
│   │   ├── exceptions.py        # Contract-compliant global error handlers & envelope
│   │   ├── logging.py           # Structured JSON/Console logging with request correlation
│   │   ├── middleware.py        # Correlation ID injection, request logging & timing
│   │   ├── pagination.py        # Standardized pagination schemas & query utilities
│   │   ├── rate_limit.py        # In-memory sliding window rate limiting
│   │   ├── security.py          # Argon2id hashing, JWT access token issuance & validation
│   │   └── tasks.py             # Non-blocking TaskDispatcher abstraction (FastAPI BackgroundTasks)
│   ├── domains/                 # Bounded business domains
│   │   ├── auth/                # Users, refresh token rotation, authentication lifecycle
│   │   ├── organizations/       # Tenants, RBAC memberships, organization management
│   │   ├── work_management/    # Projects, tasks, comments
│   │   ├── notifications/       # In-app notifications & background event consumers
│   │   └── audit/               # Immutable audit logging & administrative query logs
│   └── main.py                  # FastAPI factory, lifespan, CORS, middleware, routers
├── migrations/                  # Alembic asynchronous database migrations
│   └── versions/                # Versioned DDL migrations (001 to 006)
├── scripts/                     # Operational utilities & development seeding
│   └── seed_dev_data.py         # Idempotent development data seeder
├── specs/                       # Source of truth specifications, data models, contracts
│   └── 001-work-management-platform/
│       ├── spec.md              # Requirements & acceptance criteria
│       ├── data-model.md        # Database schemas, relationships, constraints, indexes
│       ├── quickstart.md        # Step-by-step verification guide
│       └── contracts/openapi.yaml # OpenAPI 3.1 specification
└── tests/                       # Comprehensive test pyramid
    ├── unit/                    # Security, exceptions, pagination, rate limiting
    ├── integration/             # Tenant isolation, auth flows, tasks, comments, audit, notifs
    └── contract/                # Full OpenAPI 3.1 schema & endpoint contract parity tests
```

### Key Engineering Decisions & Trade-Offs

1. **Layered Separation of Concerns**:
   - **Router (`router.py`)**: Handles HTTP transport, path parameter resolution, and response serialization.
   - **Dependencies (`dependencies.py`)**: Resolves hierarchical context, enforces RBAC policies (`require_org_role`), and validates cross-resource boundaries before services are invoked.
   - **Service (`service.py`)**: Encapsulates all domain business logic, invariants, notification hooks, and transactional integrity.
   - **Models & Schemas (`models.py`, `schemas.py`)**: Declarative SQLAlchemy 2.0 ORM models and strictly validated Pydantic v2 data transfer objects.

2. **OAuth 2.0 / JWT Lifecycle with Token Family Reuse Detection**:
   - Access tokens are short-lived (15 minutes), stateless JWTs signed with HMAC-SHA256.
   - Refresh tokens are long-lived (7 days), stored as cryptographic hashes (`SHA-256`) in the database.
   - Every refresh operation rotates the token atomically. If an adversary attempts to replay an already-consumed refresh token, the system detects token theft, immediately revokes the entire session family (`family_id`), logs a security audit event, and denies authentication.

3. **Strict Multi-Tenant Isolation & Single-Owner Invariant**:
   - Every organization-scoped resource requires tenant resolution via `resolve_org_context`.
   - Projects, tasks, comments, and audit records are strictly partitioned by `organization_id`.
   - Every organization must have exactly one active Owner. Sole owners cannot be demoted or removed. Owner transfer atomically demotes the current owner to Admin and promotes the target member to Owner within a single ACID transaction.

4. **Decoupled Background Dispatch without External Queues**:
   - Background work (such as creating in-app notification records) is dispatched via the `TaskDispatcher` interface, implemented using FastAPI's native `BackgroundTasks`.
   - This keeps the boilerplate lightweight and self-contained (no mandatory Redis/Celery/RabbitMQ dependencies) while providing an explicit abstraction boundary ready for distributed queue integration if needed.

5. **Immutable Append-Only Audit Logging**:
   - Security and compliance events (failed logins, password changes, token family revocations, member removals, role changes, project/task deletions) are recorded in `audit_log_entry`.
   - The service exposes only `record_audit` and administrative query endpoints. No update or delete operations exist.

6. **Fast, Isolated Testing with SQLite StaticPool**:
   - Production runs against PostgreSQL 16 with `asyncpg` connection pooling.
   - Test suites execute against an in-memory SQLite database utilizing SQLAlchemy's `StaticPool` and automatic table cleanup, allowing 61 integration, unit, and contract tests to run in seconds without external database dependencies.

---

## 3. Quickstart & Local Setup

### Prerequisites
- Python 3.12+
- Docker & Docker Compose
- `uv` (recommended fast package installer) or `pip`

### Step 1: Environment Setup
```bash
# Clone the repository
git clone <repo-url> Rest
cd Rest

# Copy environment template
cp .env.example .env
```

### Step 2: Start PostgreSQL Database
```bash
# Start PostgreSQL 16 via Docker Compose
docker compose up -d

# Verify database health
docker compose ps
```

### Step 3: Install Dependencies & Run Migrations
```bash
# Create virtual environment and install dependencies
uv venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
uv pip install -e ".[dev]"

# Apply Alembic asynchronous migrations
alembic upgrade head
```

### Step 4: Seed Development Data (Optional)
```bash
# Populate database with demo users, organizations, projects, tasks, and audit logs
uv run python scripts/seed_dev_data.py
```
Seeded demo accounts (password: `SecurePassword123!`):
- **Alice Smith (Owner)**: `alice@example.com`
- **Bob Jones (Member)**: `bob@example.com`
- **Charlie Brown (Viewer)**: `charlie@example.com`
- **Eve Mallory (External Tenant)**: `eve@example.com`

### Step 5: Run Development Server
```bash
uv run uvicorn src.main:app --reload --port 8000
```
Interactive API documentation:
- Swagger UI: [http://localhost:8000/docs](http://localhost:8000/docs)
- ReDoc: [http://localhost:8000/redoc](http://localhost:8000/redoc)
- OpenAPI Specification: [http://localhost:8000/openapi.json](http://localhost:8000/openapi.json)
- Health Check: [http://localhost:8000/health](http://localhost:8000/health)
- Readiness Probe: [http://localhost:8000/ready](http://localhost:8000/ready)

---

## 4. Verification & Testing

### Test Suite Execution
```bash
# Run all unit, integration, and contract tests
uv run pytest

# Run specific domain test suites
uv run pytest tests/contract/test_openapi_schema.py
uv run pytest tests/integration/test_tenant_isolation.py
uv run pytest tests/integration/test_auth_flow.py
uv run pytest tests/integration/test_quickstart_scenario.py
```

### Code Quality & Static Analysis
```bash
# Lint with Ruff
uv run ruff check src/ tests/ scripts/

# Format with Ruff
uv run ruff format --check src/ tests/ scripts/

# Strict type checking with Mypy
uv run mypy src tests scripts
```

---

## 5. Interview Presentation Notes & Discussion Points

When discussing this codebase during technical architecture reviews or system design interviews, highlight the following themes:

1. **Why Modular Monolith over Microservices?**
   - Eliminates distributed transaction complexity, network serialization overhead, and premature operational overhead while maintaining strict domain boundaries.
   - Each domain (`auth`, `organizations`, `work_management`, `notifications`, `audit`) has its own schemas, models, and services. If scale demands, any domain can be cleanly extracted into an independent microservice with minimal refactoring.

2. **Security & Authentication Defense in Depth**:
   - Argon2id password hashing protects against GPU/ASIC brute-force attacks.
   - Cryptographic token hashing ensures stored refresh tokens cannot be abused if the database is read-compromised.
   - Sliding-window rate limiting on login/registration endpoints defends against credential stuffing and DoS attacks.
   - Correlation IDs attached to incoming HTTP headers and log records enable end-to-end distributed tracing.

3. **Multi-Tenant RBAC Invariants**:
   - The 4-tier hierarchy (`OWNER` > `ADMIN` > `MEMBER` > `VIEWER`) simplifies authorization into a deterministic role comparison (`RoleEnum.is_at_least()`).
   - Tenant isolation is defensive: even if an adversary knows a project UUID, querying `/orgs/{org_id}/projects/{project_id}` verifies that the project belongs to the resolved organization, rejecting cross-tenant probes with 404 or 403.
   - The single-owner invariant prevents orphaned organizations and power struggles.

4. **Zero-Downtime Migration Strategy**:
   - All migrations are forward-compatible and backwards-compatible with PostgreSQL.
   - Primary keys use client-generated UUIDv4 values, preventing ID enumeration attacks and avoiding distributed auto-increment locks.
   - Indexes are explicitly tailored for access patterns (e.g. composite index `ix_notification_user_unread` on `(user_id, is_read, created_at DESC)`).
