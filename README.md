# Welfare Intelligence Platform

An AI-based welfare scheme eligibility and citizen benefit matching engine.

## Prerequisites
- Python 3.11+
- Node.js 18+
- PostgreSQL (or Docker)

## Setup

### Database
You can use Supabase or run a local PostgreSQL instance using Docker:
```bash
docker-compose up -d
```

### Backend Setup
```bash
cd backend
python -m venv venv
# Activate venv:
# Windows: venv\Scripts\activate
# Mac/Linux: source venv/bin/activate

pip install -r requirements.txt

# Copy .env config
cp .env.example .env

# Run migrations
alembic upgrade head

# Seed initial data
PYTHONPATH=. python scripts/seed.py

# Run the API
uvicorn app.main:app --reload
```

### Frontend Setup
```bash
cd frontend
npm install
# Ensure .env exists with VITE_API_URL=http://localhost:8000/api/v1
npm run dev
```

Visit `http://localhost:5173` to view the application.
