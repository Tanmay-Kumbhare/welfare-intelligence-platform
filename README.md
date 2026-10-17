# Welfare Intelligence Platform (VidyaSetu)

An AI-based welfare scheme eligibility and citizen benefit matching engine. Citizens fill a dynamic multi-step profile form and receive explainable results against the current development seed catalogue (7 schemes; live government ingestion is not implemented).

| Layer | Tech |
|---|---|
| Backend | FastAPI, SQLAlchemy 2.0 (async), Alembic, Pydantic v2 |
| Database | PostgreSQL (Supabase or local Docker) |
| Frontend | React 19, Vite, Tailwind CSS 4, React Router 7, Vitest |
| Auth | Email/password (bcrypt) + optional Google OAuth / DigiLocker linking |

## Project structure

```
welfare-intelligence-platform/
├── backend/
│   ├── alembic/versions/      # 11 additive migrations (0001 → 0011)
│   ├── app/
│   │   ├── api/v1/            # REST endpoints (auth, citizens, schemes, forms…)
│   │   ├── auth/              # password hashing, OAuth, sessions
│   │   ├── models/            # SQLAlchemy models
│   │   ├── services/          # eligibility engine, profile mapping, scheme matching
│   │   ├── config.py          # Settings (loads backend/.env)
│   │   └── database.py        # async engine + session factory
│   ├── scripts/               # seed.py, seed_forms.py, verification helpers
│   ├── tests/                 # pytest suites
│   └── requirements.txt
├── frontend/
│   ├── src/pages/             # LoginPage, CheckEligibilityPage, ResultsPage, OAuthCallbackPage…
│   ├── src/services/api.js    # axios client (VITE_API_URL)
│   └── package.json
├── docker-compose.yml         # optional local Postgres
└── README.md
```

## Windows Quick Start (One-Click)

1. Make sure required system dependencies are installed (**Python 3.11+** and **Node.js 18+**).
2. Configure `backend/.env` if using a custom database or OAuth keys (defaults to the provided Supabase/PostgreSQL instance or local Docker).
3. Double-click `run.bat` (or run `./run.bat` in a terminal).
4. The launcher will automatically check dependencies, set up virtual environments, install packages, run migrations, seed data, start backend and frontend, and open the application in your default browser.

- **Default Frontend URL**: [http://localhost:5173](http://localhost:5173)
- **Default Backend URL**: [http://localhost:8000](http://localhost:8000)
- **Interactive API Docs**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **Health Check**: [http://localhost:8000/health](http://localhost:8000/health)

---

## Prerequisites

- **Python 3.11+** (must be added to PATH)
- **Node.js 18+** and **npm**
- **PostgreSQL** — either a local Docker container (`docker-compose up -d`) **or** a [Supabase](https://supabase.com) project

---

## Environment Variables

### Backend (`backend/.env`)
- `DATABASE_URL`: PostgreSQL connection string (supports `postgresql://` or `postgresql+asyncpg://`).
- `APP_ENV`: `development` or `production`.
- `CORS_ORIGINS`: Comma-separated list of allowed origins (e.g. `http://localhost:3000,http://localhost:5173`).
- `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`: (Optional) Google OAuth credentials.
- `DIGILOCKER_CLIENT_ID`, `DIGILOCKER_CLIENT_SECRET`: (Optional) DigiLocker OAuth credentials.

### Frontend (`frontend/.env`)
- `VITE_API_URL`: Backend API endpoint (e.g. `http://localhost:8000/api/v1`).

---

## Common Startup Errors & Troubleshooting

- **`psycopg2` / DB driver error**: The app uses `asyncpg` for async SQLAlchemy. Ensure `DATABASE_URL` is properly formatted (automatically normalized in `app/config.py`).
- **Port conflicts**: Make sure ports `8000` (FastAPI) and `5173` (Vite) are not occupied by other processes.
- **Python not found**: Ensure Python 3.11+ is installed and "Add Python to PATH" was selected during installation.

---

## Backend — one-time setup

```powershell
cd "D:\TY (5th Sem)\EDI\Project\welfare-intelligence-platform\backend"

# 1. Create and activate the virtual environment
python -m venv venv
.\venv\Scripts\Activate.ps1        # PowerShell
# source venv/bin/activate         # Mac / Linux

# 2. Install dependencies
pip install -r requirements.txt

# 3. Create your environment file
copy .env.example .env
# Then edit .env — see "Environment variables" below

# 4. Apply all database migrations
alembic upgrade head

# 5. Seed scheme data, form definitions and the scheme catalogue
$env:PYTHONPATH="."; python scripts/seed.py
$env:PYTHONPATH="."; python scripts/seed_forms.py
```

### Start the backend

```powershell
cd backend
.\venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

- API: `http://127.0.0.1:8000`
- Interactive docs: `http://127.0.0.1:8000/docs`

---

## Frontend — one-time setup

```powershell
cd frontend
npm install
```

Create `frontend/.env.local` (or `.env`):

```
VITE_API_URL=http://localhost:8000/api/v1
```

### Start the frontend

```powershell
cd frontend
npm run dev
# App available at http://localhost:5173
```

> The Vite dev server also proxies `/api` to `http://127.0.0.1:8000`, so the app works even without `VITE_API_URL` if the backend is running locally on port 8000.

---

## Environment variables (`backend/.env`)

Copy from `backend/.env.example` and fill in. **`backend/.env` is gitignored — never commit it.**

| Variable | Notes |
|---|---|
| `DATABASE_URL` | **Must use the async driver prefix `postgresql+asyncpg://`** — a plain `postgresql://` URL makes SQLAlchemy try to import psycopg2 and crash on startup (see Troubleshooting). Supabase direct connection: `postgresql+asyncpg://postgres:<password>@db.<project-ref>.supabase.co:5432/postgres` |
| `APP_ENV` / `APP_HOST` / `APP_PORT` / `LOG_LEVEL` | Application settings |
| `CORS_ORIGINS` | Comma-separated allowed origins (must include `http://localhost:5173`) |
| `DB_POOL_SIZE` / `DB_MAX_OVERFLOW` | Optional connection-pool tuning |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` / `GOOGLE_REDIRECT_URI` | Optional — Google OAuth sign-in (leave empty to disable) |
| `DIGILOCKER_CLIENT_ID` / `DIGILOCKER_CLIENT_SECRET` / `DIGILOCKER_REDIRECT_URI` / `DIGILOCKER_BASE_URL` | Optional — DigiLocker / MeriPehchaan sign-in |

---

## Database migrations

`alembic upgrade head` reads `DATABASE_URL` from `backend/.env` and applies everything in `backend/alembic/versions/`:

| Revision | What it creates |
|---|---|
| `0001_initial_schema` | `scheme_master`, `scheme_rule_groups`, `scheme_eligibility_rules`, `scheme_document_master` |
| `0002_persona_and_diagnostics` | Persona / diagnostics tables |
| `0003_phase1_database_foundation` | Phase-1 core tables |
| `0004_auth_user_and_ownership` | `tbl_user_account`, `tbl_user_role`, `tbl_user_session`, `owning_user_id` ownership guards |
| `0005_add_profile_types_to_citizen` | `profile_types` JSONB on `tbl_citizen_master` |
| `0006_domain_documents` | `tbl_citizen_document` (document upload + validation) |
| `0007_oauth_and_linking` | OAuth columns on `tbl_user_account`: nullable `password_hash`, `google_id`, `digilocker_id`, `full_name` |

Useful commands:

```bash
alembic current        # which revision the DB is at
alembic heads          # should show exactly ONE head: 0007_oauth_and_linking
alembic downgrade -1   # roll back one step (dev only)
```

Migrations change **structure only** — run the seed scripts afterwards for data.

---

## Running tests

```powershell
# Backend (from backend/, venv active)
python -m pytest tests/test_auth_system.py -q          # quick smoke
python -m pytest tests/ -q                             # full suite

# Frontend (from frontend/)
npm test        # Vitest, single run
npm run lint    # oxlint
npm run build   # production build check
```

> Some backend suites need a reachable database. If the network or Supabase DNS is flaky, run suites individually rather than the full suite.

---

## Troubleshooting

**`ModuleNotFoundError: No module named 'psycopg2'` on `alembic upgrade head` or `uvicorn`**
`DATABASE_URL` in `backend/.env` is missing the async driver. Change the scheme from
`postgresql://` to `postgresql+asyncpg://` (one line, keep everything else identical).
There is no need to install psycopg2.

**`Multiple head revisions are present`**
Two migrations share the same `down_revision`. `alembic heads` should show only
`0007_oauth_and_linking`. If a teammate pulled a renamed migration while your DB was
stamped with the old ID, realign with:
```bash
alembic stamp 0006          # point at the revision your schema actually has
alembic upgrade head
```

**`DuplicateColumnError: column "profile_types" ... already exists`**
The schema was applied out-of-band but `alembic_version` is stale. Check what actually
exists in the DB, then `alembic stamp <matching-revision>` before upgrading. Never
re-run migrations on top of an already-applied schema.

**`ValueError` from passlib / bcrypt on register or login**
`requirements.txt` pins `bcrypt>=4.0,<4.1` on purpose — passlib 1.7.4 is incompatible
with bcrypt 5.x. Do not upgrade bcrypt.

**Supabase `getaddrinfo failed` / DNS errors**
Transient network flakiness on some networks. Retry; live-DB tests and seed scripts
fail with this error even when the code is correct.

**Port already in use (8000 / 5173)**
Kill the stale process: `netstat -ano | findstr :8000` then `taskkill /PID <pid> /F`
(Windows), or just stop the old terminal.

**History-rewrite teammates note**
If a teammate still has pre-rewrite clones, their next pull may conflict. Run
`git fetch && git reset --hard origin/main` (or re-clone) to align with the rewritten
history.

---

## Team & workflow

- `main` is the stable branch; feature branches merge via PR.
- Before pushing: `npm run build` (frontend) and `python -m pytest tests/test_auth_system.py -q` (backend) must pass.
- Never commit `.env`, `venv/`, `.venv/`, or `node_modules/`.
