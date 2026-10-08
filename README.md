# Welfare Intelligence Platform

An AI-based welfare scheme eligibility and citizen benefit matching engine.

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

## Setup

### Database

**Option A — Local Docker (default)**

```bash
docker-compose up -d
# Creates a postgres container at localhost:5432
```

**Option B — Supabase**
Point `DATABASE_URL` in `backend/.env` to your Supabase direct-connection string (port 5432).

---

### Backend Setup

```bash
cd backend

# 1. Create and activate virtual environment
python -m venv venv

# Windows (PowerShell)
venv\Scripts\activate
# Mac / Linux
source venv/bin/activate

# 2. Install dependencies
#    Includes greenlet, which is required by SQLAlchemy async + Alembic
pip install -r requirements.txt

# 3. Copy and configure environment
cp .env.example .env
# Edit .env and set DATABASE_URL to point at your Postgres instance

# 4. Run database migrations
#    Creates all tables in the database defined by DATABASE_URL in your .env
alembic upgrade head

# 5. Seed initial scheme data
# Windows (PowerShell)
$env:PYTHONPATH="."; python scripts/seed.py
# Mac / Linux
PYTHONPATH=. python scripts/seed.py

# 6. Start the API server
uvicorn app.main:app --reload
# API available at http://localhost:8000
```

> **Where does `alembic upgrade head` migrate?**
> It reads `DATABASE_URL` from `backend/.env` (via `app/config.py`) and runs all pending
> migration scripts in `backend/alembic/versions/` against that Postgres database.
> Currently there are two migrations:
>
> - `0001_initial_schema` — creates `scheme_master`, `scheme_rule_groups`, `scheme_eligibility_rules`, `scheme_document_master`
> - `0002_persona_and_diagnostics` — adds persona/diagnostics tables
>
> Migrations only create/alter **structure** (tables, columns, indexes) — no data is touched.
> Run `seed.py` separately afterwards to load scheme data.

---

### Frontend Setup

```bash
cd frontend
npm install
npm run dev
# App available at http://localhost:5173
```

> Ensure `frontend/.env` (or `frontend/.env.local`) contains:
>
> ```
> VITE_API_URL=http://localhost:8000/api/v1
> ```

Visit `http://localhost:5173` to view the application.
