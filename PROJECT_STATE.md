# PROJECT_STATE.md — Welfare Intelligence Platform (VidyaSetu)

**Status:** V2 complete and checkpointed. Phase 3B not started.
**Last updated:** 2026-09-21 (pre-Phase-3B checkpoint).

This is the **authoritative implementation-state document**. Every future coding
agent must read it (see `AGENTS.md`) before changing anything. It deliberately
separates what the code actually does today from what is only planned.

Legend: **IMPLEMENTED** = in the code and covered by tests · **PLANNED** =
designed in a spec, not built · **NOT IMPLEMENTED** = absent, no spec yet ·
**KNOWN LIMITATION** / **KNOWN BUG** = accepted current issues.

---

## 1. Mission and invariants

VidyaSetu captures a citizen profile, evaluates it against stored welfare-scheme
rules, and explains the outcome. The platform is deliberately deterministic:

- **The eligibility engine is deterministic and explainable.** Every assessment
  stores per-rule evidence (`evaluation_details`) so a human can audit why a
  citizen is or is not eligible.
- **LLM/NLP must not directly decide citizen eligibility.** If introduced in
  Phase 3, they may only assist *extraction* (e.g. scheme documents → candidate
  rules) with human review before publication.
- **Recommendation must remain separate from eligibility.** Recommendation is a
  presentation/ranking layer; it never changes an assessment's outcome.

---

## 2. IMPLEMENTED — V1 baseline

Full-stack app: FastAPI + async SQLAlchemy + PostgreSQL (Supabase-compatible),
React 19 + Vite + Tailwind v4 frontend.

- Citizen identity: `tbl_citizen_master` plus one-to-one demographic, financial,
  and location profile tables (`tbl_demographic_profile`,
  `tbl_financial_profile`, `tbl_location_profile`).
- Schemes: `tbl_scheme_master`, rule groups (`tbl_scheme_rule_group`),
  rules (`tbl_scheme_eligibility_rule`), documents
  (`tbl_scheme_document_master`), assessments (`tbl_eligibility_assessment`).
- 7 seeded development schemes (`backend/seed_data/schemes.json`). These are
  **seed data**, not government-ingested records.
- Deterministic eligibility engine (`app/services/eligibility_engine.py`) with
  explainable per-rule evaluation details.
- Recommendation service and results page (ranking over eligibility outcomes).
- Migrations `0001` and `0002` (V1 schema), all subsequent migrations additive.

## 3. IMPLEMENTED — Phase 1/V2 database foundation (migration `0003`)

Additive migration only; no V1 data modified.

- Dynamic form tables: `tbl_form_definition`, `tbl_form_section`,
  `tbl_form_question`, `tbl_form_question_option`, `tbl_form_condition`.
- Submission tables: `tbl_form_submission`, `tbl_form_answer` (typed answer
  columns: text / integer / decimal / boolean / date / JSON).
- Profile-fact tables: `tbl_profile_fact` (one open fact per
  citizen + fact_code, closed history via `effective_until`) and
  `tbl_profile_fact_provenance` (links a fact to its source answer and
  derivation).
- Scheme source/provenance tables: `tbl_scheme_source`,
  `tbl_scheme_source_document`, `tbl_scheme_source_content` (raw content
  preserved verbatim), `tbl_scheme_rule_provenance`,
  `tbl_scheme_ingestion_run`.
- Scheme master canonical metadata columns (all nullable): official scheme
  identifier, source type/name/URL, application window type, end date,
  `scheme_version`, `last_updated_at`, `last_verified_at_ts`.
- Assessment enrichment columns: `eligibility_status` (canonical status string),
  `missing_facts`, `missing_documents`, `confidence_score`,
  `assessment_version`, `created_at`, `updated_at`.

## 4. IMPLEMENTED — Versioned dynamic forms (Phases 2A/2B)

- `GENERAL_CITIZEN_PROFILE` has three seeded versions in
  `backend/seed_data/forms.json`, seeded idempotently by
  `backend/scripts/seed_forms.py`:
  - **v1** — original 7-section/19-question form. **Frozen**: kept intact so
    version-pinned submissions remain valid. It contains 3 legacy questions
    that today's stricter seed validation would reject (grandfathered).
  - **v2** — 12 sections / 64 questions / 95 options / 32 conditions.
    **Superseded but immutable**: it duplicated identity questions
    (full name, date of birth, gender) that are now collected only at
    profile creation.
  - **v3** — **active version**: 12 sections / 61 questions / 92 options /
    32 conditions. Identity questions removed; welfare attributes only.
- Seed-time validation (unique form code/version, unique question codes,
  valid types/data types/options/conditions/profile fields/fact codes, no
  circular conditions) runs for **newly created** forms; already-seeded
  frozen versions are never rewritten.
- Form API: `GET /api/v1/forms/GENERAL_CITIZEN_PROFILE` returns the full
  section → question → option → condition hierarchy of the active version.
- Deterministic condition system (Phase 2A): conditions share
  `condition_group` — conditions in one group are ANDed, groups are ORed;
  actions SHOW / HIDE / REQUIRE. Evaluated server-side by
  `app/services/form_logic.py`.
- Submission lifecycle: create draft → save/update answers → complete →
  normalize → eligibility. Drafts support resume; completion validates all
  applicable required questions and rejects incomplete submissions.
- Profile normalization (Phase 2B): answers → canonical profile registry
  (`app/services/profile_mapping.py`, 74 entries) → domain profile columns →
  profile facts → provenance. Deterministic value coercion (e.g.
  `₹2,40,000` / `2.4 lakh` / `240000` → numeric income). 8 derivation rules:
  AGE ← DATE_OF_BIRTH; SENIOR_CITIZEN ← AGE; MINORITY_STATUS ← RELIGION;
  WIDOW_STATUS ← MARITAL_STATUS + GENDER; IS_BPL_CARD_HOLDER ←
  POVERTY_CATEGORY; SELF_EMPLOYED ← EMPLOYMENT_STATUS; TENANT_FARMER and
  SHARECROPPER ← FARMER_TYPE. Repeated normalization is idempotent.

## 5. IMPLEMENTED — Canonical identity and AGE

- **One citizen identity**, created at profile registration
  (`POST /api/v1/citizens/`). The frontend stores the returned `citizen_id`
  in `localStorage["vidyasetu.citizen_id"]` and passes it to every form,
  submission, and eligibility call. Backend ownership is enforced by
  `citizen_id` comparison only (403 "Submission belongs to another citizen"
  on mismatch) — never by name/DOB/gender matching.
- The welfare form **never re-asks identity fields**; the frontend shows a
  read-only identity summary from the citizen record. Missing/stale pointer →
  explicit registration gate (no silent second citizen).
- **Canonical AGE chain**: `DATE_OF_BIRTH` → `calculate_age()`
  (`app/utils/date_calc.py`, completed-birthday math, Feb-29 → Mar-1
  non-leap) → `AGE` profile fact → engine consumes the open AGE fact
  (fallback: `calculate_age(identity DOB)` only for citizens with no fact
  layer). Age was previously computed independently in the engine; that
  duplicate source was removed and is covered by regression tests.

## 6. IMPLEMENTED — Dynamic frontend

- `frontend/src/pages/CheckEligibilityPage.jsx` renders whatever active form
  the API returns; the question catalogue exists **only in the database**.
- Components: `FormSection`, `FormQuestion`, per-type inputs (text, number,
  date, boolean, select, multi-select), `FormProgress`, `ReviewStep`, and
  `formLogic.js` (presentation-level condition evaluation mirroring backend
  semantics; backend remains authoritative).
- Multi-step experience follows API section order; saves persist before
  navigation; failed saves retain local answers; hidden questions are never
  submitted; backend validation errors map to the offending question.
- Lifecycle on submit: save → complete → normalize → existing eligibility
  evaluation → results/recommendation pages.

## 7. IMPLEMENTED — Tests

Backend (`backend/tests/`, pytest against the real dev database; several
suites use transactional rollback or clean up their own fixtures):

| Suite | Focus |
| --- | --- |
| `test_api.py`, `test_phase1_foundation.py` | API + Phase 1 schema/behaviour |
| `test_phase2a_forms.py` | forms, conditions, submissions |
| `test_phase2b_normalization.py` | normalization, facts, provenance |
| `test_phase2c_blueprint.py` | v3 form structure, seed idempotency |
| `test_age_consistency.py` | canonical AGE chain |
| `test_identity_workflow.py` | identity/ownership regressions |
| `test_eligibility_engine.py` | engine semantics |
| `test_eligibility_performance.py` | query-count assertions |

Frontend (`vitest` + Testing Library, mocked API): form loading/error states,
dynamic rendering, conditional visibility, draft save/resume, review,
completion, normalization call, identity-flow regressions. Production build
(`vite build`) passes.

## 8. IMPLEMENTED — Eligibility performance optimization

Structural DB round-trip reduction (tested, not latency-measured):

- Citizen/profile load: 5 queries → 2 (joined one-to-one profiles; eager
  facts).
- Scheme evaluation load: 4 queries → 1 (evaluation-only rule-graph join;
  documents skipped).
- Assessment persistence: 7 sequential upserts → 1 batch upsert.
- Route structure: ~16 SQL executions → 4.

## 9. KNOWN LIMITATIONS

- **No authentication.** Ownership is the localStorage `citizen_id` pointer;
  anyone with the id can act as that citizen. Acceptable for development;
  authentication is a planned later phase.
- **No live scheme ingestion.** All 7 schemes are seed data. Source tables
  exist but nothing populates them yet.
- **Document upload is not implemented** — the form's document questions are
  availability flags only.
- **Frozen v1 form** contains legacy questions that modern seed validation
  would reject; it is never rewritten.
- **Frontend test/dev duplication:** React StrictMode is enabled; draft
  creation is guarded, but new mount-time effects must stay idempotent.
- **Remote DB sensitivity:** the dev database is hosted; long test runs can
  hit transient connection resets. Suites assume cleanup of their own
  fixtures; killed runs can leave orphans (clean manually or re-run).
- **Seed schemes' provenance is MANUAL_SEED** by construction; do not invent
  government provenance for them.

## 10. KNOWN BUGS

- None currently known open. (The historical age mismatch and the
  "belongs to a different user" identity bug are fixed and regression-tested.)

## 11. Phase 3A — architecture findings (IMPLEMENTED as docs)

`PHASE_3A_SCHEME_ARCHITECTURE_AUDIT.md` inventories the existing scheme/source/
rule/document models and identifies the exact gaps for ingestion. Key
findings: raw source content must be preserved verbatim; scheme master must
hold only canonical curated fields; rule provenance must link every rule to
its evidence; the engine must stay deterministic.

## 12. PLANNED — Phase 3B–3F (NOT IMPLEMENTED)

`PHASE_3B_TO_3F_IMPLEMENTATION_SPEC.md` is the approved blueprint. Summary:

- **3B — ingestion:** source registry, scheduled/manual fetch, raw snapshots,
  content extraction plumbing. No rule changes without review.
- **3C — candidate extraction + validation:** extracted candidate rules and
  evidence, human validation workflow.
- **3D — immutable published versions:** publish workflow, versioned scheme
  records; evaluations pinned to the version used.
- **3E — fact registry + deterministic DSL:** rule DSL over the profile-fact
  registry; engine consumes published DSL, remains explainable.
- **3F — recommendation intelligence:** ranking/explanation layer, separate
  from eligibility.

**Explicitly NOT IMPLEMENTED anywhere:** live government scheme ingestion,
automatic crawling, candidate extraction, review/publish workflow, immutable
published scheme versions, tri-state eligibility evaluation
(ELIGIBLE / NOT_ELIGIBLE / POTENTIALLY_ELIGIBLE status columns exist but the
engine still emits boolean results), recommendation intelligence.

## 13. Next step after this checkpoint

1. Human review of the checkpoint commits (see `git log`), then push.
2. Begin **Phase 3B only** per `PHASE_3B_TO_3F_IMPLEMENTATION_SPEC.md`
   §4 (source snapshots and ingestion tables/logic), following `AGENTS.md`.

## 14. API surface (current)

- `/health`
- `/api/v1/citizens/` — create/get/update citizen + sub-profiles
- `/api/v1/forms/GENERAL_CITIZEN_PROFILE` — active form hierarchy
- `/api/v1/forms/submissions/` — create/update/complete submissions
- `/api/v1/forms/submissions/{id}/normalize` — profile normalization
- `/api/v1/eligibility/{citizen_id}/evaluate` — evaluate all active schemes,
  batch-persist assessments
- `/api/v1/schemes/` — scheme catalogue and documents
- Recommendation endpoints for the results flow

## 15. Migrations

Chain (never rewritten or squashed): `0001` (V1 core) → `0002` (V1 indexes /
refinements) → `0003` (additive Phase 1/V2 foundation). Future schema changes
require new additive Alembic migrations with working upgrade *and* downgrade.
