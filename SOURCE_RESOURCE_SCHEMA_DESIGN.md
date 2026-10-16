# Source → Resource → Snapshot Design (Phase 3B, Task 1D)

> **Status:** Design/review only. **No migration authored, no DB change, no application-code change.**
> Prepared 2026-10-03 against the **live database** (introspected directly, not documentation-derived) and the current code.
> Feeds: migration `0008` (to be reviewed separately). Evidence base: `MAHARASHTRA_SOURCE_REGISTRY.md` (Task 1C inventory), `SOURCE_SEEDING_AUDIT_NOTE.md` (Tasks 1A/1B).

---

## 1. Current Schema Inventory (source of truth: live DB introspection)

Tables actually present (matching `tbl_scheme%`):

```
tbl_scheme_master, tbl_scheme_rule_group, tbl_scheme_eligibility_rule,
tbl_scheme_document_master, tbl_scheme_ingestion_run,
tbl_scheme_source, tbl_scheme_source_document, tbl_scheme_source_content,
tbl_scheme_rule_provenance
```

**`tbl_scheme_source_resource` does NOT exist in the live database.** Any doc suggesting it exists is stale.

### `tbl_scheme_source` (6 rows live: SRC-01..04 + PM-KISAN + test artifact)

| column | type | nullable | default | notes |
|---|---|---|---|---|
| source_id | uuid | NO | gen_random_uuid() | PK |
| source_name | varchar | NO | — | UNIQUE (`uq_scheme_source_name`) |
| source_type | varchar(50) | NO | — | CHECK: GOVERNMENT_API / GOVERNMENT_WEBSITE / GOVERNMENT_PORTAL / GOVERNMENT_PDF / OTHER_AUTHORIZED_SOURCE |
| base_url | varchar(500) | YES | — | |
| authority_name | varchar(255) | YES | — | |
| status | varchar(20) | YES | 'ACTIVE' | ACTIVE/INACTIVE/RETIRED |
| created_at / updated_at | timestamptz | NO | now() | |

### `tbl_scheme_source_document` — today this is the de-facto **snapshot** entity

| column | type | nullable | notes |
|---|---|---|---|
| source_document_id | uuid | NO | PK |
| scheme_id | uuid | YES | FK `tbl_scheme_master` ON DELETE SET NULL |
| source_id | uuid | NO | FK `tbl_scheme_source` ON DELETE CASCADE |
| document_name | varchar | NO | derived from URL by `ingestion_service.py` |
| document_url | varchar | NO | the fetched URL |
| document_type | varchar | YES | |
| language | varchar | YES | default 'en' |
| **version** | int | NO | default 1; UNIQUE `(source_id, document_name, version)` |
| retrieved_at | timestamptz | YES | fetch timestamp |
| published_at | date | YES | |
| content_hash | varchar | YES | SHA-256 of body |
| processing_status | varchar | YES | PENDING/PROCESSING/PROCESSED/FAILED |
| created_at / updated_at | timestamptz | NO | |

### `tbl_scheme_source_content` — content variants of a snapshot

`content_id` PK; `source_document_id` FK CASCADE; `content_type` (RAW/NORMALIZED/EXTRACTED_TEXT); `raw_content`/`normalized_content` text; `language` (default 'en'); `processing_status`; `extraction_version`; `retrieved_at`. UNIQUE `(source_document_id, content_type, language)`.

### `tbl_scheme_ingestion_run` — run header only

`ingestion_run_id` PK; `source_id` FK CASCADE; `started_at`, `completed_at`, `status` (RUNNING/COMPLETED/FAILED/CANCELLED); `records_discovered/created/updated/failed`; `error_summary`; `created_at`. **No per-resource/per-URL item tracking.**

### Related code contracts (verified)

- `POST /api/v1/admin/sources` (`SourceCreate`): `source_name`, `source_type`, `base_url`, `authority_name`, `status`. `GET /sources` returns `SourceOut` + `document_count`, `last_run_status`, `last_run_at`. PATCH supported on the five mutable fields.
- `POST /admin/sources/{id}/fetch` → `run_manual_fetch()` (plain HTTP GET, 20 s timeout, 5 MB cap, UA "welfare scheme provenance snapshots", creates document(version N+1 by name) + RAW content + run rows). Stops at the raw layer by hard invariant.
- `SchemeSource` model in `backend/app/models/scheme_source.py`; DDL originates in migration `0003`.
- Tests: `backend/tests/test_phase1_foundation.py` (source CRUD + snapshot + provenance; 13 passed on 2026-10-03).

---

## 2. Existing Contracts That Must Keep Working

| Contract | Guarantee required |
|---|---|
| `POST/GET/PATCH /api/v1/admin/sources` | Same payloads, same response fields, 4 seeded sources untouched |
| `POST /admin/sources/{id}/fetch` + run inspection | Same behavior; old runs/documents remain queryable |
| Public `GET /api/v1/schemes/`, `/schemes/{id}` | Unchanged (this task adds nothing to them) |
| Eligibility engine & assessments | Untouched |
| Frontend (AdminSourcesPage etc.) | Zero changes required |
| Existing FK semantics | `tbl_scheme_source_document.source_id` CASCADE stays |

---

## 3. Proposed Architecture (additive)

```
SOURCE (tbl_scheme_source, extended additively)
   │ 1:N
   ├── RESOURCE (NEW tbl_scheme_source_resource)
   │        │ 1:N
   │        └── RAW SNAPSHOT  =  tbl_scheme_source_document (+ new metadata cols)
   │                                │ 1:N
   │                                └── tbl_scheme_source_content   (unchanged)
   │
   └── INGESTION RUN (tbl_scheme_ingestion_run, unchanged)
            │ 1:N
            └── INGESTION ITEM (NEW tbl_scheme_ingestion_item)
                    links run ↔ resource ↔ resulting snapshot
```

**Key reuse decision:** the existing `tbl_scheme_source_document` already *is* the immutable raw snapshot (versioned, hash-stamped, never overwritten — a refetch inserts a new version row). It is **not** a stable resource: its identity key `(source_id, document_name, version)` changes per fetch and `document_name` is URL-derived. Therefore:

- **Resource** = new table (stable logical identity: URL + type + status, one row per discoverable endpoint).
- **Snapshot** = existing document table, extended with fetch-metadata columns, plus a new nullable `resource_id` FK. Old rows keep `resource_id = NULL` and remain fully valid.

This satisfies "if an existing table already contains the required concept, reuse it": the snapshot concept is reused; only the missing stable-resource concept is added.

---

## 4. Proposed Source design (additive columns on `tbl_scheme_source`)

Only 4 new columns are proposed. Each is **nullable** → no backfill, no default-rollout risk, no break.

| field | exists? | why needed | placement | nullable | break risk |
|---|---|---|---|---|---|
| `canonical_base_url` | No (base_url may hold a deep GR-portal path, e.g. SRC-02) | 1C proved base_url ≠ canonical origin (SRC-02's base_url is a path; tribal had 3 domain variants) | Source | YES | None — not read by any existing code |
| `precedence_rank` (int) | No | Registry conflict-resolution: department GR > department site > e-Gazette > portal > aggregator | Source | YES | None |
| `fetch_policy` (varchar, e.g. 'ANONYMOUS_GET', 'SESSION_TOKEN_URL') | No | Evidence: MahaDBT tokenized deep URLs expire; e-Gazette is WebForms; everything else anonymous GET | Source | YES | None |
| `org_type` (varchar, e.g. DEPARTMENT / COMMISSIONERATE / BOARD / CORPORATION / MISSION / PORTAL) | No | Task 1C's core finding: Department ≠ Commissionerate ≠ Corporation (8+ confirmed instances); needed to prevent future merges | Source | YES | None |

**Explicitly rejected for now (with reasons):**
- `language` — per-URL reality is bilingual; belongs on Resource (which already has `language` via documents) not Source.
- `jurisdiction` — every current source is Maharashtra state-level; YAGNI until a district/national origin is registered.
- `parent_authority` — derivable from `authority_name` today; adding an FK hierarchy is a bigger design step than Task 1C evidence requires.
- `authority_level` — collapsed into `precedence_rank` (one ordering field instead of two competing ones).
- `active/inactive` — already exists (`status`).

## 5. Proposed Resource design (NEW `tbl_scheme_source_resource`)

| column | type | nullable | rationale |
|---|---|---|---|
| resource_id | uuid PK | NO | |
| source_id | uuid FK → tbl_scheme_source ON DELETE CASCADE, indexed | NO | Parent origin |
| resource_name | varchar(500) | NO | Human label |
| resource_url | varchar(1000) | NO | The stable discoverable URL |
| resource_type | varchar(50) | NO | CHECK: CATALOGUE_PAGE / SCHEME_PAGE / PDF / APPLICATION_PORTAL / API_ENDPOINT / DOCUMENT_ARCHIVE / OTHER |
| language | varchar(20) | YES | default 'en' to match document table convention |
| status | varchar(20) | YES default 'ACTIVE' | ACTIVE/INACTIVE/RETIRED |
| fetch_method | varchar(50) | YES default 'HTTP_GET' | Future: PDF_GET, API_GET |
| is_application_portal | boolean | YES default false | Task 1C classification made queryable |
| discovered_at / last_checked_at | timestamptz | YES | Inventory hygiene |
| notes | text | YES | e.g. redirect observations (sas.mahait.org → mahadbt2) |
| UNIQUE `(source_id, resource_url)` | | | Prevents duplicate resources; URL is the natural key of a logical endpoint |

Rejected: `content_type` (belongs on snapshots — varies per fetch), `document_type` (already on snapshots), `canonical_url` (the resource URL *is* canonical by definition; redirect final URLs belong on snapshots), separate application-portal table (a boolean + type covers the 1C evidence).

## 6. Proposed Raw Snapshot design (additive columns on `tbl_scheme_source_document`)

The immutability rule is already satisfied: **snapshots are never updated — a new fetch inserts a new `version` row.** Add only the fetch-evidence columns Task 1A/1B proved necessary:

| new column | type | nullable | rationale |
|---|---|---|---|
| `resource_id` | uuid FK → tbl_scheme_source_resource ON DELETE SET NULL, indexed | YES | Links snapshot to stable resource; NULL preserves all 10+ existing documents |
| `http_status` | int | YES | 1A/1B recorded status per fetch; currently nowhere |
| `final_url` | varchar(1000) | YES | Redirect evidence (sas.mahait.org → mahadbt2; mhada → /mr) |
| `content_type` | varchar(200) | YES | Observed response content type |
| `content_length` | bigint | YES | Observed size |
| `error_detail` | text | YES | Failure evidence (today `error_summary` lives only on the run) |

**Existing-column changes: NONE.** `document_name`, `version`, the UNIQUE constraint, and the URL-collision caveat noted in the original audit remain as-is; the new `resource_id` gives a cleaner long-term identity path without touching the constraint in this migration.

## 7. Proposed Ingestion Item design (NEW `tbl_scheme_ingestion_item`)

Per-resource attempt tracking within a run (today a run only has aggregate counters):

| column | type | nullable |
|---|---|---|
| item_id | uuid PK | NO |
| ingestion_run_id | FK → tbl_scheme_ingestion_run ON DELETE CASCADE, indexed | NO |
| resource_id | FK → tbl_scheme_source_resource ON DELETE SET NULL | YES |
| source_document_id | FK → tbl_scheme_source_document ON DELETE SET NULL | YES |
| status | varchar(20) default 'PENDING' (PENDING/RUNNING/SUCCEEDED/FAILED/SKIPPED) | YES |
| http_status / error_detail | int / text | YES |
| started_at / completed_at | timestamptz | YES |

## 8. Design tested against Task 1C findings

| Task 1C finding | Modeled as |
|---|---|
| Tribal Development Department (`tribal.maharashtra.gov.in`) | **Source** (org_type=DEPARTMENT, precedence high) |
| — department scheme catalogue page | Resource (CATALOGUE_PAGE) |
| — SWAYAM (`swayam.mahaonline.gov.in`) | Resource (APPLICATION_PORTAL, is_application_portal=true) **under the Tribal source** — never a standalone source (1B decision preserved) |
| — departmental PDFs | Resources (PDF) |
| Tribal Commissionerate (`mahatribal.gov.in` + `.mahaitgov.in` mirror) | **Second Source** (org_type=COMMISSIONERATE); the mahaitgov host recorded as an alternate host in notes — mirrors do not create sources |
| Agriculture Department | Source; department scheme pages → Resources; MahaDBT remains its own Source (application destination reached via resources' URLs) |
| Labour trio: IELMD sub-site (labour.maharashtra.gov.in) / Commissioner of Labour (mahakamgar) / MBOCWW Board (mahabocw.in) | **Three Sources** — org_type DEPARTMENT / COMMISSIONERATE / BOARD; not merged (1C instruction) |
| Housing: Dept / MHADA / Mah Housing Corp portal | Dept = Source; MHADA = Source (CORPORATION); `mahahousing.mahaonline.gov.in` = Resource (APPLICATION_PORTAL) under whichever source the freeze assigns (open question §12) |
| Legacy portal redirect (`sas.mahait.org` → `mahadbt2.maharashtra.gov.in`) | One Resource under the pension-owning source; `final_url` on snapshots captures the redirect; **no duplicate source created** |
| MJPJAY portal unreachable / mahawrd unreachable | Resource rows may hold `status='INACTIVE'` + notes; verification failures don't block registration |

## 9. Existing API compatibility analysis

- `SourceCreate` / `SourceOut` / PATCH: **remain unchanged.** All new source columns are nullable; the create endpoint can ignore them initially (admin UI can later send optional fields). Existing clients (frontend, seeded rows) are unaffected because no request field becomes required and no response field changes meaning.
- Fetch endpoint: unchanged signature; internally can begin populating `resource_id`/`http_status`/`final_url` **after** migration 0008 ships — a follow-up code change outside this task's scope.
- Public scheme APIs, eligibility, frontend: zero interaction with the new tables.

## 10. Migration 0008 proposal (NOT implemented — for review)

- **New tables:** `tbl_scheme_source_resource`; `tbl_scheme_ingestion_item`.
- **New columns (all nullable):** on `tbl_scheme_source`: `canonical_base_url` (varchar 500), `precedence_rank` (int), `fetch_policy` (varchar 50), `org_type` (varchar 50). On `tbl_scheme_source_document`: `resource_id` (uuid FK SET NULL, indexed), `http_status` (int), `final_url` (varchar 1000), `content_type` (varchar 200), `content_length` (bigint), `error_detail` (text).
- **New constraints:** CHECK on `resource_type` (7 values); UNIQUE `(source_id, resource_url)`; CHECK on item `status`.
- **Indexes:** `resource.source_id`, `resource.status`, `document.resource_id`, `item.ingestion_run_id`.
- **Data migration: NONE.** Existing 6 sources and all documents stay byte-identical (new columns NULL).
- **No changes to:** existing columns, existing constraints (incl. the `(source_id, document_name, version)` uniqueness), `source_type` values, or any other table.
- **Rollback:** both new tables `DROP TABLE`; new columns dropped in reverse order (FK/index first, then column). Fully reversible because nothing pre-existing is modified.
- **Risk flagged:** `alembic revision` numbering must follow the current head (`0007_oauth_and_linking` → `0008_...`); the earlier duplicate-`0005` incident (fixed in the working tree) shows head state must be checked before authoring.

## 11. Backward compatibility analysis (summary)

| Existing behavior | Impact |
|---|---|
| Source CRUD API payloads/responses | None — additive, nullable |
| Existing 6 source rows | None — untouched, new columns NULL |
| Existing documents/content/provenance | None — only new nullable columns |
| Existing runs | None — items table is separate |
| Eligibility, schemes, public APIs | None — no interaction |
| Frontend | None — no required changes |
| Model files | Extended additively (`scheme_source.py` gains 2 classes + optional columns); no renames/deletions |

## 12. Risks / open questions for the freeze review

1. **Who owns the Mah Housing Corp application-portal resource** — Housing Dept or MHADA? (Freeze decision needed; both modeled as Sources.)
2. **MahaDBT as platform vs source** — it is both a Source (SRC-03, registered) and a platform hosting other departments' application flows (sas→mahadbt2). Proposal: keep SRC-03 as the platform Source; other departments' deep tokenized URLs become their own Resources with `fetch_policy='SESSION_TOKEN_URL'`.
3. **`precedence_rank` values** — a concrete ordering (registry §5) should be ratified at freeze time; the column exists either way.
4. **Snapshot identity long-term** — the `(source_id, document_name, version)` uniqueness can still collide on renamed URLs; `resource_id` mitigates but does not change the constraint in 0008. A later migration may revisit; out of scope here.
5. **`org_type` value list** — seven values proposed from 1C evidence (DEPARTMENT, COMMISSIONERATE, BOARD, CORPORATION, MISSION, DIRECTORATE, PORTAL); freeze review should ratify.

---

## Task 1E — Final Compatibility Freeze Validation

> 2026-10-03. Read-only validation: live-DB introspection, Alembic state check, constraint/data audit. No DB, schema, code, API, or frontend changes; no migration created.

### 1. Resource identity decision

**A Resource is uniquely identified by `(source_id, resource_url_normalized)`.**

Normalization rules applied to `resource_url` before uniqueness comparison (documented, deterministic):
1. lowercase scheme and host
2. drop default port (`:80`/`:443`)
3. drop fragment (`#...`)
4. collapse empty path: `https://host` ≡ `https://host/`
5. strip trailing slash on the last non-empty path segment (`/schemes/` ≡ `/schemes`)
6. keep query string **except** recognized session/tracking parameters (MahaDBT `str=`, ASP.NET session ids) — a tokenized deep URL and its token-less form are the same Resource

Tested against the required examples:

| case | decision |
|---|---|
| `…/schemes` vs `…/schemes/` | **One Resource** (rules 4–5) |
| `krishi…/schemes` vs `mahadbt…/...` describing the same scheme | **Two Resources** — host differs; resources are per-origin |
| `sas.mahait.org` → MahaDBT destination | **One Resource**, `resource_url` = the stable requested URL; the redirect destination is recorded per-fetch in `tbl_scheme_source_document.final_url`. A changed redirect destination never creates a new Resource — only new snapshot rows |

Implementation note (for 0008 review): normalization can be enforced by a stored normalized column or by application-level convention; the design note recommends a plain `resource_url` plus UNIQUE `(source_id, resource_url)` with normalization applied by convention in the (future) CRUD layer — no DB-side normalization function is required for 0008.

### 2. `org_type` controlled vocabulary (final)

Controlled CHECK constraint, 8 values — each with a live Task 1C example:

| value | meaning | example from inventory |
|---|---|---|
| `DEPARTMENT` | Mantralaya administrative department site | Tribal Development Dept, SJSA, Agriculture |
| `COMMISSIONERATE` | Field-execution commissionerate under a department | Commissioner of Labour (mahakamgar), Tribal Commissionerate (mahatribal) |
| `DIRECTORATE` | Directorate under a department | Directorate of Industries, Directorate of Municipal Administration |
| `BOARD` | Welfare/skills board | MBOCWW (mahabocw.in), MSBSVET |
| `CORPORATION` | Government corporation/undertaking | MHADA, Mah Housing Corp, MS-OBC Finance & Dev Corp |
| `MISSION` | Time/programme-bound mission society | NHM Maharashtra, MSSDS (kaushalya) |
| `COMMISSION` | Statutory commission | Maharashtra State Minority Commission (msmc) |
| `PLATFORM` | Shared government application/DBT infrastructure | MahaDBT, MahaOnline family |

Rejected: `AUTHORITY` (MHADA's legal name contains "Authority" but functionally it is a Corporation; adding both invites misclassification) and `OTHER` (1C evidence produced no origin that fits none of the 8; if one appears later the CHECK can be extended additively).

### 3. FK delete strategy (final)

Fundamental rule honored: *deleting/deactivating a Resource must never silently destroy historical snapshots or evidence.*

| FK | parent ← child | ON DELETE | verdict & reasoning |
|---|---|---|---|
| `tbl_scheme_source.source_id` ← `tbl_scheme_source_resource` | Source ← Resource | **CASCADE** | A Resource without its Source is meaningless; mirrors the existing document.source_id CASCADE. Historical snapshots survive via their own `resource_id` SET NULL (below). Sources are retired (`status=RETIRED`), never deleted, in practice |
| `tbl_scheme_source_resource.resource_id` ← `tbl_scheme_source_document` | Resource ← Snapshot | **SET NULL** | Chosen over RESTRICT: snapshot remains fully interpretable after the link is lost because it self-describes (`source_id`, `document_url`, `final_url`, `document_name`, `version`, `content_hash`, `retrieved_at`). RESTRICT would block legitimate resource cleanup while SET NULL only drops the association, never history |
| `tbl_scheme_ingestion_run.ingestion_run_id` ← `tbl_scheme_ingestion_item` | Run ← Item | **CASCADE** | Items are constituent attempts of a run; deleting a run deletes its audit trail as a unit (mirrors existing run.source_id CASCADE) |
| `tbl_scheme_source_resource.resource_id` ← `tbl_scheme_ingestion_item` | Resource ← Item | **SET NULL** | Run history survives resource removal; `resource_url` is not copied onto items — after SET NULL the item still shows status/http/error and its snapshot link |
| `tbl_scheme_source_document.source_document_id` ← `tbl_scheme_ingestion_item` | Snapshot ← Item | **SET NULL** | Same rationale |
| existing: `document.source_id` CASCADE, `document.scheme_id` SET NULL | — | **unchanged** | Out of scope for 0008 |

⚠️ Pre-existing behavior flagged (unchanged by 0008, for awareness): deleting a **Source** CASCADEs its documents (snapshots) today. Recommendation for operations: soft-delete sources via `status=RETIRED`; physical source deletion should be considered forbidden. No schema change proposed.

### 4. Alembic history (actual state, verified 2026-10-03)

- Live DB revision: **`0007_oauth_and_linking`** (from `alembic_version` table and `alembic current`)
- Repository head: **`0007_oauth_and_linking` (head)** — **single head, no branching**
- Chain: `0001 → 0002 → 0003 → 0004_auth_user_and_ownership → 0005 → 0006 → 0007_oauth_and_linking` — linear
- No duplicate numbering remains (the old duplicate `0005_oauth…` file is deleted in the working tree and replaced by `0007_oauth_providers_and_account_linking.py`, which is exactly the live head)
- **A new `0008` can be created safely** with `down_revision = "0007_oauth_and_linking"`

### 5. Existing source compatibility (live-verified)

6 rows; PK `source_id`; UNIQUE `source_name`; CHECK `ck_scheme_source_type`; in-use types only `GOVERNMENT_WEBSITE` (3) and `GOVERNMENT_PORTAL` (3) — no `GOVERNMENT_API`/`GOVERNMENT_PDF`/`OTHER` rows exist; **no duplicate `base_url` values**. The four proposed columns are nullable → existing INSERT path (`SourceCreate` sets 5 fields), PATCH, GET/list, tests, and seeded rows are unaffected; `SourceOut` simply won't read the new columns until the API is later extended.

### 6. Existing document compatibility (live-verified)

4 rows; PK `source_document_id`; all 4 belong to one URL (`https://pmkisan.gov.in`) with **4 versions and 4 distinct `content_hash` values** — empirical proof that snapshots are immutable and versioned (content changed between fetches → new version row, old row untouched). All `processing_status='PROCESSED'`. Adding nullable `resource_id` is safe: existing rows keep NULL, remain valid/queryable/immutable; **no backfill required** (the PM-KISAN resource link can be established later by normal CRUD, not by migration).

### 7. Proposed migration impact (final shape, per column)

**New table `tbl_scheme_source_resource`** — `resource_id` uuid PK; `source_id` uuid NOT NULL FK→source CASCADE + index; `resource_name` varchar(500) NOT NULL; `resource_url` varchar(1000) NOT NULL; `resource_type` varchar(50) NOT NULL CHECK (7 values: CATALOGUE_PAGE/SCHEME_PAGE/PDF/APPLICATION_PORTAL/API_ENDPOINT/DOCUMENT_ARCHIVE/OTHER); `language` varchar(20) NULL default 'en'; `status` varchar(20) NULL default 'ACTIVE'; `fetch_method` varchar(50) NULL default 'HTTP_GET'; `is_application_portal` bool NULL default false; `discovered_at`/`last_checked_at` timestamptz NULL; `notes` text NULL; **UNIQUE `(source_id, resource_url)`** + index on `status`.

**New table `tbl_scheme_ingestion_item`** — `item_id` uuid PK; `ingestion_run_id` uuid NOT NULL FK→run CASCADE + index; `resource_id` uuid NULL FK→resource SET NULL; `source_document_id` uuid NULL FK→document SET NULL; `status` varchar(20) NULL default 'PENDING'; `http_status` int NULL; `error_detail` text NULL; `started_at`/`completed_at` timestamptz NULL.

**`tbl_scheme_source` additions (all nullable, no defaults, no indexes needed):** `canonical_base_url` varchar(500) — stable origin when base_url is a deep path; `precedence_rank` int — registry conflict ordering; `fetch_policy` varchar(50) — evidence-based fetch behavior class; `org_type` varchar(50) — controlled vocabulary §2.

**`tbl_scheme_source_document` additions:** `resource_id` uuid NULL FK→resource SET NULL + index — stable-resource link; `http_status` int NULL — fetch evidence; `final_url` varchar(1000) NULL — redirect evidence; `content_type` varchar(200) NULL — observed response type; `content_length` bigint NULL — observed size; `error_detail` text NULL — failure evidence.

No column modifications. No data migration. Fully reversible (drop FKs/indexes → drop columns → drop tables).

### 8. Existing-data constraint checks (live-audited)

| check | result |
|---|---|
| Duplicate source `base_url` | **NONE** (6 distinct) |
| Duplicate source names | NONE (UNIQUE already enforced) |
| Duplicate `canonical_base_url` (proposed) | N/A — column empty at creation; no existing data to violate |
| Duplicate document content hashes | NONE (4 rows, 4 distinct hashes) |
| `resource` UNIQUE `(source_id, resource_url)` | N/A — new empty table; cannot fail on existing data |
| Nullable assumptions | All proposed columns nullable → no existing row can violate NOT NULL |
| `source_type` collisions | None — CHECK unchanged; only 2 of 5 values in use |
| `document.resource_id` FK violations | None possible — all existing rows get NULL |
| Any constraint that would fail on existing data | **NONE found** |

### 9. Backward compatibility matrix

| Existing functionality | Migration impact | Expected result |
|---|---|---|
| Source creation (POST) | None — new columns not in request schema | Works |
| Source listing (GET) | None — SourceOut unchanged | Works |
| Source PATCH | None | Works |
| Manual fetch (POST /fetch) | None until follow-up code change populates new columns | Works |
| Scheme catalogue / detail | None | Works |
| Eligibility | None | Works |
| Existing documents (4 rows) | Nullable `resource_id` | Remain valid, immutable, queryable |
| Existing runs | Untouched table | Works |
| Provenance citations | Untouched tables | Works |
| Existing frontend | No API contract change | Works |
| Existing migrations | Append-only 0008 | Works |

### 10. Remaining risks (non-blocking)

1. **Source-level CASCADE on documents** is pre-existing; operational rule needed (soft-delete sources only) — documented in §3, no schema change.
2. **URL normalization for resource uniqueness** is convention-based; a mis-normalized insert could create a near-duplicate Resource. Acceptable: cleanup is a simple DELETE before snapshots reference it.
3. **Snapshot-identity constraint** `(source_id, document_name, version)` untouched — long-term revisit documented in Task 1D §12.4.
4. **`resource_url` length 1000** — observed government URLs are well under; longer URLs would need truncation policy at insert time (future code concern).

### Freeze decision

All validations passed: single linear Alembic head at `0007_oauth_and_linking`; zero constraint collisions in live data; every proposed change nullable/additive; all existing contracts preserved.

#### READY FOR MIGRATION 0008

(No blockers. Awaiting manual approval to author the migration.)

---

**Deliverable status (Task 1D):** design only. Database unchanged; no migration created; application behavior unchanged; no code modified (git working tree contains only the pre-existing local changes plus documentation files). Existing tests unaffected (no code touched).
