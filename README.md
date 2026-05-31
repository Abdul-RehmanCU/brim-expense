# Brim Expense Intelligence Copilot

React + Vite frontend with Supabase data storage and a Python FastAPI backend for business logic.

The existing CSV import and normalization flow still runs in the React app. FastAPI owns policy/risk services, approvals, reports, and AI orchestration; React calls it through the configured backend URL.

## Canonical Local URLs

- Frontend: `http://localhost:5173`
- Backend: `http://localhost:8000`

## Frontend

```powershell
npm install
npm run dev
```

The frontend expects:

```env
VITE_SUPABASE_URL=
VITE_SUPABASE_ANON_KEY=
VITE_BACKEND_URL=http://localhost:8000
```

## Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```

Create `backend/.env` from `backend/.env.example`. Server-only keys stay in the backend and must not be copied into React code.

## Tests

Frontend:

```powershell
npm run build
npm run lint
npm test
```

Backend:

```powershell
cd backend
python -m pytest
```
