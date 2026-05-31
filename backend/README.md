# Brim Backend

FastAPI backend for the Brim Expense Intelligence Copilot.

The backend owns authoritative policy checks, risk scoring, approvals, reports, and AI orchestration. Approval APIs return complete decision packets for human approve/deny decisions only. Report APIs include workflow metrics, citations, visuals, CSV export, and approval/readiness context.

## Setup

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Create `backend/.env` from `backend/.env.example`. You can reuse the same Supabase project values as the frontend, but keep service-role and AI keys backend-only.

## Run

```powershell
cd backend
python -m uvicorn app.main:app --reload
```

The API runs at `http://localhost:8000` by default.

## Test

```powershell
cd backend
python -m pytest
```

## Frontend Connection

Set this in the frontend `.env`:

```env
VITE_BACKEND_URL=http://localhost:8000
```

React continues to use its existing Supabase import flow for now. Backend-owned workflows call FastAPI, and the dashboard health card verifies `React -> FastAPI -> Supabase`.
