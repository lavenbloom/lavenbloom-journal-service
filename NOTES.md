# journal-service — Study Notes

---

## Table of Contents

1. [How This Service Works](#1-how-this-service-works)
2. [Dockerfile — Line by Line](#3-dockerfile--line-by-line)
3. [Q&A](#4-qa)

---

## 1. How This Service Works

### What it does

The journal-service provides a **private text journaling** feature. Users write free-form journal entries — thoughts, reflections, daily notes — which are stored privately in a PostgreSQL database. Only the owner of each entry can read it.

It is the simplest of the four backend microservices: no Redis, no background workers, no external events. It is a straightforward authenticated CRUD service.

### API routes

| Method | Path | What it does |
|---|---|---|
| `GET` | `/health` | Health check for Kubernetes liveness probe |
| `POST` | `/journal` | Create a new journal entry for the authenticated user |
| `GET` | `/journal` | Retrieve all journal entries for the authenticated user |

### Authentication

Every route except `/health` validates the JWT from `Authorization: Bearer <token>` header using `auth_middleware.py` and `JWT_SECRET`. The `user_id` extracted from the token is stored with every entry — ensuring complete data isolation between users.

### Database

PostgreSQL (`journal_db`) with a `journal_entries` table: `id`, `user_id`, `content`, `created_at`. All queries filter by `user_id` from the JWT — no user can access another user's entries.

### How it connects to other components

```
User → Gateway → /journal/* → journal-service:8000 → PostgreSQL journal-db:5432
                                    ↑
                         JWT_SECRET from Kubernetes Secret
```

No Redis dependency. No inter-service HTTP calls. Fully self-contained.

---

## 2. Dockerfile — Line by Line

```dockerfile
FROM python:3.11-slim
```
Debian-based Python 3.11 slim image. Consistent base across all backend microservices, ensuring the same OS security patch level. `slim` reduces image size by removing documentation and locale files.

---

```dockerfile
WORKDIR /app
```
All subsequent `COPY`, `RUN`, `CMD` instructions use `/app` as the working directory. The directory is created automatically.

---

```dockerfile
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*
```
Installs C build tools needed to compile `psycopg2` (Python ↔ PostgreSQL driver):
- `gcc` — C compiler for compiling C extensions
- `libpq-dev` — PostgreSQL client library headers

These tools are only needed during **build time** to compile the Python package. They are not needed at runtime but remain in this single-stage image. The `rm -rf /var/lib/apt/lists/*` removes the package index in the same layer to prevent bloating the image.

---

```dockerfile
COPY requirements.txt .
```
Copies `requirements.txt` before application code. Exploits Docker's layer cache: if dependencies haven't changed, the following `pip install` step is skipped on rebuild. This is the single most impactful optimization for iterative development builds.

---

```dockerfile
RUN pip install --no-cache-dir -r requirements.txt
```
Installs:
- `fastapi` — web framework (routes, request/response models, validation)
- `uvicorn` — ASGI server that runs FastAPI
- `sqlalchemy` — ORM for database models and queries
- `psycopg2` — PostgreSQL driver (or `psycopg2-binary` — pre-compiled)
- `python-jose` — JWT token verification using `JWT_SECRET`

`--no-cache-dir` prevents pip from writing a download cache into the image layer, keeping the layer smaller.

---

```dockerfile
COPY app/ app/
```
Copies `app/main.py`, `app/database.py`, `app/auth_middleware.py` into `/app/app/`. This layer is the one rebuilt most frequently during development. Its position after `pip install` means dependency installation is not re-triggered by code edits.

---

```dockerfile
RUN useradd -m appuser && chown -R appuser /app
USER appuser
```
**Why this matters:** journal entries contain personal, potentially sensitive content. Running as `root` would mean a code injection vulnerability gives the attacker root privileges inside the container (and potential host escape). Running as `appuser` contains the blast radius to the `/app` directory.

Steps:
1. `useradd -m appuser` — creates `appuser` with a home directory at `/home/appuser`
2. `chown -R appuser /app` — makes `appuser` own all files in `/app`
3. `USER appuser` — all subsequent operations in the Dockerfile and at runtime use this user

---

```dockerfile
EXPOSE 8000
```
Documentation metadata. States that the containerized process listens on TCP port 8000. Not enforced by Docker — actual port exposure is done via Kubernetes Service (`targetPort: 8000`) or `docker run -p 8000:8000`.

---

```dockerfile
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```
Starts the FastAPI application at container startup.

- **Exec form** (JSON array): process receives OS signals directly — `docker stop` sends `SIGTERM` to uvicorn which gracefully closes in-flight requests before shutting down
- `--host 0.0.0.0`: binds to all network interfaces, making the service reachable from the Kubernetes network fabric
- `--port 8000`: consistent with `EXPOSE` and the Kubernetes Service definition

---

## 3. Q&A

**Q: Why is journal-service the simplest — no Redis, no events?**
A: Journal entries are created and read by the owner only — there are no cross-service dependencies triggered by journal actions. A journal entry being created doesn't need to notify anyone or trigger any other service. This makes it purely CRUD (Create, Read, Update, Delete). The simpler the service, the easier it is to test, debug, and scale independently.

**Q: Could journal entries be searched by content?**
A: Not currently — the `GET /journal` endpoint retrieves all entries for the user. Full-text search would require either PostgreSQL's `tsvector` (full-text search columns) or an Elasticsearch integration. Adding this would be a feature enhancement to `main.py` and would not require any infrastructure changes.

**Q: Why use SQLAlchemy instead of raw SQL?**
A: SQLAlchemy ORM provides: (1) SQL injection protection — queries are parameterized automatically; (2) database portability — switching from PostgreSQL to MySQL requires changing the connection string, not the query code; (3) Python-native query building — `session.query(JournalEntry).filter_by(user_id=user_id)` is more readable than SQL strings.

**Q: What happens to journal entries if the PostgreSQL pod is deleted?**
A: Because `journal-db` runs as a StatefulSet with a PersistentVolumeClaim backed by NFS, the data persists on the NFS server. Deleting the pod (or rescheduling it to another node) does not delete the PVC or the data it contains. When the new pod starts, it mounts the same PVC and finds all existing data intact.

**Q: The Dockerfile is identical to habit-service's. Should they be the same?**
A: Yes — all four backend microservices use the same Python/PostgreSQL stack, so their Dockerfiles are structurally identical. Each references its own `app/` directory and `requirements.txt`. This consistency is intentional: the same security hardening, the same base image, the same layer ordering. In a large organisation, you'd centralise this into a shared base image (`FROM company/python-base:3.11`) that all services inherit from — meaning one update patches the base for all services simultaneously.
