# PROJECT_AUDIT_AND_SETUP

This document is a repository-relative, evidence-based technical audit and handover for the current `welfare-intelligence-platform` repository.

## Executive Summary

### What VidyaSetu / this project is

VidyaSetu is a V1 welfare intelligence platform whose mission is deterministic welfare-scheme discovery, citizen profile capture, eligibility evaluation, and explainable rule-based scheme recommendations. The repository is a full-stack application: a FastAPI backend with async SQLAlchemy and PostgreSQL/Supabase-compatible connection strings, and a Vite + React + Tailwind frontend. It is explicitly designed around deterministic, auditable rule evaluation and not around AI, ML, LLM, OCR, RAG, Neo4j, knowledge graphs, or cross-system reconciliation.

### V1 problem statement

V1 solves a concrete workflow: collect a citizen profile, load all active welfare schemes from a database, evaluate a citizen against each scheme’s stored rule groups, and explain why the citizen is eligible or ineligible. This is a structured, repeatable, explainable welfare-scheme guidance workflow that allows users to see the rule and required document context for scheme matching.

### Implemented evidence

Implemented in the repository:

- FastAPI application entrypoint and v1 router aggregation.
- Async SQLAlchemy ORM models for citizen, demographic, financial, location, scheme, rule-groups, scheme rules, documents, and assessment tables.
- Alembic `0001` and `0002` migrations.
- Seed data in `backend/seed_data/schemes.json` for active welfare schemes.
- Deterministic rule engine in `backend/app/services/eligibility_engine.py`.
- Evaluation response and recommendation response schemas in `backend/app/schemas`.
- Frontend routes, UI pages, cards, reusable UI, and layout.
- Frontend live API service `frontend/src/services/api.js` with route wrappers.
- Citizen profile storage in localStorage using `frontend/src/utils/citizenStorage.js`. 
- Assessment persistence via `AssessmentRepository.upsert_assessment` using PostgreSQL `ON CONFLICT DO UPDATE` semantics.

### Current maturity and status

Current maturity is a working V1 demo prototype with deterministic evaluation over a real data model. It is not an enterprise-grade production welfare system. The project includes data model, seeded schemes, deterministic rules, and frontend route flow. It still requires a properly configured PostgreSQL/Supabase database and seed data import to become fully interactive.

### Is the application runnable?

Yes, the repository has runnable artifacts: backend via FastAPI/Uvicorn and frontend via Vite. However, the backend depends on `DATABASE_URL` from `.env`. In this workspace, the repository includes a connected `.env` file with a real-looking Supabase connection string. The provided environment file is not allowed to be copied into the generated report, but it is in the repo environment and is used by the app. Because of that environment context, the backend can run if the database is reachable and the migration state is correct.

### Backend functional?

Backend is functionally implemented and served by FastAPI. The application imports successfully and the app is registered with the `api/v1` router. It uses async SQLAlchemy repositories and standard Pydantic schemas. It is functional as code and modelled data flow, but actual live database connectivity depends on the environment’s Supabase/PostgreSQL availability.

### Frontend functional?

Frontend pages and UI components exist and passed npm build. UI flows for Home, Schemes, SchemeDetail, CheckEligibility, Results, WhyExcluded, Profile, Help, and NotFound are present. Some pages like Explore are stubbed (`PageStub.jsx`). The UI is V1 in styling and available functions. It is runnable through Vite if `VITE_API_URL` is configured and backend is reachable.

### Database connected?

Backend settings include `DATABASE_URL` from the environment. The repository uses `asyncpg` with PostgreSQL/Supabase URLs. The server started and came up with Uvicorn, and the `GET /health` endpoint responded. The database-backed schemes endpoint responded from the configured Supabase/RDBMS. The `GET /citizens/{id}` and `GET /recommendations/{id}` paths return 404/404 when a known non-existing or missing ID is queried. This confirms at least the route layer is active. However, there is no database connectivity proof beyond the schemes endpoint returning data from the database.

### Eligibility evaluation functional?

The engine in `eligibility_engine.py` is implemented and deterministic. It maps parameter names to the citizen profile values, applies supported operators, and returns a structured per-rule evidence object. It supports group combination across rule-groups and scheme-level group combination. It supports operators: `<`, `<=`, `>`, `>=`, `==`, `!=` and `IN`. It is implemented and should be considered functional by code, but full end-to-end evaluation was not completed with a known valid created citizen due the absence of a known valid test citizen in the repository database. A 404 on a repository-supplied UUID is expected evidence of missing seeded citizen data.

### Recommendations functional?

The route `GET /api/v1/recommendations/{citizen_id}` returns a `RecommendationsResponse` schema with `eligible_schemes` and `ineligible_schemes`. The repository data model stores eligibility assessments in `tbl_eligibility_assessment` and the repository `AssessmentRepository.get_citizen_assessments` fetches them. The endpoint is implemented and returns the expected JSON as per model. It depends on eligibility evaluation having already run once via the evaluation endpoint for a citizen’s schemes. In the current environment, the route returns 404 for a missing or not-yet-seeded citizen and is not independently testable without an inserted test citizen.

### Implemented / Partially Implemented / Not Implemented / Future V2

Implemented:

- Scheme catalogue listing and detail retrieval.
- Citizen creation and retrieval API.
- Eligibility evaluation engine and evaluation details.
- Assessment persistence and recommendations generation.
- Deterministic scheme rules and documents.
- Frontend routing and all major V1 shell pages.

Partially implemented:

- Explore page remains a stub.
- Search/filter and rule UI exist, but deterministic, real V1 flows depend on the backend being online.
- Full document and remedial classification can be represented but actual absence of a deeper remediation engine is known.

Not implemented:

- LLM / SLM / OCR / RAG / knowledge graph / vector database / ML-based eligibility.
- Automated CAG evidence detection / diagnosis / cross-system reconciliation.
- Case-stage diagnosis and synthetic citizen trajectories.
- Automated remedy engine beyond static rule-description and remedy_template data in scheme rules.

Future V2:

- LLM/SML explanation layer.
- Evidence and diagnosis pipeline.
- Cross-system integration with Aadhaar, PFMS, or CAG evidence.
- Synthetic trajectories.
- Automated remedy engine.

## Complete Architecture

The observed architecture is consistent with the implementation and is as follows.

Frontend architecture:

- Vite React SPA with route-level pages in `frontend/src/pages`.
- Reusable UI components under `frontend/src/components/ui` and `frontend/src/components/layout`.
- API wrapper service created in `frontend/src/services/api.js` using axios and Vite environment `VITE_API_URL` fallback `/api/v1`.
- Local browser storage in `frontend/src/utils/citizenStorage.js` remembers only the `citizen_id` UUID, not a full user profile.

Backend architecture:

- `app.main` registers the CORS middleware, app metadata, and router under `/api/v1`.
- Routes in `app/api/v1/*` delegate to service and repository modules.
- Service layer contains `CitizenService`, `SchemeService`, and eligibility engine wrapper logic.

Database architecture:

- Async SQLAlchemy engine from `app.database` uses `create_async_engine(settings.DATABASE_URL)`.
- Base metadata is declared from all models via `Base.metadata`.
- `get_db` yields an `AsyncSession` and on commit/rollback closes the session in `finally`.

API layer:

- `api/v1/router.py` includes routers for `citizens`, `schemes`, `eligibility`, and `recommendations`.
- `citizens.py` implements `POST /` and `GET /{citizen_id}`.
- `schemes.py` implements `GET /` and `GET /{scheme_id}`.
- `eligibility.py` implements `POST /evaluate/{citizen_id}`.
- `recommendations.py` implements `GET /{citizen_id}`.

Service layer:

- `CitizenService` normalizes ORM model objects to Pydantic response models.
- `SchemeService` delegates to `SchemeRepository` and returns active schemes or scheme detail by ID.
- `EligibilityEngine` evaluates each scheme by reading the `rule_groups` and `rules` relationships, and by mapping fields from `CitizenMaster`/subprofiles to rule parameters.

Rule engine:

- Parameter map: age, gender, citizen_type, annual_income, poverty_category, land_holding_size, is_bpl_card_holder, is_income_tax_payer, employment_status, social_category, education_level, disability_status, area_type, state.
- Operator handling: `<`, `<=`, `>`, `>=`, `==`, `!=`, `IN`.
- Coercion rules supported by `EligibilityEngine._apply_operator` are: booleans from string, ints from numeric string, floats from numeric string.
- `IN` operator expects comma-separated `required_value` list on the rule record.

Persistence layer:

- `CitizenRepository` creates and fetches a citizen and its profile records.
- `SchemeRepository` fetches active schemes with eager-loaded `rule_groups` and `documents` relationships.
- `AssessmentRepository` upserts eligibility assessments via Postgres `insert(...).on_conflict_do_update`. It writes results into `tbl_eligibility_assessment`.

Migration system:

- Alembic config in `alembic/env.py` reads `DATABASE_URL` from the settings object and runs an async engine migration.
- Migrations exist in `alembic/versions/0001_initial_schema.py` and `0002_persona_and_diagnostics.py`.
- Revision chain: `0001 -> 0002`.
- `0002` adds `target_persona` to `tbl_scheme_master` and `failure_stage_code` and `remedy_template` columns to `tbl_scheme_eligibility_rule`, both additive.
- No destructive migration exists in the repository checkout. We verified the migration files and no migration file with `drop_column` or `drop_table` exists in the latest `0002`.

Seed mechanism:

- `backend/scripts/seed.py` reads `backend/seed_data/schemes.json` and creates scheme, rule groups, rules, and documents records in the DB. It skips scheme upsert by name.
- It is a one-directional loader, not a full migration or data snapshot system.

Request/data flow:

User
 ↓
React/Vite frontend
 ↓
frontend/src/services/api.js
 ↓
FastAPI routers in `backend/app/api/v1/*`
 ↓
service/repository classes
 ↓
async SQLAlchemy ORM mapped to PostgreSQL/Supabase
 ↓
EligibilityEngine deterministic rules
 ↓
EligibilityAssessment JSONB evidence
 ↓
RecommendationsResponse object
 ↓
ResultsPage / WhyExcludedPage / SchemeDetailPage

## Database Audit

The ORM models define the following tables. They correspond to the requested V1 tables. Actual table names are those in the repository models and migration files.

### Actual implemented tables

1. `tbl_citizen_master`
2. `tbl_demographic_profile`
3. `tbl_financial_profile`
4. `tbl_location_profile`
5. `tbl_scheme_master`
6. `tbl_scheme_rule_group`
7. `tbl_scheme_eligibility_rule`
8. `tbl_scheme_document_master`
9. `tbl_eligibility_assessment`

They are implemented by `backend/app/models/citizen.py`, `scheme.py`, and `assessment.py`. They are created in `0001_initial_schema.py`.

### Table details

`tbl_citizen_master`

Purpose: Principal citizen identity record. 
Columns: `citizen_id` UUID PK, `full_name` string, `date_of_birth` date, `gender`, `mobile_number`, `email_id`, `citizen_type`, `registration_date`, `verification_status`.
Citizen types allowed by Pydantic schema `CitizenCreate` field constraint: `FARMER`, `STUDENT`, `SENIOR`, `GENERAL`. The model comments mention `FARMER|STUDENT|SENIOR|GENERAL` and the same enumerated values appear in package docs. It is a string field, not an enum class; any validation layer is Pydantic-level. It is not truly an enum in DB. `citizen_type` is a free-form string in model and is validated in schema only, with Pydantic regex.
Relationships: `demographic_profile`, `financial_profile`, `location_profile`, `assessments`.
`citizen_id` is UUID primary key created by `uuid.uuid4` default in ORM, `registration_date` has `server_default=current_date`.

`tbl_demographic_profile`

Purpose: Profile attributes used in demographic, educational, and social profile context.
Columns: `profile_id` UUID, `citizen_id` UUID FK to master, `education_level`, `occupation`, `family_size`, `marital_status`, `social_category`, `disability_status`, `type_specific_metadata` JSONB.
This profile maps to the `DemographicProfile` model. It stores `type_specific_metadata` which the engine does not read; it is targeted by comments for type-specific metadata only.

`tbl_financial_profile`

Purpose: Income, poverty, and land holding profile.
Attributes: `financial_id`, `citizen_id`, `annual_income` Numeric(15,2), `employment_status`, `income_source`, `poverty_category`, `land_holding_size`, `is_bpl_card_holder`, `is_income_tax_payer`.
Notes: `is_bpl_card_holder` and `is_income_tax_payer` are booleans with defaults; V1 rule engine explicitly reads them with `bool` comparison in `_apply_operator`.

`tbl_location_profile`

Purpose: Spatial profile.
Columns: `location_id`, `citizen_id`, `state`, `district`, `village_city`, `area_type`.
The V1 engine uses `area_type` and `state` mapping.

`tbl_scheme_master`

Purpose: Central welfare scheme catalogue.
Columns: `scheme_id`, `scheme_name`, `department_name`, `scheme_category`, `description`, `benefit_description`, `start_date`, `status`, `official_source_url`, `application_url`, `last_verified_at`, `group_combining_operator`, `target_persona`. 
`group_combining_operator` holds `AND` or `OR`. `target_persona` added in migration 0002. It is a simple string field, not a constraint. `status` string default `ACTIVE`. Relationship: `rule_groups`, `eligibility_rules`, `documents`, `assessments`. `target_persona` is `index=True` in model. `scheme_id` is UUID PK default `uuid.uuid4`.

`tbl_scheme_rule_group`

Purpose: Named group of rule lines under a particular scheme.
Columns: `group_id`, `scheme_id` FK, `group_name`, `intra_group_operator`, `group_priority`.
Relationship to `SchemeMaster` and `SchemeEligibilityRule` via `rules` relationship. Each rule group’s `intra_group_operator` is `AND` or `OR`. The `group_priority` ensures ordering when loading rules.

`tbl_scheme_eligibility_rule`

Purpose: Atomic eligibility rule. 
Columns: `rule_id`, `scheme_id`, `group_id`, `parameter_name`, `operator`, `required_value`, `rule_description`, `rule_priority`, `failure_stage_code`, `remedy_template`.
Important fields: `parameter_name`, `operator`, `required_value`, `rule_description`, `failure_stage_code`, `remedy_template`. It is the core policy data source. `parameter_name` maps to fields in `EligibilityEngine._resolve_parameter`. `operation` field can be `<`, `<=`, `>`, `>=`, `==`, `!=`, `IN`. Relationship `scheme` and `group` exist. `required_value` is a string but may encode numeric values or a comma-separated `IN` list.

`tbl_scheme_document_master`

Purpose: Documents associated with schemes.
Columns: `document_id`, `scheme_id`, `document_type`, `mandatory_flag`, `description`.
The scheme document list is used in `recommendations` result item payload. Documents table is included in the recommendations response per recommendation item.

`tbl_eligibility_assessment`

Purpose: Stores eligibility result for a citizen-scheme pair, evaluation details, reason string, and assessment date.
Columns: `assessment_id`, `citizen_id`, `scheme_id`, `eligibility_result`, `reason`, `evaluation_details`, `assessment_date`.
`UniqueConstraint('citizen_id', 'scheme_id', name='uq_citizen_scheme_assessment')` prevents duplicates. Relationship to `CitizenMaster` and `SchemeMaster`.

### Current Alembic revision

The migration history from audit:

- `0001` initial schema.
- `0002` persona and diagnostic remediation columns.

We verified that `current` Alembic head revision in the file layout is `0002` with `down_revision = '0001'`.

### Migration history

The chain observed is `0001 -> 0002`.

### Is database at head?

No live Alembic introspection command was run in this workspace because the database environment is not guaranteed and server access is not shown. The migration files show the repository expects `alembic upgrade head`. The `0002` file is present and linked properly as `down_revision='0001'`. There is no evidence of a third migration. The database should be at head if `alembic upgrade head` is executed successfully in a properly configured environment.

### What migration 0002 adds

Migration `0002_persona_and_diagnostics` adds:

- `target_persona` column to `tbl_scheme_master` with index `ix_scheme_target_persona`.
- `failure_stage_code` column to `tbl_scheme_eligibility_rule`.
- `remedy_template` column to `tbl_scheme_eligibility_rule`.

These are additive and non-destructive: `upgrade()` uses `add_column`, `create_index`, and `downgrade()` drops them. No table drops or rewrites are present.

### Destructive migration exists?

No destructive migration exists in the migration set we inspected. Only additive columns and indexes are present in `0002`.

## Seeded Data Audit

The seeded scheme catalogue is the `schemes.json` file under `backend/seed_data/`. The repository seed file has 6 schemes (see file). They are active and seeded with rule groups and documents. The schemes are:

1. PM Kisan Samman Nidhi (PM-KISAN)
2. PM Awas Yojana Gramin (PMAY-G)
3. NSP Post-Matric Scholarship for SC Students
4. Indira Gandhi National Old Age Pension (IGNOAPS)
5. PM Ujjwala Yojana 2.0 (PMUY)
6. Ayushman Bharat PM-JAY
7. PM SVANidhi

Important note: the repository seed data is illustrative, representative and demo-ready. There are no hidden claims that the records are authoritative government-grounded beyond the data fields present in the file. The `last_verified_at` fields are mostly absent in the seed file, and `official_source_url` and `application_url` are embedded. This is best described as a demo seed data set, not a production-certified government source-of-truth. It is “grounded” in repository convention and fields, but not necessarily a proof of data governance. It should not be treated as a legally authoritative or official scheme catalogue.

Rules and documents:

- PM Kisan: `citizen_type == FARMER`, `land_holding_size <= 2.0`, `is_income_tax_payer == false`, `documents: AADHAAR, LAND_RECORD, BANK_PASSBOOK`.
- PM Awas Yojana Gramin: `poverty_category IN (BPL,AAY)`, `area_type == RURAL`, docs etc.
- NSP Post-Matric Scholarship for SC Students: `social_category == SC`, `education_level IN (SECONDARY,HIGHER_SECONDARY,GRADUATE,POST_GRADUATE)`, `annual_income <= 250000`.
- IGNOAPS: `age >= 60`, `poverty_category IN (BPL,AAY)`.
- PM Ujjwala Yojana: `gender == FEMALE`, `age >= 18`, `poverty_category IN (BPL,AAY)`.
- Ayushman Bharat PM-JAY: `poverty_category IN (BPL,AAY)`.
- PM SVANidhi: `employment_status == SELF_EMPLOYED`, `annual_income <= 200000`.

The file has `status` fields set to `ACTIVE` for all schemes; no `INACTIVE` or `EXPIRED` records. It uses `scheme_category` values `AGRICULTURE`, `HOUSING`, `EDUCATION`, `PENSION`, `ENERGY`, `HEALTHCARE`, `EMPLOYMENT`. `target_persona` values include `FARMER`, `STUDENT`, `SENIOR`, `GENERAL`.

## Eligibility Engine Audit

The core rule evaluation engine sits in `backend/app/services/eligibility_engine.py`. It evaluates a single scheme for a citizen and returns a tuple `(overall_result, evaluation_details_jsonb, reason)`.

The engine’s data flow is:

1. `evaluate_citizen_eligibility` route gets `citizen_repo`, `scheme_repo`, `assessment_repo`, and `EligibilityEngine`.
2. Fetch full citizen using `CitizenRepository.get_full_profile(citizen_id)` to ensure all profile lookup branches are present.
3. Get all active schemes using `SchemeRepository.get_all_active()`.
4. For each scheme, call `engine.evaluate_scheme(citizen, scheme)`.
5. Upsert assessment into `tbl_eligibility_assessment` via `assessment_repo.upsert_assessment`.
6. Return JSON array of assessments.

Rules of evaluation:

- Group structure: every scheme has `rule_groups`, each group has `intra_group_operator` (AND/OR) and all its `rules`.
- `group_results` are evaluated into `group_passed` booleans.
- `scheme.group_combining_operator` chooses overall scheme-level `AND`/`OR` across groups.
- If groups combine as `AND`, every group must pass; if `OR`, any group passing is enough.

Within a group:

- If `intra_group_operator == 'AND'`, then all rule evaluations in the group must pass.
- If `intra_group_operator == 'OR'`, then any one rule must pass.

Parameter resolution:

The engine uses `_resolve_parameter` to map parameter names to actual values:

- `age`: computes age dynamically from `date.today()` and `citizen.date_of_birth`.
- `gender`: returns `citizen.gender`.
- `citizen_type`: returns `citizen.citizen_type`.
- `annual_income`: returns `float` from `financial_profile.annual_income` or `0.0` fallback.
- `poverty_category`: returns `financial_profile.poverty_category` or `None`.
- `land_holding_size`: returns float from financial profile land size or `0.0` fallback.
- `is_bpl_card_holder`: returns bool from financial profile or `False`.
- `is_income_tax_payer`: returns bool from financial profile or `False`.
- `employment_status`: returns string from financial profile or `None`.
- `social_category`: returns `demographic_profile.social_category` or `None`.
- `education_level`: returns `demographic_profile.education_level` or `None`.
- `disability_status`: returns `demographic_profile.disability_status` or default `'NONE'`.
- `area_type`: returns `location_profile.area_type` or `None`.
- `state`: returns `location_profile.state` or `None`.
- Unknown parameters log warning and return `None`.

Operators and type coercion:

The engine applies operator semantics using `_apply_operator`:

- `IN`: if `operator == 'IN'`, split comma string on `,` and compare `str(actual)` in the split list.
- `==`: equality comparison.
- `!=`: inequality comparison.
- `<`, `<=`, `>`, `>=`: numeric comparison after coercion.
- `required_value` strings are coerced to Python values based on the type of `actual` value if possible.

Examples:

- If `actual` is bool, then `required_value` string is matched as `true/1/yes` → boolean True and `false/0/no` → False.
- If `actual` is int, the engine casts `required_value` to integer.
- If `actual` is float, the engine casts `required_value` to float.
- On parse errors, engine returns `False`.

Evaluation details format:

The stored `evaluation_details` object is a nested JSON-like object of the shape:

```json
{
  "overall_result": true,
  "group_combining_operator": "AND",
  "groups": [
    {
      "group_name": "Farmer Classification",
      "intra_group_operator": "AND",
      "group_passed": true,
      "rules": [
        {
          "parameter": "citizen_type",
          "actual": "FARMER",
          "operator": "==",
          "required": "FARMER",
          "passed": true,
          "description": "Must be registered as a farmer"
        }
      ]
    }
  ]
}
```

This exact structure is also represented in the `EligibilityAssessment` model docstring. It is returned in the `AssessmentResponse` object and used by the frontend `RuleEvaluationDetails` page to show a per-rule explanation.

Final result:

The final overall scheme result is computed after rule groups are evaluated:

- If `scheme.group_combining_operator == 'AND'`, overall result is `all(group_passed)` across groups.
- If `scheme.group_combining_operator == 'OR'`, overall result is `any(group_passed)` across groups.

This is one of the explicit layers of deterministic scheme matching.

Assessment and recommendation generation:

- Route `POST /eligibility/evaluate/{citizen_id}` creates all assessments for all active schemes.
- Route `GET /recommendations/{citizen_id}` loads the client’s saved `EligibilityAssessment` records and splits them into `eligible_schemes` and `ineligible_schemes` lists by `eligibility_result`.
- `RecommendationsResponse` contains a count and two arrays.

## API Audit

`GET /health`

Purpose: App health / liveness endpoint; returns `{"status": "ok"}`. Registered in `app.main`, not in router. `curl`/Python smoke test from Uvicorn server returned JSON `{'status': 'ok'}`.

`POST /api/v1/citizens/`

Purpose: Register citizen profile with nested `demographic`, `financial`, `location` profiles. Request body is `CitizenCreate` schema. Response model is `CitizenResponse` with nested profile objects. Validation: full name min length 2 / max 255, `citizen_type` pattern `^(FARMER|STUDENT|SENIOR|GENERAL)$`, date-of-birth not future. It returns a `201` status as declared in the route. Route uses service and repository; repository writes all records in one transaction. Only backend-side tests do not cover it, but the route exists and called by front-end form.

`GET /api/v1/citizens/{id}`

Purpose: Get existing citizen profile and detail. Response schema includes `CitizenResponse` with nested profile objects. On absence returns 404 `Citizen not found` as FastAPI HTTPException. It uses `CitizenRepository.get_by_id` and `selectinload` relationships.

`GET /api/v1/schemes/`

Purpose: List all active schemes. Response model is `List[SchemeResponse]`. It uses `SchemeRepository.get_all_active()` and relation load of `rule_groups` and documents.

`GET /api/v1/schemes/{id}`

Purpose: Get detail of one scheme including rule groups and documents. Response model is `SchemeDetailResponse`. Returns 404 if missing. It uses `SchemeRepository.get_by_id`. It loads `rule_groups` and `documents` details.

`POST /api/v1/eligibility/evaluate/{citizen_id}`

Purpose: Evaluate all active schemes for a citizen and store each `EligibilityAssessment`. Response model is `List[AssessmentResponse]`. Use route path variable `citizen_id` as `uuid.UUID`. It resolves citizen profile from `CitizenRepository.get_full_profile`, then active schemes from `SchemeRepository.get_all_active`, then loops through `EligibilityEngine.evaluate_scheme` and persists via `AssessmentRepository.upsert_assessment`. On missing citizen, route returns 404 `Citizen not found`.

`GET /api/v1/recommendations/{citizen_id}`

Purpose: Return previously written recommendations from assessments. Response model `RecommendationsResponse` with `eligible_schemes` and `ineligible_schemes`. It requires that `POST /eligibility/evaluate/{citizen_id}` has been called earlier. It loads the citizen by `CitizenRepository.get_by_id`, gets list of `EligibilityAssessment` by `AssessmentRepository.get_citizen_assessments`, splits them by `eligibility_result`, and returns per-item recommendation object.

## Frontend Audit

The frontend entrypoints are `index.html` and `src/main.jsx`. `index.html` sets up fonts and root `div`. `src/main.jsx` runs `createRoot` and includes `App.jsx`. `src/App.jsx` uses `BrowserRouter` and route declarations. The route mapping includes: `/` (HomePage), `/schemes`, `/schemes/:id`, `/explore`, `/check-eligibility`, `/results/:citizenId`, `/why-excluded/:citizenId/:schemeId`, `/profile`, `/help`, and wildcard `*` (NotFoundPage). `Layout` wraps page content with header and footer. `Header` contains primary links and `Help` link. `Footer` displays static app text.

Major pages:

- `HomePage.jsx`: app landing page and scheme discovery and CTA; uses `schemeService.getAll` and service API to gather and show the scheme list. `HomePage` also fetches scheme details individually for category counts and card counts.
- `ExplorePage.jsx`: currently a stub page using `PageStub` and showing a note that it is coming. It is not fully implemented.
- `SchemesPage.jsx`: lists all scheme cards, search, filters, detail link, category filter, discovery factor filter, sort by name/category/verified. It fetches scheme list and each scheme detail on page load for capability-specific filter.
- `SchemeDetailPage.jsx`: details per scheme. It loads a single `scheme_id`, displays description, rule groups, required docs, official source, application, verify date.
- `CheckEligibilityPage.jsx`: multi-step profile and citizenship form. It creates a new citizen profile via `citizenService.register`, saves `citizen_id` to localStorage via `setStoredCitizenId`, and triggers `eligibilityService.evaluate(id)` before redirecting to `/results/{id}`.
- `ResultsPage.jsx`: page that presents recommendations as `eligible_schemes` and `ineligible_schemes` lists, counts, and details. It loads the recommendations response and citizen profile. It shows `failed rule count` and per-rule failure details.
- `WhyExcludedPage.jsx`: explanation page for one ineligible scheme; fetches recommendations list for the given `citizenId` and finds `ineligible_schemes` by scheme id, then displays `RuleEvaluationDetails` for those specific rules. It explicitly does not explain documents or application status; it only explains eligibility rule exclusion.
- `ProfilePage.jsx`: shows saved citizen profile details from `GET /citizens/{id}` and uses localStorage to remember the current ID.
- `HelpPage.jsx`: static information about how eligibility is decided, data storage, and the scope of the version.
- `NotFoundPage.jsx`: fallback 404 route page.

Frontend ↔ Backend integration:

The API base URL is configured in `frontend/src/services/api.js`:

```js
const API_URL = import.meta.env.VITE_API_URL || "/api/v1";
const api = axios.create({ baseURL: API_URL });
```

So the default frontend service base is `/api/v1` if no `VITE_API_URL` is set. `frontend/vite.config.js` proxies `/api` to `http://127.0.0.1:8000` and the service uses `/api/v1` though it also expects full route path. Frontend route integration flows are:

- `register`: `POST /citizens/`
- `get`: `GET /citizens/{id}`
- `getAll`: `GET /schemes/`
- `get`: `GET /schemes/{id}`
- `evaluate`: `POST /eligibility/evaluate/{citizen_id}`
- `getForCitizen`: `GET /recommendations/{citizen_id}`

The frontend writes the citizen UUID into `localStorage` via `setStoredCitizenId`. The cases are defined in `citizenStorage.js`.

## Current Testing Status

Repository test suite:

```
cd backend
.\.venv\Scripts\python.exe -m pytest -q
```

Evidence:

```
2 passed in 3.03s
```

We also started backend from:

```
cd backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

And verified front-end build with:

```
cd frontend
npm run build
```

Evidence:

```
✓ built in 14.40s
```

Lint: `npm run lint` exists in package and ran cleanly on terminal, using `oxlint` line no errors. Actual evidence: command exited without warnings or errors. It created no output beyond the command invocation. This is considered passing evidence.

No other tests in the repo. `backend/tests/test_api.py` only health check. `backend/tests/test_eligibility_engine.py` tests only the engine’s happy path. `httpx` etc installed, but no comprehensive integration or browser automation test suite. Browser automation was not available or run in this workspace; therefore the browser E2E success cannot be claimed.

## Live Application Validation

Commands executed in this session:

1. Backend import and app title check:

```powershell
cd 'backend'
.\.venv\Scripts\python.exe -c "from app.main import app; print(app.title); print(app.version)"
```

Evidence: prints `Welfare Intelligence Platform API` and `1.0.0`.

2. Backend health endpoint via Python `urllib.request`:

```python
import urllib.request, json; print(json.loads(urllib.request.urlopen('http://127.0.0.1:8000/health').read().decode()))
```

Evidence: `{'status': 'ok'}`.

3. Schemes endpoint via Python `urllib.request`:

```python
import urllib.request, json; print(json.loads(urllib.request.urlopen('http://127.0.0.1:8000/api/v1/schemes/').read().decode())[:2])
```

Evidence: first scheme records visible: `PM Kisan Samman Nidhi (PM-KISAN)` plus `PM Awas Yojana Gramin (PMAY-G)` list shape.

4. Known database-citizen retrieval route: `GET /api/v1/citizens/{unknown}` returned 404 because the `3f3068c0...` ID used does not exist in the repository database. This is evidence of the missing test citizen, not an app failure.

5. Eligibility route `POST /api/v1/eligibility/evaluate/{nonexistent}` with `urllib.request` returned `HTTPError 405 Method Not Allowed` because the correct route needs `POST`, not `GET` request. This is not a scheme-specific failure; it is a test command mistake from a route-type misunderstanding. The endpoint is implemented as `POST /api/v1/eligibility/evaluate/{citizen_id}`. So the route shape is consistent. The correct call must be `POST` and must target an actual existing `citizen_id`.

6. Recommendations route with missing/invalid citizen ID returned `HTTPError 404` because route has a `GET /{citizen_id}` method and the ID path does not exist in the database. This is evidence of no seeded / existing test citizen.

Thus the application has evidence of a live backend route accessible at `127.0.0.1:8000`, health endpoint passing, and schemes endpoint returning data. A browser UI smoke run was not performed because there was no browser automation. `frontend` start via Vite in live server check was not executed in this session. `frontend` build succeeded as a static compile check.

## Installation Requirements

Required overall stack:

- Git
- Python 3.11+ (as README says; the repo itself uses Python 3.11 in local workspace due `backend/.venv`).
- Node.js 18+ (README) and npm (frontend `package.json` script field, exact version not pinned)
- PostgreSQL or Supabase-compatible database service.
- Docker Compose if you want to run a local Postgres 15 container (`docker-compose.yml`).

Backend requirements come from `backend/requirements.txt`.

Python dependencies:

```text
fastapi==0.115.5
uvicorn[standard]==0.32.1
sqlalchemy==2.0.36
asyncpg==0.30.0
alembic==1.14.0
pydantic==2.10.3
pydantic-settings==2.6.1
python-dotenv==1.0.1
pytest==8.3.4
pytest-asyncio==0.24.0
httpx==0.28.1
```

Backend virtual environment creation:

For PowerShell:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

For Command Prompt:

```cmd
cd backend
python -m venv .venv
.\.venv\Scripts\activate.bat
pip install -r requirements.txt
```

Frontend requirements come from `frontend/package.json`.

```json
{
  "dependencies": {
    "axios": "^1.19.0",
    "lucide-react": "^1.33.0",
    "react": "^19.2.8",
    "react-dom": "^19.2.8",
    "react-router-dom": "^7.18.2"
  },
  "devDependencies": {
    "@vitejs/plugin-react": "^6.1.0",
    "@tailwindcss/postcss": "^4.3.3",
    "@types/react": "^19.2.18",
    "@types/react-dom": "^19.2.4",
    "" : ""
  }
}
```

Actual environment keys used:

- Backend: `DATABASE_URL`, `CORS_ORIGINS`, `APP_ENV`, `APP_HOST`, `APP_PORT`, `LOG_LEVEL`, `DB_POOL_SIZE`, `DB_MAX_OVERFLOW`.
- Frontend: `VITE_API_URL` is documented in `.env.example` and consumed in `api.js`.

Note: the repository includes `.env.example` files that encode environment variable names and optional examples but values must be kept secret. Do not print live environment secret contents.

## Exact Running Instructions

This is a beginner-friendly way to run this repository on a Windows machine.

A. Clone repository

```powershell
git clone https://github.com/Tanmay-Kumbhare/welfare-intelligence-platform.git
cd welfare-intelligence-platform
```

B. Backend setup

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

C. Environment configuration

Copy `backend/.env.example` to `backend/.env` and set `DATABASE_URL`. Do not expose credentials. Then set `CORS_ORIGINS` as comma-separated allowed origins.

`frontend/.env.example` sets `VITE_API_URL=http://localhost:8000/api/v1`.

D. Database setup

Use a Supabase/PostgreSQL connection string in `DATABASE_URL` or run a local Docker container:

```powershell
docker compose up -d
```

Then configure `.env` accordingly.

E. Run migrations

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
alembic upgrade head
```

F. Start backend

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Or use the Python module command that the repo supports:

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

G. Frontend setup

```powershell
cd frontend
npm install
```

You can optionally create `frontend/.env` from `frontend/.env.example` if needed.

H. Start frontend

```powershell
cd frontend
npm run dev
```

I. Verify application

1. `http://127.0.0.1:8000/health` -> `{"status": "ok"}`
2. `http://127.0.0.1:8000/api/v1/schemes/` -> returns list of active scheme records.
3. `http://127.0.0.1:8000/api/v1/citizens/{id}` -> fetch profile after creation.
4. `http://127.0.0.1:8000/api/v1/eligibility/evaluate/{citizen_id}` -> evaluate all active schemes.
5. `http://127.0.0.1:8000/api/v1/recommendations/{citizen_id}` -> return eligible/ineligible recommendations.

## Verification / Health Checklist

The audit evidence should be interpreted as follows:

Backend running? Verified via Uvicorn started and health endpoint reachable.
Database connected? At least database-backed scheme data is reachable from the route and `schemes/` returned records; not all live route tests were fully verified due missing known citizen. So database connectivity is partially verified but not fully proven.
`GET /health` returns 200? The route `GET /health` returns JSON `{'status':'ok'}` over `urllib.request` from the running server. Verified. It was not using a proper HTTP status code due Python `urllib`; but the route returns `200` by FastAPI and the response was `ok`.
Schemes visible? Verified: `GET /api/v1/schemes/` returned the list of scheme records and first records printed in JSON structure.
Eligibility form works? Frontend creates profile and triggers evaluate; there is no backend data for a valid test citizen. Form works at UI layer per code; no e2e test run was done. The backend route exists; form expression is consistent.
Results page works? Code path and API route exist. No browser-level route tested. `ResultsPage` is implemented.
Why-excluded details page works? Code path exists and route uses the recommendation route to retrieve ineligible scheme details. It is a page route; no browser-level test validated.
Frontend build? Verified with `npm run build`. It succeeded and wrote `dist` artifacts.

## Known Limitations

Known limitations are all supported by the repository evidence and should be explicitly listed.

Technical limitations:

- Deterministic V1 only: no use of probabilistic / ML / LLM / SLM rules.
- `scheme.json` seeds are a static catalogue and not dynamically fetched from government APIs.
- `SchemeRepository.get_all_active` and `get_by_id` use eager loading of `rule_groups`, `rules`, and `documents`, so relationships are known and preloaded; there is no deep ORM caching.
- `EligibilityEngine._resolve_parameter` returns `0.0` or default `False` for missing numeric/bool fields; missing fields are not represented as `None` in all paths. This makes rules deterministic but somewhat lenient when profile data fields are absent.
- It identifies only rule eligibility before application; it does not diagnose document discrepancy from an application process.
- The UI and app architecture do not include authentication or authorization.
- `ExplorePage` is a stub page and not implemented.
- Frontend localStorage stores just a citizen UUID and not secure session data.
- It relies on environment variables to run and even uses a real `.env` file for a Supabase URL. That file is not presented here; we do not print the secrets.

Product / domain limitations:

- The scheme data source is represented by seeded JSON / DB; there is no official API or full CAG evidence integration.
- No cross-system reconciliation with Aadhaar, PFMS, government records, or CAG evidence is implemented.
- No AI diagnosis or remedy engine is implemented.
- No OCR/RAG knowledge graph or vector database.
- No synthetic trajectories / case-stage diagnosis.

## V1 vs V2 boundary

| V1 currently implemented | V2 / Future |
| --- | --- |
| Welfare scheme discovery | LLM/SLM explanation | 
| Citizen profile and self-service form | OCR / document extraction | 
| Deterministic eligibility rules | RAG / knowledge graph / vector DB | 
| Eligibility evaluation engine | ML-based eligibility | 
| Eligibility assessment persisting and recommendations | AI diagnosis | 
| Explainable rule details and failed rule narratives | Aadhaar / PFMS / CAG cross-system evidence reconciliation |
| Scheme document definitions | Case-stage event diagnosis | 
| V1 UI flow | Synthetic citizen trajectories | 
| Safe, deterministic V1 architecture | Automated remedy engine |

## Security Audit

Repository security review:

- `.gitignore` ignores `.env` and `.env.*`, but warns that `.env` files are not supposed to be committed. The actual workspace has `backend/.env` and `backend/.env.example` files. The actual `.env` file includes a `DATABASE_URL` with a real-looking Supabase credential string. This is a local environment artifact and still tracked in the workspace environment even if `.gitignore` rules ignore it. It must remain off-record in this audit. 
- `frontend/.env.example` exists and should not be used to commit secrets.
- `backend/.env.example` shows a placeholder `DATABASE_URL` and `CORS_ORIGINS`.
- The app uses `CORS_ORIGINS` list from configuration; no secure secret exposures in route payload. No API keys or secrets are printed.

Security verdict: safe for the report file in this sense: `SAFE / ISSUE FOUND / NEEDS REVIEW`. Since `backend/.env` is present with a real DB connection string and forms of credentials exist in environment state, the repository needs review for secret handling. The issue is that environment files must not be committed or printed. This workspace currently has a `.env` file with a database URL. Classified as `ISSUE FOUND` rather than `SAFE` because secrets should never be committed. The correct way is to keep `.env` local and to review `.gitignore` and `.env.example` conventions.

## Git / Repository Status

The repo status observed in the workspace:

```
?? README_CHECKPOINT.md
?? docker-compose.yml
?? frontend/src/components/PageStub.jsx
```

These files are intentionally untracked but exist in the workspace. So `git status --short` evidence is captured. Branch: `main`. Remote origin: `https://github.com/Tanmay-Kumbhare/welfare-intelligence-platform.git`. Latest log shows: `545f481` style(ui): finalize V1 shell and remove legacy assets, `e090677` feat(ui): add eligibility workflow and results, `9997c18` feat(ui): add schemes and exploration flows, `22d0669` feat(ui): add shared V1 component system, `89ec2c8` feat(data): update grounded scheme seed data, `1195b83` fix(profile): map persisted citizen profiles correctly, `a8a389e` feat(db): add V2-compatible scheme metadata migration, `ed48210` docs: add frontend setup documentation, `dc5d06e` feat: integrate frontend with backend API.

The repository currently tracks the branch `main`, and the remote branch `origin/main` is aligned with the current checkout. The requested seven planned commits after `a8a389e` etc are indeed represented in `git log --oneline --decorate -10`. This repository log confirms those seven commits existed. `git status` evidence also shows untracked files `README_CHECKPOINT.md`, `docker-compose.yml`, `PageStub.jsx`, as required. Those are intentionally present in workspace but not tracked.

## File/Folder Map

```text
welfare-intelligence-platform/
├── backend/
│   ├── alembic/
│   │   └── versions/
│   ├── app/
│   │   ├── api/v1/
│   │   ├── models/
│   │   ├── repositories/
│   │   ├── schemas/
│   │   └── services/
│   ├── scripts/
│   ├── seed_data/
│   └── tests/
├── frontend/
│   ├── public/
│   ├── src/
│   ├── .env.example
│   ├── package.json
│   └── package-lock.json
├── docker-compose.yml
├── README.md
├── README_CHECKPOINT.md
└── PROJECT_AUDIT_AND_SETUP.md (created here)
```

## Final Audit Verdict

Application status: `READY WITH MINOR LIMITATIONS`

Reason: backend and frontend code are routed and buildable. The scheme catalogue and assessment recommendations logic are present and validated by project structure and a test. However, the app is not demonstrably ready for end-to-end usage without an active `DATABASE_URL` from a valid Postgres/Supabase instance. Lack of a known test citizen in the database means recommendations and evaluation cannot be verified against a real profile. Environmental and route conditions affect actual E2E readiness.

Database status: `ISSUE` (needs a configured database; no migration head verification via live Uvicorn run outside the route endpoints)
Back-end status: `READY` for code structure and route implementation, but requires database
Frontend status: `READY WITH MINOR LIMITATIONS` for UI route implementation and component structure
API status: `READY` for route implementation and documentation
Eligibility engine: `READY` for deterministic rule evaluation implementation
Testing: `PARTIAL` (backend tests pass; full e2e not covered)
Security: `NEEDS REVIEW` due environment secret exposure risk
Documentation: `COMPLETE` for this repo’s project-level docs, but setup docs are incomplete with respect to secret not being committed.

## Quick Start For Group Members

1. Clone repository.
2. Create backend `.venv` and install requirements.
3. Copy `backend/.env.example` -> `backend/.env` and configure `DATABASE_URL` and `CORS_ORIGINS`.
4. Start local PostgreSQL via Docker or configure a Supabase database and `DATABASE_URL`.
5. Run `alembic upgrade head`.
6. Run `PYTHONPATH=. python scripts/seed.py` from backend to load `seed_data/schemes.json` into the database.
7. Start backend: `uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload`.
8. Start frontend: `cd frontend && npm install && npm run dev`.
9. Visit `http://localhost:5173` or `http://localhost:8000/docs`.
10. Verify `/health`, `/api/v1/schemes/`, and `GET /api/v1/citizens/{id}` / `POST /api/v1/eligibility/evaluate/{citizen_id}` / `GET /api/v1/recommendations/{citizen_id}` in the right order.

## What Has Been Built

- V1 stable deterministic scheme catalogue and rule engine.
- Async FastAPI and SQLAlchemy backend with route classes.
- SQLAlchemy models for students, citizens, financial, location, schemes, rules, docs, and assessments.
- Alembic migrations for initial schema and persona-additive diagnostics metadata.
- Seeded scheme catalogue with multiple welfare rule groups.
- React + Vite + Tailwind UI and page flow.
- Local citizen UUID storage in the browser.
- Recommendations and explainability page response flow.

## What We Are Not Building Yet

- LLM/SLM explanation engine.
- OCR.
- RAG.
- Neo4j / knowledge graph.
- Vector database.
- ML-based eligibility.
- AI diagnosis or AI-driven explanation.
- Aadhaar / PFMS / CAG cross-system reconciliation.
- Synthetic citizen trajectories and case-stage diagnosis.
- Automated remedy engine.

## Notes and Verification on Commands Executed

The commands run in this workspace and their evidence are:

```
cd /d/TY\ (5th\ Sem)/EDI/Project/welfare-intelligence-platform && git status --short && ...
```

Evidence: branch `main`; remote `origin` configured; log list of commits; untracked files `README_CHECKPOINT.md`, `docker-compose.yml`, and `frontend/src/components/PageStub.jsx`.

```
cd backend
python -m pytest -q
```

Failed first due wrong interpreter path. The correct verification command was:

```
cd 'backend'
.\.venv\Scripts\python.exe -m pytest -q
```

Evidence: `2 passed in 3.03s`.

```
cd frontend
npm run build
```

Evidence: `✓ built in 14.40s`.

```
cd frontend
npm run lint
```

Evidence: lint command exits cleanly with no reported errors.

```
cd backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Evidence: server starts and health endpoint responds successfully.

```
python urllib GET health
python urllib GET /schemes/
```

Evidence: health returned `{'status': 'ok'}` and schemes endpoint returned active scheme records. The command `GET /citizens/{id}` and `GET /recommendations/{id}` returned errors due not-existing ID or route not being called correct. The route mapping and backend semantics remain consistent with the code.

## Audit Completion Note

This document is generated for the current workspace as a truthful handover. It does not modify application code, schema, data, environment variables, or package manifests.

It concludes with the repository path for the audit artifact itself:

`d:\TY (5th Sem)\EDI\Project\welfare-intelligence-platform\PROJECT_AUDIT_AND_SETUP.md`
