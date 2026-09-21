# AGENTS.md — Rules for coding agents

**Read `PROJECT_STATE.md` first, every session.** It is the authoritative
record of what is implemented, what is planned, and what must not be claimed
as done. These rules exist so agents can continue this project safely without
rewriting, regressing, or inventing parts of it.

## Non-negotiable rules

1. **Read `PROJECT_STATE.md` before writing any code.** Then inspect the
   actual code — never assume behaviour from memory or a spec alone.
2. **Never rewrite, reconstruct, or "clean up" the application wholesale.**
   Make the smallest change that addresses the task.
3. **Inspect existing code before implementing anything.** Search for existing
   models, services, repositories, schemas, and components first.
4. **Reuse existing models/services/repositories.** Extend the canonical
   registry (`app/services/profile_mapping.py`) rather than hardcoding
   per-question mappings.
5. **Do not duplicate existing functionality** (a second form renderer, a
   second age calculation, a second eligibility path, parallel API clients).
6. **Do not remove existing features without explicit instruction** in the
   current task.
7. **Any DB schema change requires an Alembic migration** — additive, with
   working `upgrade()` *and* `downgrade()`. Never edit, squash, or rewrite
   historical migrations; the chain is `0001 → 0002 → 0003 → …`.
8. **Never fabricate government scheme data or official provenance.** The 7
   seeded schemes are development seed data. Real schemes must come from real
   sources recorded in the provenance tables.
9. **Eligibility is deterministic and explainable.** No randomness, no
   undocumented heuristics; every assessment keeps audit-ready
   `evaluation_details`.
10. **LLM/NLP may assist extraction only — never decide eligibility.** Any
    machine-extracted rule is a *candidate* until human-reviewed and published.
11. **Recommendation stays separate from eligibility.** Ranking/presentation
    layers must not alter assessment outcomes.
12. **Preserve the citizen_id identity workflow**: one identity created at
    profile registration; ownership checks compare `citizen_id` only; never
    match citizens by name/DOB/gender; never silently create duplicates.
13. **Preserve dynamic forms**: the DB (not the frontend) is the question
    catalogue; new form versions are additive (v3 is active; v1/v2 are frozen
    history).
14. **Preserve profile-fact normalization** (answers → registry → domain
    profiles → facts → provenance) and its idempotency.
15. **Preserve provenance**: facts and (future) rules must remain traceable to
    their source answers/documents.
16. **Work phase-by-phase** per `PHASE_3B_TO_3F_IMPLEMENTATION_SPEC.md`;
    **do not jump ahead** to later Phase 3 stages or mix phases in one task.
17. **Run the relevant tests before committing** (`pytest` for touched backend
    areas; `vitest` + build for frontend changes). Report results honestly —
    never fabricate passing tests or measurements.
18. **Never use destructive Git commands** (`reset --hard`, `clean`,
    `checkout .`, `restore .`, force push, history rewriting).
19. **Never commit secrets or artifacts**: `.env*`, credentials, tokens,
    `.freebuff/`, virtual environments, `node_modules/`, `frontend/dist/`,
    `__pycache__/`, caches, logs, or temporary/generated files.
20. **Version-pinned submissions stay valid**: existing submissions reference
    their form version; never mutate seeded form versions or their questions.

## Useful entry points

- Backend: `backend/app/` (api/v1, services, repositories, models, schemas),
  tests in `backend/tests/`, seeds in `backend/seed_data/`.
- Frontend: `frontend/src/pages/CheckEligibilityPage.jsx` (dynamic form),
  `frontend/src/components/forms/`, API client `frontend/src/services/api.js`.
- DB state helpers: `backend/scripts/verify_db_state.py`,
  `backend/scripts/verify_api_live.py`.
- Local backend venv: `backend/.venv/Scripts/python.exe` (Windows);
  run pytest from `backend/`.
