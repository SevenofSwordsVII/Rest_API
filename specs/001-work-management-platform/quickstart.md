# Quickstart & Verification Guide: Project & Work Management Platform

**Date**: 2026-09-29  
**Feature**: Project & Work Management Platform REST API  
**Branch**: `001-work-management-platform`  
**Spec Reference**: [spec.md](./spec.md) | [data-model.md](./data-model.md) | [contracts/openapi.yaml](./contracts/openapi.yaml)

---

## 1. Prerequisites & Environment Setup

- Python 3.12+
- Docker & Docker Compose (for PostgreSQL 16)
- `uv` (recommended fast package installer) or `pip`

```bash
# Clone and enter repo
cd C:/Users/Milad/Desktop/Rest

# Start local PostgreSQL instance
docker run --name rest-postgres -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=rest_db -p 5432:5432 -d postgres:16-alpine

# Set local environment variables
cp .env.example .env
```

---

## 2. Dependency Installation & Database Migration

```bash
# Create virtual environment and install dependencies
uv venv
source .venv/bin/activate  # Or on Windows: .venv\Scripts\activate
uv pip install -e ".[dev]"

# Run database migrations
alembic upgrade head

# Start development server
uvicorn src.main:app --reload --port 8000
```

---

## 3. End-to-End Validation Scenarios (cURL Walkthrough)

### Scenario 1: User Registration & Authentication
```bash
# 1. Register Alice
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "alice@example.com", "password": "SecurePassword123!", "full_name": "Alice Smith"}'

# 2. Login to get access token and refresh token
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "alice@example.com", "password": "SecurePassword123!"}'
# Expected: 200 OK with {"access_token": "...", "refresh_token": "...", "expires_in": 900}
```

### Scenario 2: Organization Creation & Direct Member Addition
```bash
# 1. Alice creates Acme Corp (Alice is OWNER)
curl -X POST http://localhost:8000/api/v1/orgs \
  -H "Authorization: Bearer $ALICE_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "Acme Corp", "slug": "acme-corp"}'

# 2. Register Bob
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "bob@example.com", "password": "SecurePassword123!", "full_name": "Bob Jones"}'

# 3. Alice adds Bob as MEMBER
curl -X POST http://localhost:8000/api/v1/orgs/$ORG_ID/members \
  -H "Authorization: Bearer $ALICE_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"email": "bob@example.com", "role": "MEMBER"}'
```

### Scenario 3: Tenant Isolation Verification
```bash
# 1. Register Eve and create Evil Org
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "eve@example.com", "password": "SecurePassword123!"}'
# Eve logs in -> $EVE_TOKEN

# 2. Eve attempts to access Acme Corp projects
curl -i -X GET http://localhost:8000/api/v1/orgs/$ORG_ID/projects \
  -H "Authorization: Bearer $EVE_TOKEN"
# Expected: 403 Forbidden with {"error": {"code": "FORBIDDEN", ...}}
```

### Scenario 4: Work Management (Project & Task Flow)
```bash
# 1. Alice creates Project Alpha
curl -X POST http://localhost:8000/api/v1/orgs/$ORG_ID/projects \
  -H "Authorization: Bearer $ALICE_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "Project Alpha", "description": "Core initiative"}'

# 2. Alice creates Task assigned to Bob
curl -X POST http://localhost:8000/api/v1/orgs/$ORG_ID/projects/$PROJECT_ID/tasks \
  -H "Authorization: Bearer $ALICE_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"title": "Implement Auth", "priority": "HIGH", "assignee_id": "'$BOB_ID'"}'

# 3. Bob queries assigned tasks
curl -X GET "http://localhost:8000/api/v1/orgs/$ORG_ID/projects/$PROJECT_ID/tasks?assignee_id=$BOB_ID&status=TODO" \
  -H "Authorization: Bearer $BOB_TOKEN"

# 4. Bob adds comment
curl -X POST http://localhost:8000/api/v1/orgs/$ORG_ID/projects/$PROJECT_ID/tasks/$TASK_ID/comments \
  -H "Authorization: Bearer $BOB_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"content": "Working on initial schemas now."}'
```

### Scenario 5: Token Rotation & Reuse Detection
```bash
# 1. Rotate refresh token
curl -X POST http://localhost:8000/api/v1/auth/refresh \
  -H "Content-Type: application/json" \
  -d '{"refresh_token": "'$OLD_REFRESH_TOKEN'"}'
# Expected: 200 OK with new $NEW_REFRESH_TOKEN

# 2. Adversary replays OLD_REFRESH_TOKEN
curl -i -X POST http://localhost:8000/api/v1/auth/refresh \
  -H "Content-Type: application/json" \
  -d '{"refresh_token": "'$OLD_REFRESH_TOKEN'"}'
# Expected: 401 Unauthorized with token family revocation trigger
```

---

## 4. Automated Test Suite Execution

```bash
# Run full test suite with coverage
pytest --cov=src tests/

# Run specific domain test slice
pytest tests/unit/test_auth.py
pytest tests/integration/test_tenant_isolation.py
pytest tests/integration/test_tasks.py

# Lint & type checking
ruff check src tests
ruff format --check src tests
mypy src
```
