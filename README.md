# lavenbloom-journal-service

> **Runbook & Developer Walkthrough** — Personal journal microservice for the Lavenbloom platform.

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [API Reference](#api-reference)
4. [Environment Variables](#environment-variables)
5. [Local Development Walkthrough](#local-development-walkthrough)
6. [Docker Walkthrough](#docker-walkthrough)
7. [CI/CD Pipeline Walkthrough](#cicd-pipeline-walkthrough)
8. [Kubernetes Deployment](#kubernetes-deployment)
9. [Secrets Management](#secrets-management)
10. [Troubleshooting](#troubleshooting)

---

## Overview

`journal-service` is a **FastAPI** microservice that provides personal journaling functionality for authenticated Lavenbloom users. It allows users to create titled journal entries and retrieve them in reverse-chronological order.

All routes (except `/health`) require a valid JWT Bearer token issued by `auth-service`. The service independently verifies tokens using the shared `JWT_SECRET` — no live call to `auth-service` is made at request time.

| Property | Value |
|---|---|
| **Runtime** | Python 3.11 |
| **Framework** | FastAPI |
| **Database** | PostgreSQL 15 (`journal_db`) |
| **Auth** | JWT (HS256) — verified locally via `auth_middleware.py` |
| **Port** | `8000` |
| **Docker image** | `lavenbloom/lavenbloom-journal-service` |

---

## Architecture

```
┌──────────────┐    JWT     ┌──────────────────────┐    SQLAlchemy   ┌──────────────────┐
│   Frontend   │ ─────────▶ │   journal-service    │ ──────────────▶ │   PostgreSQL      │
│  (via Gateway│            │   FastAPI :8000      │                 │   (journal_db)    │
└──────────────┘            └──────────────────────┘                 └──────────────────┘
```

### Source Layout

```
journal-service/
├── app/
│   ├── __init__.py
│   ├── main.py             # FastAPI routes (create_journal, get_journals, health)
│   ├── auth_middleware.py  # JWT verification — get_current_user dependency
│   ├── database.py         # SQLAlchemy engine + session factory
│   ├── models.py           # JournalEntry ORM model
│   └── schemas.py          # Pydantic request/response schemas
├── Dockerfile
├── requirements.txt
└── sonar-project.properties
```

### Data Model

`JournalEntry` table (`journal_db`):

| Column | Type | Notes |
|---|---|---|
| `id` | Integer (PK) | Auto-increment |
| `user_id` | Integer | From JWT claim `id` |
| `title` | String | Entry title |
| `content` | Text | Entry body |
| `created_at` | DateTime | Auto-set on insert (UTC) |

---

## API Reference

All endpoints (except `/health`) require:
```
Authorization: Bearer <JWT_TOKEN>
```

### `GET /health`

Returns service liveness status.

```bash
curl http://localhost:8003/health
# {"status":"ok"}
```

---

### `POST /journals`

Create a new journal entry for the authenticated user.

**Request body:**
```json
{
  "title": "A productive Monday",
  "content": "Today I completed my morning run and felt great..."
}
```

**Success — `200 OK`:**
```json
{
  "id": 12,
  "user_id": 42,
  "title": "A productive Monday",
  "content": "Today I completed my morning run and felt great...",
  "created_at": "2025-04-28T07:35:00.123456"
}
```

---

### `GET /journals`

Retrieve all journal entries for the authenticated user, ordered by `created_at` descending (newest first).

```bash
curl http://localhost:8003/journals \
  -H "Authorization: Bearer <token>"
```

**Success — `200 OK`:**
```json
[
  {
    "id": 12,
    "user_id": 42,
    "title": "A productive Monday",
    "content": "...",
    "created_at": "2025-04-28T07:35:00"
  },
  {
    "id": 11,
    "user_id": 42,
    "title": "Sunday reflection",
    "content": "...",
    "created_at": "2025-04-27T21:00:00"
  }
]
```

---

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `POSTGRES_URI` | ✅ | `postgresql://user:password@localhost/journal_db` | Full PostgreSQL connection string |
| `JWT_SECRET` | ✅ | `supersecretjwtkey` | HS256 signing key — must match `auth-service` exactly |

> ⚠️ Never use default secrets in production. Inject via Kubernetes Secret `journal-service-secret`.

---

## Local Development Walkthrough

### Prerequisites

- Python 3.11+
- PostgreSQL 15 (local or Docker)

### Step 1 — Clone and install

```bash
git clone https://github.com/lavenbloom/lavenbloom-journal-service.git
cd lavenbloom-journal-service
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### Step 2 — Start a local PostgreSQL (Docker shortcut)

```bash
docker run -d --name journal-db \
  -e POSTGRES_USER=user \
  -e POSTGRES_PASSWORD=password \
  -e POSTGRES_DB=journal_db \
  -p 5434:5432 postgres:15-alpine
```

### Step 3 — Set environment variables

```bash
# macOS/Linux
export POSTGRES_URI="postgresql://user:password@localhost:5434/journal_db"
export JWT_SECRET="devsecret"

# Windows PowerShell
$env:POSTGRES_URI = "postgresql://user:password@localhost:5434/journal_db"
$env:JWT_SECRET   = "devsecret"
```

### Step 4 — Run the service

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Swagger UI: `http://localhost:8000/docs`

### Step 5 — End-to-end walkthrough

```bash
# 1. Obtain a token from auth-service (must be running on :8001)
TOKEN=$(curl -s -X POST http://localhost:8001/login \
  -d "username=testuser&password=pass1234" | jq -r .access_token)

# 2. Create a journal entry
curl -X POST http://localhost:8000/journals \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"title":"My first entry","content":"Today was a great day."}'

# 3. Retrieve all entries (newest first)
curl http://localhost:8000/journals \
  -H "Authorization: Bearer $TOKEN"
```

---

## Docker Walkthrough

### Build the image

```bash
docker build -t lavenbloom-journal-service:local .
```

### Run standalone

```bash
docker run -d \
  -e POSTGRES_URI="postgresql://user:password@host.docker.internal:5434/journal_db" \
  -e JWT_SECRET="devsecret" \
  -p 8003:8000 \
  lavenbloom-journal-service:local
```

### Full stack via Docker Compose

```bash
# From project root
docker compose up journal-db journal-service
```

Service available at `http://localhost:8003`.

---

## CI/CD Pipeline Walkthrough

Pipeline file: `.github/workflows/ci-journal-service.yml`

| Event | Jobs triggered |
|---|---|
| Pull Request → `develop` / `main` | `sast` → `sca` → `trivy` → `pr-check` |
| Push → `develop` | `dev-publish` → `dev-cd` |
| GitHub Release created | `publish` → `cd` |

### Job descriptions

| Job | Shared workflow | What it does |
|---|---|---|
| `sast` | `ci-sast.yml` | SonarQube static analysis + quality gate check |
| `sca` | `ci-sca.yml` | Snyk dependency vulnerability scan (`runtime: python`) |
| `trivy` | `ci-docker-build.yml` | Temporary Docker build + Trivy CVE scan (CRITICAL/HIGH). Image is **not** pushed. |
| `pr-check` | — | Aggregated gate job required by branch protection |
| `dev-publish` | `ci-docker-publish.yml` | Build and push `dev-{SHA}` tag to Docker Hub |
| `dev-cd` | `cd-template.yml` | Update `values-dev.yaml` in `lavenbloom-charts`, ArgoCD syncs dev cluster |
| `publish` | `ci-docker-publish.yml` | Build and push semver tag on GitHub Release |
| `cd` | `cd-template.yml` | Update `values-prod.yaml`, ArgoCD syncs prod cluster |

### Required GitHub Secrets

| Secret | Description |
|---|---|
| `SONAR_TOKEN` | SonarQube authentication token |
| `SONAR_URL` | SonarQube server URL |
| `SNYK_TOKEN` | Snyk API token |
| `DOCKER_USERNAME` | Docker Hub username |
| `DOCKER_PASSWORD` | Docker Hub password or access token |
| `HELM_REPO_PAT` | GitHub PAT with push access to `lavenbloom-charts` |

---

## Kubernetes Deployment

`journal-service` runs in the `backend` namespace. Its dedicated PostgreSQL StatefulSet runs in the `db` namespace.

### Helm install (dev)

```bash
helm install journal-service ./microservices/journal-service -f values-dev.yaml
```

### Verify the deployment

```bash
# Check pod status
kubectl get pods -n backend -l app=journal-service

# Stream logs
kubectl logs -n backend deployment/journal-service -f

# Port-forward for local testing
kubectl port-forward -n backend deployment/journal-service 8003:8000

# Health check
curl http://localhost:8003/health
```

### Verify Secret injection

```bash
kubectl get secret journal-service-secret -n backend -o jsonpath='{.data.POSTGRES_URI}' | base64 -d
kubectl get secret journal-service-secret -n backend -o jsonpath='{.data.JWT_SECRET}' | base64 -d
```

### Network policy

- `journal-service` → `journal-db` (in `db` namespace): **allowed**
- Gateway → `journal-service`: **allowed**
- All other traffic: **denied** (zero-trust default-deny policy)

---

## Secrets Management

| Secret Name (K8s) | Keys | Injected As |
|---|---|---|
| `journal-service-secret` | `POSTGRES_URI`, `JWT_SECRET` | `envFrom.secretRef` on the Deployment |
| `journal-db-secret` | `POSTGRES_USER`, `POSTGRES_PASSWORD` | Environment vars on the PostgreSQL StatefulSet |

> ⚠️ `values-dev.yaml` and `values-prod.yaml` currently store these values in plaintext.  
> Recommended improvement: migrate to [Sealed Secrets](https://github.com/bitnami-labs/sealed-secrets) or [External Secrets Operator](https://external-secrets.io/).

---

## Troubleshooting

### `401 Unauthorized` on all journal routes

The Bearer token is expired or the `JWT_SECRET` does not match `auth-service`.  
Steps to diagnose:

```bash
# 1. Verify the secret value in Kubernetes
kubectl get secret journal-service-secret -n backend -o jsonpath='{.data.JWT_SECRET}' | base64 -d

# 2. Compare with auth-service secret
kubectl get secret auth-service-secret -n backend -o jsonpath='{.data.JWT_SECRET}' | base64 -d

# 3. If they differ, update and rollout restart
kubectl rollout restart deployment/journal-service -n backend
```

### Service crashes on startup — `could not connect to server`

The PostgreSQL init Job may not have finished. Check:

```bash
kubectl get jobs -n db | grep journal
kubectl logs job/journal-db-init -n db
```

### Entries not ordered correctly

`GET /journals` uses `ORDER BY created_at DESC`. If entries appear out of order, check the system clock on the database pod:

```bash
kubectl exec -n db statefulset/journal-db -- date
```

### `422 Unprocessable Entity` on `POST /journals`

Both `title` and `content` fields are required. Ensure the request body includes both fields with string values.