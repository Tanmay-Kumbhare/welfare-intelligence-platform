# Welfare Intelligence Platform

An AI-based welfare scheme eligibility and citizen benefit matching engine.

## Prerequisites

- Python 3.11+
- Node.js 18+
- PostgreSQL — either a local Docker container **or** a [Supabase](https://supabase.com) project

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
