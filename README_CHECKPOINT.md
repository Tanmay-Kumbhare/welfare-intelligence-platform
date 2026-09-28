# VidyaSetu — Checkpoint 1 + 2 delivery

This archive contains only the files created or changed for:
- Checkpoint 1: application shell, routing, UI primitives
- Checkpoint 2: real, API-backed Home page

## How to apply

Copy the `frontend/` folder here directly over your existing
`frontend/` folder in the repo (same relative paths). Nothing under
`backend/` was touched in this checkpoint.

```
cp -r frontend/* /path/to/welfare-intelligence-platform/frontend/
```

Then, from `frontend/`:

```
npm install
npm run dev
```

The dev server proxies `/api` to `http://127.0.0.1:8000` (see
`vite.config.js`, unchanged), so run the FastAPI backend locally
against your real Supabase/Postgres database for the Home page's
scheme data to load.

## Not included here (untouched this checkpoint)

- `frontend/src/pages/ResultsPage.jsx` — still the working V1 version
  from before this checkpoint; its Part 9 upgrade is scheduled for
  Checkpoint 5.
- `frontend/src/services/api.js` — untouched; already sufficient for
  Checkpoints 1–2.
- Everything under `backend/` — no backend changes were required for
  Checkpoints 1–2.

See the chat report for the full file list, routes, and known
limitations.
