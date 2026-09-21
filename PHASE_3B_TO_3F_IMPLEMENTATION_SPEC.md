# Phase 3B–3F Implementation Specification

**Status:** design specification only  
**Input:** `PHASE_3A_SCHEME_ARCHITECTURE_AUDIT.md` and the repository audited for Phase 3A  
**Non-goal of this document:** implementation. No code, schema, migrations, seed data, or database state is changed by this specification.

## 1. Scope and decisions resolved

This specification defines the implementation target for source ingestion, candidate extraction, evidence, immutable scheme versions, publication, a typed deterministic rule DSL, tri-state eligibility, and operational scale.

The following decisions are final for Phases 3B–3F:

1. `tbl_scheme_master` remains the stable, public **scheme identity**. It no longer represents a mutable rule set after the compatibility migration.
2. A new `tbl_scheme_version` is the immutable, published-or-historical representation that owns versioned metadata, rules, documents, geography, and publication state.
3. Existing source tables are retained and extended. A source resource and an immutable retrieval snapshot are separated; raw bytes live in configured object storage and are content-addressed by SHA-256.
4. Extraction creates candidate records only. Neither an adapter nor an LLM may insert published scheme rules directly.
5. Evidence points to an immutable extraction artifact plus a stable locator and quote hash. Government-source evidence and citizen evidence remain separate domains.
6. A version becomes runtime eligible for evaluation only after publication. Published versions are immutable; corrections create a successor version.
7. Runtime eligibility has exactly three persisted/public statuses: `ELIGIBLE`, `NOT_ELIGIBLE`, and `INSUFFICIENT_INFORMATION`. `UNKNOWN` is a rule-level evaluation outcome and maps to `INSUFFICIENT_INFORMATION` at scheme level.
8. Recommendation remains downstream of eligibility and has no authority to alter any eligibility result.

## 2. Terminology and relationship map

```text
Scheme identity (existing tbl_scheme_master)
  1 -> N Scheme version (NEW)
           1 -> N published groups/rules/doc requirements/geography
           N -> 1 publishing candidate batch

Source registry (existing tbl_scheme_source)
  1 -> N source resources (NEW)
           1 -> N immutable snapshots (existing source document, modified)
                    1 -> N extraction artifacts (existing source content, modified)

Ingestion run (existing, modified)
  1 -> N ingestion items (NEW)
  1 -> N candidate batches (NEW)
           1 -> N candidate schemes -> groups/rules/document requirements/geography (NEW)
           N -> N evidence references (NEW)
           1 -> N validation findings/review decisions (NEW)
```

All table names below use the repository's `tbl_` naming convention. `UUID` means PostgreSQL UUID. All timestamps are `timestamptz`; all created/updated timestamps use database `now()` defaults. Actor IDs are nullable UUID references only where the current application has no users table; Phase 3 must not invent a foreign key to a non-existent actor table.

## 3. Existing tables to modify

### 3.1 `tbl_scheme_master` — MODIFY, stable scheme identity

Keep existing PK `scheme_id`. Existing public metadata remains for backward compatibility through 3D. Add:

| Column | Type | Null | Definition |
| --- | --- | --- | --- |
| `canonical_scheme_key` | `varchar(255)` | no | Stable normalized identity, e.g. `central:agriculture:pm-kisan`; generated/approved, never reinterpreted. |
| `primary_source_id` | UUID | yes | FK -> `tbl_scheme_source.source_id`, `ON DELETE RESTRICT`; authority owning the official identifier when known. |
| `current_published_version_id` | UUID | yes | FK -> `tbl_scheme_version.scheme_version_id`, `ON DELETE RESTRICT`; only the currently active published version. Added after version table creation to avoid a cycle. |
| `identity_status` | `varchar(30)` | no | `ACTIVE`, `RETIRED`, or `MERGED`; default `ACTIVE`. This is identity lifecycle, not version publication. |
| `merged_into_scheme_id` | UUID | yes | Self-FK -> `tbl_scheme_master.scheme_id`, `ON DELETE RESTRICT`; required when status is `MERGED`. |
| `created_at` | timestamptz | no | Existing data backfilled at migration time. |
| `updated_at` | timestamptz | no | Maintained on compatible identity updates only. |

Constraints/indexes:

* `uq_scheme_master_canonical_key` unique (`canonical_scheme_key`).
* `uq_scheme_master_source_identifier` unique (`primary_source_id`, `official_scheme_identifier`) **where `official_scheme_identifier IS NOT NULL`**.
* `ck_scheme_master_identity_status` restricts `ACTIVE`, `RETIRED`, `MERGED`.
* `ck_scheme_master_merged_target`: `(identity_status <> 'MERGED' AND merged_into_scheme_id IS NULL) OR (identity_status = 'MERGED' AND merged_into_scheme_id IS NOT NULL AND merged_into_scheme_id <> scheme_id)`.
* Index `(identity_status, current_published_version_id)` for active catalogue queries.

Existing mutable columns (`description`, benefit, dates, source fields, group-combining operator, status, `scheme_version`) remain temporarily as a legacy read projection. From 3D forward, services populate/update them only from the current published version in the same transaction; new ingestion logic must not treat them as authoritative. Do not remove them in 3B–3F.

### 3.2 `tbl_scheme_source` — MODIFY, source registry

Retain `source_id`, current name/type/base URL/authority/status/timestamps. Add:

| Column | Type | Null | Definition |
| --- | --- | --- | --- |
| `canonical_base_url` | varchar(500) | yes | Canonicalized base origin/path used for dedupe; no credentials/query secrets. |
| `publisher_name` | varchar(255) | yes | Legal/administrative publisher name. |
| `publisher_jurisdiction` | varchar(100) | yes | `INDIA`, state/UT code, or other controlled jurisdiction token. |
| `authoritative_status` | varchar(30) | no | `OFFICIAL`, `AUTHORITATIVE`, `REFERENCE_ONLY`, `UNVERIFIED`; default `UNVERIFIED`. |
| `authority_basis` | text | yes | Reviewable explanation/reference for status. |
| `default_language` | varchar(10) | no | BCP-47-like project token, default `en`. |
| `precedence_rank` | smallint | no | Lower value wins when sources conflict; default 100. |
| `fetch_policy` | jsonb | yes | Non-secret allowed methods, interval, rate limits and discovery settings. |
| `status_reason` | text | yes | Required when disabling/retiring. |
| `last_successful_retrieval_at` | timestamptz | yes | Operational field. |

Replace the informal source status with `ENABLED`, `PAUSED`, `RETIRED`, `BLOCKED`; migrate current `ACTIVE` to `ENABLED`, `INACTIVE` to `PAUSED`. This is an explicit data migration. Add checks for source status, authoritative status, non-negative precedence rank, and `canonical_base_url` beginning with `https://` for network sources. Add unique partial index on `canonical_base_url` where non-null and index `(status, precedence_rank)`.

### 3.3 `tbl_scheme_source_document` — MODIFY and rename at ORM/API level to source snapshot

Do not rename the physical table during 3B–3F. Its existing `source_document_id` becomes the immutable **snapshot ID**. Remove no column. Add:

| Column | Type | Null | Definition |
| --- | --- | --- | --- |
| `source_resource_id` | UUID | no | FK -> `tbl_scheme_source_resource.source_resource_id`, `ON DELETE RESTRICT`. |
| `retrieval_sequence` | integer | no | Monotonic sequence per resource, starts 1. |
| `canonical_url` | varchar(1000) | no | URL after canonicalization/redirection policy. |
| `content_object_uri` | varchar(1000) | yes | Immutable object-store URI/key for original bytes; mandatory for successful binary/content retrieval. |
| `content_length_bytes` | bigint | yes | Exact retrieved bytes, >= 0. |
| `mime_type` | varchar(255) | yes | Observed/effective MIME type. |
| `charset` | varchar(100) | yes | Observed character encoding when applicable. |
| `http_status_code` | smallint | yes | 100–599 for HTTP fetches. |
| `http_etag` | varchar(500) | yes | Stored verbatim, never used alone as change proof. |
| `http_last_modified_at` | timestamptz | yes | Parsed header/source metadata. |
| `source_updated_at` | timestamptz | yes | Timestamp claimed by source content. |
| `retrieval_status` | varchar(30) | no | `SUCCEEDED`, `NOT_MODIFIED`, `FAILED`, `SKIPPED`; default `SUCCEEDED` only for legacy rows after explicit backfill rule. |
| `retrieval_error_code` | varchar(100) | yes | Safe classified error, not secrets. |
| `retrieval_error_detail` | text | yes | Sanitized detail. |
| `observed_metadata` | jsonb | yes | Safe headers/API cursor/file metadata. |

Rules/constraints:

* Existing `document_url` remains original discovered URL and `document_name` remains display name.
* `content_hash` is SHA-256 lowercase hex. Add check `content_hash ~ '^[0-9a-f]{64}$'` when non-null.
* Unique `(source_resource_id, retrieval_sequence)` and unique partial `(source_resource_id, content_hash)` where `content_hash IS NOT NULL AND retrieval_status = 'SUCCEEDED'`; identical content is represented by a `NOT_MODIFIED` retrieval item, not a duplicate success snapshot.
* Add index `(source_resource_id, retrieved_at DESC)` and `(content_hash)`.
* A `SUCCEEDED` snapshot requires `retrieved_at`, `content_hash`, and `content_length_bytes`; failed snapshots require `retrieval_error_code` and must have no `content_object_uri`/content hash.
* Existing `(source_id, document_name, version)` uniqueness remains until legacy rows are migrated; it is no longer the logical identity rule.
* Snapshots and source resources use `RESTRICT`, never cascade deletion. Audit material is retained.

### 3.4 `tbl_scheme_source_content` — MODIFY, extraction artifact

Retain table/PK `content_id`, FK to snapshot, and current textual fields for compatibility. Add:

| Column | Type | Null | Definition |
| --- | --- | --- | --- |
| `artifact_kind` | varchar(30) | no | `RAW_TEXT`, `NORMALIZED_TEXT`, `EXTRACTED_TEXT`, `OCR_TEXT`, `STRUCTURED_JSON`; maps existing `content_type` during backfill. |
| `artifact_sequence` | integer | no | Version sequence for same snapshot/kind/language. |
| `content_hash` | varchar(64) | yes | SHA-256 of artifact textual/JSON canonical bytes. |
| `object_uri` | varchar(1000) | yes | Object-store location for artifact too large for text columns. |
| `page_map` | jsonb | yes | PDF page-to-offset metadata; required for page-addressable PDF extraction. |
| `parser_name` | varchar(100) | yes | Extractor/parser identity. |
| `parser_version` | varchar(100) | yes | Reproducible implementation/model version. |
| `processing_error_code` | varchar(100) | yes | Classified failure. |
| `processing_error_detail` | text | yes | Sanitized failure detail. |

`content_type` remains populated with the compatible legacy value; new code uses `artifact_kind`. Replace the old unique `(source_document_id, content_type, language)` with `(source_document_id, artifact_kind, language, artifact_sequence)` and unique `(source_document_id, artifact_kind, language, parser_name, parser_version, content_hash)` where hash is non-null. Checks constrain kind/status and require a parser name/version for non-raw artifacts. Index `(source_document_id, artifact_kind, language, artifact_sequence DESC)`.

### 3.5 `tbl_scheme_ingestion_run` — MODIFY, operational run header

Add:

| Column | Type | Null | Definition |
| --- | --- | --- | --- |
| `adapter_type` | varchar(30) | no | `API`, `HTML`, `PDF`, `JSON`, `MANUAL`; legacy records `MANUAL`. |
| `adapter_version` | varchar(100) | no | Version of adapter implementation. |
| `trigger_type` | varchar(30) | no | `SCHEDULED`, `MANUAL`, `RETRY`, `WEBHOOK`; legacy `MANUAL`. |
| `requested_by_actor_id` | UUID | yes | Actor reference without FK until actor model exists. |
| `configuration_snapshot` | jsonb | no | Redacted, immutable run configuration. |
| `idempotency_key` | varchar(255) | yes | Caller/run-key to prevent duplicate manual requests. |
| `candidate_batch_id` | UUID | yes | FK -> `tbl_scheme_candidate_batch`, `ON DELETE RESTRICT`; added after that table. |
| `failure_code` | varchar(100) | yes | Classified terminal failure. |
| `cancelled_at` | timestamptz | yes | Cancellation time. |

Replace run statuses with `QUEUED`, `RUNNING`, `COMPLETED`, `PARTIALLY_COMPLETED`, `FAILED`, `CANCELLED`. Backfill completed legacy runs to `COMPLETED`. Add status check, `completed_at` required for all terminal statuses, partial unique index `(source_id, idempotency_key)` where key non-null, and index `(source_id, started_at DESC)`.

### 3.6 `tbl_scheme_rule_provenance` — MODIFY, published-rule evidence link

Retain existing IDs/FKs/source fields. Add:

| Column | Type | Null | Definition |
| --- | --- | --- | --- |
| `content_id` | UUID | yes | FK -> `tbl_scheme_source_content.content_id`, `ON DELETE RESTRICT`; mandatory for new records. |
| `start_offset` | integer | yes | Inclusive zero-based character offset in selected artifact. |
| `end_offset` | integer | yes | Exclusive offset, > start offset. |
| `source_locator` | jsonb | yes | PDF coordinate, DOM selector, JSON pointer, or API path. |
| `quote_hash` | varchar(64) | yes | SHA-256 of normalized quoted text. |
| `evidence_role` | varchar(30) | no | `PRIMARY`, `SUPPORTING`, `CONTRADICTING`; default `PRIMARY`. |
| `reviewed_by_actor_id` | UUID | yes | Actor reference. |
| `review_note` | text | yes | Review rationale. |

New rows require `content_id`, `source_text`, `quote_hash`, and at least one locator (page+section, offsets, or structured `source_locator`). `source_text` hash must match `quote_hash` in application validation. Verification statuses are `PENDING`, `VERIFIED`, `REJECTED`, `SUPERSEDED`; add check and indexes `(content_id)` and `(rule_id, verification_status)`. Keep source-document FK as snapshot provenance.

### 3.7 `tbl_eligibility_assessment` — MODIFY in 3E

The current legacy unique row remains the current-result cache. Add:

| Column | Type | Null | Definition |
| --- | --- | --- | --- |
| `scheme_version_id` | UUID | yes | FK -> `tbl_scheme_version.scheme_version_id`, `ON DELETE RESTRICT`; required for all newly evaluated rows. |
| `evaluated_at` | timestamptz | yes | Exact evaluation time. |
| `engine_version` | varchar(100) | yes | Deterministic engine implementation/DSL version. |
| `rule_outcomes` | jsonb | yes | Typed per-rule/group result evidence; replaces untyped-only detail gradually. |

Change the status data contract to exactly `ELIGIBLE`, `NOT_ELIGIBLE`, `INSUFFICIENT_INFORMATION`; a check constraint is added only after all backfill has converted legacy nulls. `eligibility_result` remains non-null for API compatibility: `true` iff status `ELIGIBLE`; `false` for the other two statuses. Remove `POTENTIALLY_ELIGIBLE` from model constants/API semantics, but do not delete historical data; migrate it to `INSUFFICIENT_INFORMATION` with migration audit note.

Add `ck_assessment_status_boolean` enforcing the mapping where status is non-null, and index `(citizen_id, scheme_version_id, evaluated_at DESC)`. Do not change the existing unique `(citizen_id, scheme_id)` in 3E; version history is stored in a new table below.

## 4. New tables — source snapshots and ingestion (3B)

### 4.1 `tbl_scheme_source_resource`

Logical addressable government resource, separate from a snapshot.

| Column | Type | Null | Definition |
| --- | --- | --- | --- |
| `source_resource_id` | UUID PK | no | Generated UUID. |
| `source_id` | UUID FK | no | -> source, `ON DELETE RESTRICT`. |
| `resource_type` | varchar(30) | no | `API_ENDPOINT`, `HTML_PAGE`, `PDF_DOCUMENT`, `JSON_DOCUMENT`, `PORTAL_RECORD`, `MANUAL_RECORD`. |
| `discovered_url` | varchar(1000) | no | URL/name at discovery. |
| `canonical_url` | varchar(1000) | no | Canonical fetch identity. |
| `external_resource_identifier` | varchar(255) | yes | API/document ID where supplied. |
| `display_name` | varchar(500) | yes | Latest safe display name. |
| `language` | varchar(10) | yes | Known/default language. |
| `status` | varchar(30) | no | `ACTIVE`, `UNAVAILABLE`, `RETIRED`, `BLOCKED`; default `ACTIVE`. |
| `first_discovered_at` | timestamptz | no | Discovery time. |
| `last_checked_at` | timestamptz | yes | Last retrieval attempt. |
| `latest_snapshot_id` | UUID | yes | FK -> source document snapshot, added after snapshot reference/backfill. |
| `created_at`, `updated_at` | timestamptz | no | Audit timestamps. |

Constraints: unique `(source_id, canonical_url)`; unique partial `(source_id, external_resource_identifier)` where identifier non-null; resource-type/status checks; index `(source_id, status)`.

### 4.2 `tbl_scheme_ingestion_item`

One discover/fetch/extract attempt for one source resource within one run.

| Column | Type | Null | Definition |
| --- | --- | --- | --- |
| `ingestion_item_id` | UUID PK | no | Generated UUID. |
| `ingestion_run_id` | UUID FK | no | -> ingestion run, `ON DELETE RESTRICT`. |
| `source_resource_id` | UUID FK | yes | -> source resource, `ON DELETE RESTRICT`; null only before discovery persists resource. |
| `source_document_id` | UUID FK | yes | -> source snapshot, `ON DELETE RESTRICT`. |
| `item_sequence` | integer | no | Deterministic sequence in run. |
| `stage` | varchar(30) | no | `DISCOVERED`, `FETCHED`, `EXTRACTED`, `PROPOSED`, `SKIPPED`, `FAILED`. |
| `outcome` | varchar(30) | no | `CREATED`, `UNCHANGED`, `UPDATED_SOURCE`, `FAILED`, `SKIPPED`. |
| `started_at`, `completed_at` | timestamptz | yes | Item timings. |
| `error_code`, `error_detail` | varchar(100), text | yes | Sanitized failure detail. |
| `metadata` | jsonb | yes | Adapter item metadata/cursor/selector. |

Unique `(ingestion_run_id, item_sequence)`; indexes on run and resource; terminal-stage/time consistency check. A completed item never changes its immutable snapshot link.

## 5. New tables — candidate extraction, evidence, validation (3C)

### 5.1 `tbl_scheme_candidate_batch`

Candidate output boundary for a run. One run may create at most one batch.

Columns: `candidate_batch_id` UUID PK; `ingestion_run_id` UUID unique FK -> run (`RESTRICT`); `status` (`DRAFT`, `VALIDATING`, `VALIDATED`, `REVIEW_REQUIRED`, `REJECTED`, `PUBLISHED`, `SUPERSEDED`); `extractor_name` varchar(100); `extractor_version` varchar(100); `model_metadata` jsonb nullable/redacted; `created_at`; `validated_at`; `published_at`; `created_by_actor_id` UUID nullable; `summary` jsonb nullable; `validation_summary` jsonb nullable.

Indexes `(status, created_at DESC)`. A batch can progress to `PUBLISHED` only through a successful candidate version publication.

### 5.2 `tbl_scheme_candidate`

One proposed scheme representation, which may match an existing identity or propose a new identity.

Columns: `candidate_scheme_id` UUID PK; `candidate_batch_id` UUID FK -> batch (`CASCADE`); `matched_scheme_id` UUID FK -> master (`RESTRICT`) nullable; `proposed_canonical_scheme_key` varchar(255) nullable; `official_scheme_identifier` varchar(100) nullable; `scheme_name` varchar(255) not null; `department_name` varchar(255); `scheme_category` varchar(50); `description` text; `benefit_description` text; `application_url` varchar(500); `application_window_type` varchar(30); `application_open_at`, `application_close_at`, `scheme_effective_from`, `scheme_effective_to` dates nullable; `candidate_status` (`EXTRACTED`, `VALIDATION_FAILED`, `VALIDATED`, `REVIEW_REQUIRED`, `APPROVED`, `REJECTED`, `PUBLISHED`) not null; `extraction_confidence` numeric(4,3) nullable; `unresolved_summary` text nullable; `metadata` jsonb nullable; timestamps.

Checks: either matched identity or proposed key must exist; confidence 0–1; date ordering; status. Index `(candidate_batch_id, candidate_status)` and `(matched_scheme_id, candidate_status)`.

### 5.3 `tbl_scheme_candidate_rule_group`

Columns: UUID `candidate_group_id` PK; `candidate_scheme_id` FK cascade; `parent_candidate_group_id` self FK restrict nullable (reserved for nested groups); `group_name` varchar(255) not null; `logical_operator` (`AND`, `OR`, `NOT`) not null; `requirement_type` (`ELIGIBILITY`, `EXCLUSION`, `DOCUMENT`, `APPLICATION_WINDOW`) not null; `display_order` integer not null default 1; `candidate_status` (`SUPPORTED`, `UNSUPPORTED`, `AMBIGUOUS`, `REJECTED`) not null; `original_text` text nullable; timestamps.

Unique `(candidate_scheme_id, parent_candidate_group_id, display_order)`. Check: `NOT` groups have exactly one child enforced in application validation (not cross-row SQL). Index candidate scheme.

### 5.4 `tbl_scheme_candidate_rule`

Columns: UUID `candidate_rule_id` PK; `candidate_group_id` FK cascade; `fact_code` varchar(100) nullable; `operator_code` varchar(30) nullable; `value_json` jsonb nullable; `data_type` varchar(20) nullable; `unit_code` varchar(50) nullable; `requirement_type` as above; `rule_effective_from`, `rule_effective_to` date nullable; `original_text` text not null; `normalized_text` text nullable; `candidate_status` (`SUPPORTED`, `UNSUPPORTED`, `AMBIGUOUS`, `INVALID`, `REJECTED`) not null; `unsupported_reason_code` varchar(100) nullable; `extraction_confidence` numeric(4,3) nullable; `display_order` integer not null default 1; `metadata` jsonb nullable; timestamps.

Checks: confidence range; supported rows require fact/operator/data type/value; unsupported/ambiguous rows require reason; dates ordered. Unique `(candidate_group_id, display_order)`. Index `(fact_code, candidate_status)`.

### 5.5 `tbl_scheme_candidate_document_requirement`

Columns: UUID `candidate_document_requirement_id` PK; `candidate_scheme_id` FK cascade; `candidate_rule_id` FK set null; `document_type_code` varchar(100) not null; `requirement_mode` (`REQUIRED`, `OPTIONAL`, `ALTERNATIVE`) not null; `alternative_set_code` varchar(100) nullable; `description` text nullable; `issuer_name` varchar(255) nullable; `verification_required` boolean not null default false; `candidate_status` same candidate rule status; `original_text` text nullable; timestamps.

Check alternative mode requires set code; indexes on candidate scheme/rule.

### 5.6 `tbl_scheme_candidate_geography`

Columns: UUID PK; candidate scheme FK cascade; `geography_code` varchar(50) not null; `geography_level` (`COUNTRY`, `STATE_UT`, `DISTRICT`, `LOCAL_BODY`, `CONSTITUENCY`, `REGION`) not null; `inclusion_mode` (`INCLUDE`, `EXCLUDE`) not null; `candidate_status`; `original_text`; timestamps. Unique `(candidate_scheme_id, geography_code, inclusion_mode)`.

### 5.7 `tbl_scheme_evidence_reference`

Generic evidence reference for candidate nodes and future non-rule source claims. This is required because published provenance needs a published rule ID.

Columns: UUID `evidence_reference_id` PK; `source_document_id` FK restrict not null; `content_id` FK restrict not null; `candidate_scheme_id`, `candidate_group_id`, `candidate_rule_id`, `candidate_document_requirement_id`, `candidate_geography_id` nullable FKs cascade; `evidence_role` (`PRIMARY`, `SUPPORTING`, `CONTRADICTING`) not null; `source_quote` text not null; `quote_hash` varchar(64) not null; `page_number` integer nullable; `section_label` varchar(255) nullable; `start_offset`, `end_offset` integer nullable; `locator` jsonb nullable; `created_at`.

Exactly one candidate target must be non-null—enforce with a PostgreSQL `num_nonnulls(...) = 1` check. Require an offset pair or a locator/page+section. Hash format check. Index each target FK and `(content_id, quote_hash)`. Evidence is copied/linked into `tbl_scheme_rule_provenance` at publication without losing candidate evidence.

### 5.8 `tbl_scheme_validation_finding`

Columns: UUID PK; `candidate_batch_id` FK cascade not null; candidate target FKs nullable (same one-target check); `severity` (`ERROR`, `WARNING`, `INFO`) not null; `finding_code` varchar(100) not null; `message` text not null; `details` jsonb nullable; `validator_name`, `validator_version` varchar(100) not null; `status` (`OPEN`, `WAIVED`, `RESOLVED`) not null default `OPEN`; `resolved_by_actor_id` UUID nullable; `resolved_at` timestamptz nullable; `resolution_note` text nullable; timestamps.

Publication blocks if any `ERROR` finding remains `OPEN`; waiving `ERROR` is forbidden by service policy. Index `(candidate_batch_id, severity, status)`.

### 5.9 `tbl_scheme_review_decision`

Append-only human/system review audit.

Columns: UUID PK; `candidate_scheme_id` FK restrict not null; `decision` (`REQUEST_CHANGES`, `APPROVE`, `REJECT`, `PUBLISH`) not null; `decision_reason` text not null; `reviewer_actor_id` UUID nullable; `reviewer_role` varchar(50) not null; `snapshot` jsonb not null (candidate state/diff summary at decision); `created_at`.

Index `(candidate_scheme_id, created_at DESC)`. Only a reviewer role authorized by deployment policy may make `PUBLISH`; the application records the role but authorization is external to SQL until an actor model exists.

## 6. New tables — immutable versions and publication (3D)

### 6.1 `tbl_scheme_version`

| Column | Type | Null | Definition |
| --- | --- | --- | --- |
| `scheme_version_id` | UUID PK | no | Immutable version identity. |
| `scheme_id` | UUID FK | no | -> master, `ON DELETE RESTRICT`. |
| `version_number` | integer | no | Monotonic positive integer per scheme. |
| `version_status` | varchar(30) | no | `DRAFT`, `PUBLISHED`, `SUPERSEDED`, `ARCHIVED`, `REJECTED`; default `DRAFT`. |
| `source_candidate_scheme_id` | UUID FK | yes | -> candidate scheme, `ON DELETE RESTRICT`; mandatory for new ingested publications. |
| `publication_source_document_id` | UUID FK | yes | -> source snapshot, `RESTRICT`; primary source record. |
| `scheme_name`, `department_name`, `scheme_category` | compatible | no/yes | Snapshot public metadata. |
| `description`, `benefit_description` | text | yes | Snapshot public metadata. |
| `official_scheme_identifier` | varchar(100) | yes | Snapshot identifier. |
| `application_url` | varchar(500) | yes | Snapshot URL. |
| `application_window_type` | varchar(30) | yes | `CONTINUOUS`, `FIXED_WINDOW`, `RENEWAL`, `UNKNOWN`. |
| `application_open_at`, `application_close_at` | date | yes | Application window, distinct from validity. |
| `effective_from`, `effective_to` | date | yes | Scheme validity. |
| `published_at` | timestamptz | yes | Required when published. |
| `publication_date` | date | yes | Source/administrative publication date if known. |
| `superseded_by_version_id` | UUID self FK | yes | `RESTRICT`; set at successor publication. |
| `change_summary` | text | yes | Reviewer-approved human summary. |
| `change_diff` | jsonb | yes | Deterministic metadata/rule/document/geography diff. |
| `published_by_actor_id` | UUID | yes | Publisher audit. |
| `created_at` | timestamptz | no | Audit. |

Constraints/indexes:

* unique `(scheme_id, version_number)`;
* one partial unique index on `scheme_id` where `version_status = 'PUBLISHED' AND effective_to IS NULL` only if product policy permits one open-current version; otherwise service selection uses date ranges. This specification adopts **one current open published version per scheme**;
* check status, positive number, date ordering, self-supersession prevention; published requires `published_at` and source candidate (except migration-created legacy v1); superseded requires successor;
* index `(scheme_id, version_status, effective_from DESC)` and `(version_status, application_open_at, application_close_at)`.

No UPDATE may alter public/rule-linked fields after `PUBLISHED`; service/database trigger policy allows only transition to `SUPERSEDED`/`ARCHIVED`, setting supersession pointers and audit fields. If database triggers are out of project convention, enforce with repository transactional policy and tests, but the invariance is mandatory.

### 6.2 `tbl_scheme_version_rule_group`

Columns: UUID `scheme_version_group_id` PK; `scheme_version_id` FK restrict; `parent_group_id` self FK restrict nullable; `group_name` varchar(255) not null; `logical_operator` (`AND`, `OR`, `NOT`) not null; `requirement_type` (`ELIGIBILITY`, `EXCLUSION`, `DOCUMENT`, `APPLICATION_WINDOW`) not null; `display_order` integer not null; `effective_from`, `effective_to` dates nullable; `source_candidate_group_id` UUID FK restrict nullable; timestamps.

Unique `(scheme_version_id, parent_group_id, display_order)`; index version; date check. A version must have at least one root group before publishing, enforced in publication service.

### 6.3 `tbl_scheme_version_rule`

Columns: UUID `scheme_version_rule_id` PK; `scheme_version_group_id` FK restrict; `fact_code` varchar(100) not null; `operator_code` varchar(30) not null; `value_json` jsonb not null; `data_type` varchar(20) not null; `unit_code` varchar(50) nullable; `requirement_type` same enum not null; `rule_description` text nullable; `display_order` integer not null; `effective_from`, `effective_to` dates nullable; `source_candidate_rule_id` UUID FK restrict nullable; `created_at`.

Unique `(scheme_version_group_id, display_order)`; indexes `(fact_code)`, `(scheme_version_group_id)`; constraints for known data types and dates. The allowed `operator_code` values are `EQ`, `NEQ`, `LT`, `LTE`, `GT`, `GTE`, `IN`, `NOT_IN`, `EXISTS`, `NOT_EXISTS`, `DATE_BEFORE`, `DATE_ON_OR_BEFORE`, `DATE_AFTER`, `DATE_ON_OR_AFTER`. Only operators implemented in a given engine DSL version may be published; this 3E initial engine permits `EQ`, `NEQ`, `LT`, `LTE`, `GT`, `GTE`, `IN`, `NOT_IN`, and date comparators for registered DATE facts.

### 6.4 `tbl_scheme_version_document_requirement`

Columns: UUID PK; `scheme_version_id` FK restrict; `scheme_version_rule_id` FK restrict nullable; `document_type_code` varchar(100) not null; `requirement_mode` (`REQUIRED`, `OPTIONAL`, `ALTERNATIVE`) not null; `alternative_set_code` varchar(100) nullable; `description` text nullable; `issuer_name` varchar(255) nullable; `verification_required` boolean not null default false; `effective_from`, `effective_to` dates nullable; `source_candidate_document_requirement_id` UUID FK restrict nullable; `created_at`.

Unique `(scheme_version_id, document_type_code, alternative_set_code)`; indexes version/rule. Required documents without a future citizen-evidence feature still appear as unmet information, not false eligibility.

### 6.5 `tbl_scheme_version_geography`

Columns: UUID PK; `scheme_version_id` FK restrict; `geography_code` varchar(50) not null; `geography_level` enum; `inclusion_mode` enum; `source_candidate_geography_id` UUID FK restrict nullable; `created_at`.

Unique `(scheme_version_id, geography_code, inclusion_mode)` and version index. Initial 3E supports only `COUNTRY`, `STATE_UT`, `DISTRICT`, and `AREA_TYPE` where canonical fact coverage exists; other levels may publish as metadata only if no eligibility rule references them.

### 6.6 `tbl_scheme_version_publication`

Immutable event record, one row per publication transition.

Columns: UUID PK; `scheme_version_id` UUID unique FK restrict; `candidate_scheme_id` UUID FK restrict; `publication_decision_id` UUID FK restrict; `published_by_actor_id` UUID nullable; `published_at` timestamptz not null; `publication_note` text nullable; `publication_snapshot_hash` varchar(64) not null; `created_at`.

The hash is over a canonical serialized version payload and protects audit/diff integrity. Index candidate scheme.

### 6.7 `tbl_scheme_eligibility_assessment_history`

Immutable assessment history; the existing assessment row remains latest cache.

Columns: UUID `assessment_history_id` PK; `assessment_id` UUID FK -> current assessment `ON DELETE SET NULL`; `citizen_id` UUID FK -> citizen `ON DELETE RESTRICT`; `scheme_id` UUID FK -> master `RESTRICT`; `scheme_version_id` UUID FK -> version `RESTRICT`; `eligibility_status` varchar(30) not null; `reason` text nullable; `evaluation_details` jsonb not null; `rule_outcomes` jsonb not null; `missing_facts` jsonb not null default `[]`; `missing_documents` jsonb not null default `[]`; `engine_version` varchar(100) not null; `evaluated_at` timestamptz not null; `created_at` timestamptz not null.

Check status belongs to the three statuses; index `(citizen_id, evaluated_at DESC)`, `(scheme_version_id, evaluated_at DESC)`, and `(citizen_id, scheme_id, scheme_version_id, evaluated_at DESC)`. It is append-only.

## 7. Fact registry and deterministic DSL (3E)

### 7.1 `tbl_eligibility_fact_definition` — NEW

This formalizes current profile mapping and engine resolver support without replacing profile facts.

Columns: `fact_definition_id` UUID PK; `fact_code` varchar(100) unique not null; `display_name` varchar(255) not null; `data_type` (`STRING`, `INTEGER`, `DECIMAL`, `BOOLEAN`, `DATE`, `JSON`) not null; `unit_code` varchar(50) nullable; `cardinality` (`SINGLE`, `MULTI`, `HOUSEHOLD_AGGREGATE`) not null default `SINGLE`; `resolver_key` varchar(100) nullable; `resolver_status` (`SUPPORTED`, `METADATA_ONLY`, `DEPRECATED`) not null; `source_policy` (`SELF_DECLARED_ALLOWED`, `VERIFIED_REQUIRED`, `GOVERNMENT_VERIFIED_REQUIRED`) not null; `freshness_days` integer nullable; `description` text nullable; `created_at`, `updated_at`.

Constraint: supported resolver status requires resolver key; non-negative freshness. Index `(resolver_status, data_type)`. Initial rows map only currently verified resolver capabilities—do not claim every Phase 2 profile field is evaluator-supported until its resolver is implemented and tested.

### 7.2 Rule semantics

Each rule resolves to `PASS`, `FAIL`, `UNKNOWN`, or `UNSUPPORTED` internally.

* `PASS`: fact/evidence is present, valid/fresh enough, and predicate holds.
* `FAIL`: fact/evidence is present and predicate conclusively does not hold.
* `UNKNOWN`: required fact/document is absent, unreadable, stale, not verified where policy requires, or cannot be resolved.
* `UNSUPPORTED`: a published version must never contain it. If a legacy version contains it, map result to `UNKNOWN` and log a data-integrity error.

Group logic uses Kleene-style three-valued evaluation: AND returns FAIL if any child fails; PASS only if all pass; otherwise UNKNOWN. OR returns PASS if any child passes; FAIL only if all fail; otherwise UNKNOWN. `NOT` reverses PASS/FAIL and preserves UNKNOWN. An exclusion group is evaluated by its own expression then interpreted as: PASS means `NOT_ELIGIBLE`, FAIL means it does not disqualify, UNKNOWN contributes `INSUFFICIENT_INFORMATION` unless another required/exclusion rule conclusively decides the scheme.

Scheme-level precedence is: any conclusive required-rule failure or confirmed exclusion -> `NOT_ELIGIBLE`; otherwise any unknown required/document/window/geography result -> `INSUFFICIENT_INFORMATION`; otherwise -> `ELIGIBLE`.

Application windows are not applicant eligibility facts. A closed/unavailable window produces `INSUFFICIENT_INFORMATION` for applicability unless product policy explicitly defines it as a non-eligibility availability state; it must never be presented as an applicant `NOT_ELIGIBLE` reason.

## 8. Lifecycle transitions

### 8.1 Source and snapshot

`ENABLED -> PAUSED | BLOCKED | RETIRED`; `PAUSED -> ENABLED`; `BLOCKED -> PAUSED | ENABLED`; `RETIRED` is terminal except documented administrative restoration. A resource moves `ACTIVE -> UNAVAILABLE | BLOCKED | RETIRED`; a new successful retrieval may restore `UNAVAILABLE -> ACTIVE`.

Run: `QUEUED -> RUNNING -> COMPLETED | PARTIALLY_COMPLETED | FAILED | CANCELLED`. A terminal run does not reopen; retry is a new run with trigger `RETRY` and parent reference in configuration metadata.

Snapshot retrieval status is immutable after creation. New observation means new ingestion item; content change means new successful snapshot sequence.

### 8.2 Candidate and validation

Batch: `DRAFT -> VALIDATING -> VALIDATED | REVIEW_REQUIRED | REJECTED`; `VALIDATED -> REVIEW_REQUIRED`; `REVIEW_REQUIRED -> VALIDATED | REJECTED`; `VALIDATED -> PUBLISHED`; `PUBLISHED -> SUPERSEDED` only when all candidate schemes are superseded.

Candidate scheme: `EXTRACTED -> VALIDATION_FAILED | VALIDATED | REVIEW_REQUIRED`; `VALIDATION_FAILED -> EXTRACTED` only through a newly generated candidate revision, not overwrite; `VALIDATED/REVIEW_REQUIRED -> APPROVED | REJECTED`; `APPROVED -> PUBLISHED`. Any open error finding prevents `APPROVED` and `PUBLISHED`.

### 8.3 Published version

`DRAFT -> PUBLISHED`; `PUBLISHED -> SUPERSEDED | ARCHIVED`; `SUPERSEDED -> ARCHIVED`. A rejected candidate never creates a published version. A published version is immutable except status/supersession fields. Publishing a successor updates predecessor to `SUPERSEDED`, sets its `superseded_by_version_id`, updates master `current_published_version_id`, and writes the publication event in one serializable transaction.

## 9. API contracts

All new write endpoints are admin/internal endpoints. They return correlation IDs and never expose source credentials or raw citizen data. Pagination uses `limit` (1–100, default 25) and opaque `cursor`; every list has stable ordering by creation/time + UUID.

### 9.1 Phase 3B source APIs

* `POST /api/v1/admin/scheme-sources` creates a source. Request: display/canonical URL, type, publisher/authority, authoritative status/basis, language, precedence, fetch policy. Response `201`: source object.
* `GET /api/v1/admin/scheme-sources` lists sources with status/type/authority filters.
* `GET /api/v1/admin/scheme-sources/{source_id}` returns source and resource summary.
* `PATCH /api/v1/admin/scheme-sources/{source_id}` changes registry metadata/status only; canonical URL identity change requires explicit review field.
* `POST /api/v1/admin/scheme-sources/{source_id}/ingestion-runs` queues run. Request: adapter type, optional resource IDs, redacted configuration, idempotency key. Response `202`: run ID/status.
* `GET /api/v1/admin/scheme-ingestion-runs/{run_id}` returns run counters, batch link and item summary.
* `GET /api/v1/admin/scheme-source-snapshots/{snapshot_id}` returns metadata and authorized artifact/evidence references, not a public raw object URL.

### 9.2 Phase 3C candidate/review APIs

* `GET /api/v1/admin/scheme-candidate-batches` and `/{batch_id}` list/read validation summaries and candidates.
* `GET /api/v1/admin/scheme-candidates/{candidate_scheme_id}` returns candidate metadata, expression tree, document/geography requirements, evidence, findings, review history, and diff to current published version.
* `POST /api/v1/admin/scheme-candidates/{id}/validate` reruns deterministic validators; response `202` batch/job state.
* `POST /api/v1/admin/scheme-candidates/{id}/review-decisions` appends `REQUEST_CHANGES`, `APPROVE`, or `REJECT`; request requires decision reason and expected candidate revision/version token.
* Manual candidate creation uses `POST /api/v1/admin/scheme-candidate-batches` then `POST /.../candidates`; it must supply evidence references and follows the same validation/publication route.

### 9.3 Phase 3D publication and public catalogue APIs

* `POST /api/v1/admin/scheme-candidates/{id}/publish`: requires an approved latest review, no open errors, expected candidate revision, optional approved change summary. Response `201`: immutable version and publication event. Conflict `409` if a competing successor/current version exists.
* `GET /api/v1/admin/schemes/{scheme_id}/versions`: returns all version metadata/statuses/diff summary.
* `GET /api/v1/admin/scheme-versions/{version_id}`: returns full version tree and published provenance.
* Existing `GET /api/v1/schemes` and `/{scheme_id}` remain backward compatible but read only current published versions after cutover. Add optional public `version` only for authorized/audit consumers; historical unarchived versions are not default catalogue results.

### 9.4 Phase 3E eligibility APIs

Keep `POST /api/v1/eligibility/evaluate/{citizen_id}` route for compatibility. Its response model gains `eligibility_status`, `missing_facts`, `missing_documents`, `scheme_version_id`, `evaluated_at`, `engine_version`, and typed `rule_outcomes`. `eligibility_result` remains but follows the specified Boolean mapping.

`GET /api/v1/recommendations/{citizen_id}` returns three groups or a single ordered list with status; it may not put `INSUFFICIENT_INFORMATION` into `NOT_ELIGIBLE`. No ranking algorithm is introduced in 3E.

API errors: validation failures `422`; missing source/candidate/version `404`; illegal state transition or stale expected revision `409`; unauthorised admin action `403`; fetch/extraction runtime failures are represented in run/item records, not leaked as generic candidate publication success.

## 10. Migration order

Every migration is additive first, transactional where feasible, reversible for empty/new structures, and tested against a database at `0003` plus the seven legacy seed rows. No destructive rename/drop occurs in 3B–3F.

### 3B migrations

1. Create `tbl_scheme_source_resource` without `latest_snapshot_id`; extend source registry fields/checks/indexes; backfill source status mapping.
2. Extend source document/snapshot table with nullable fields; backfill one source resource per distinct legacy `(source_id, document_url)` and attach document rows; assign sequences; then make `source_resource_id` non-null.
3. Extend content artifact table; map current content types to artifact kinds and assign sequence 1; replace old uniqueness only after backfill.
4. Extend ingestion run; create ingestion item; backfill adapter/trigger/config/status defaults and create no fictitious items for historical rows.
5. Add `latest_snapshot_id` after snapshots/resources are consistent; add all new indexes/checks in validate-safe order.

### 3C migrations

6. Create candidate batch, candidate scheme/group/rule/document/geography, generic evidence, findings, and review decision tables. No backfill from seeds: legacy schemes lack source evidence and must not be fabricated as candidates.
7. Extend published rule provenance locator columns; backfill old provenance content link as null and mark it legacy; new rows require new evidence contract at service validation level until historical data is remediated.

### 3D migrations

8. Create scheme version, version group/rule/document/geography/publication tables with all FKs initially nullable only where cyclical/backfill conditions require.
9. Backfill each existing scheme as immutable version number 1 with source candidate null, a `change_summary` stating `Legacy manual seed baseline; official source evidence not yet captured`, and copied current groups/rules/documents. Create a dedicated internal legacy source/candidate only if policy requires operational provenance; do not mark it official.
10. Add `current_published_version_id` to master, point it to each legacy v1, and make v1 published. Synchronise legacy public master fields from v1. Add final unique/current-version constraints.
11. Cut read services to current version; retain old table reads only as compatibility projection until all response/tests pass.

### 3E migrations

12. Create eligibility fact definition and seed only supported facts through a controlled data migration corresponding to tested resolver keys.
13. Extend assessment plus add immutable history. Backfill assessment status: existing `eligibility_result = true` -> `ELIGIBLE`; false -> `NOT_ELIGIBLE`; existing `POTENTIALLY_ELIGIBLE` -> `INSUFFICIENT_INFORMATION`; null status derived from Boolean. Set legacy scheme-version link to current v1 only when historically appropriate; otherwise retain null and mark historical in details.
14. Add status/Boolean consistency checks after backfill; deploy tri-state engine/API in the same release boundary; start appending history records.

### 3F migrations

15. Add operational indexes only after measured query plans: snapshot hash/resource retrieval indexes, candidate review queues, current published version lookups, fact/operator filters, assessment history indexes/partitioning plan. No partitioning is required before evidence demonstrates need.

## 11. Phase deliverables and acceptance criteria

**3B:** source registry, resources, immutable snapshot/content contract, run/item audit, one adapter skeleton that preserves data but does not publish. Acceptance: same content is idempotent; changed content creates new snapshot; raw snapshot is retrievable/auditable.

**3C:** candidate extraction/output, evidence linking, deterministic validation, review records. Acceptance: unsupported/ambiguous source text is retained and publication-blocking; candidate evidence resolves to an immutable quote.

**3D:** stable identities, immutable versions, review/publish transaction, current public projection. Acceptance: a changed source produces a new candidate and successor version without altering a previous published version.

**3E:** fact registry, typed initial DSL, tri-state evaluator, versioned assessments/API. Acceptance: missing required fact/document yields `INSUFFICIENT_INFORMATION`; known failure yields `NOT_ELIGIBLE`; LLM confidence never alters a result.

**3F:** source scheduling/change detection/operational metrics, pagination, measured indexing and retention plan. Acceptance: unchanged source does not create a version; run/item failures are auditable; catalogue/evaluation behaviour is bounded at the agreed scale target.

## 12. Explicit exclusions

Phases 3B–3F do not introduce a recommendation/ranking algorithm, GIS/Mapbox/QGIS, unrestricted web crawling, automatic legal interpretation, citizen document upload/storage implementation, or an LLM eligibility decision. They define interfaces that later phases may use.

---

STATUS: PHASE 3B–3F IMPLEMENTATION SPECIFICATION COMPLETE  
CODE CHANGES: NONE  
DATABASE CHANGES: NONE  
MIGRATIONS: NONE
