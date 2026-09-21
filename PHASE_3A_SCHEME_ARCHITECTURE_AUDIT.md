# Phase 3A — Scheme Architecture Audit and Ingestion Design

**Audit date:** 2026-09-20  
**Scope:** planning only. Findings below come from the current repository models, migrations, seed file, services, API routes, and tests. No application behaviour is changed by this document.

## 1. Executive summary

The repository already has a useful, additive Phase 1 foundation for source-aware schemes: a source registry, versioned source documents, raw/normalized/extracted text variants, rule provenance, and ingestion-run bookkeeping were introduced by migration `0003`. It also already has profile facts and a deterministic, explainable rule evaluator.

The foundation is not yet an ingestion pipeline. There are no adapters, source-management APIs, extraction services, candidate scheme/rule records, review/publish workflow, or code using the Phase 1 source tables. The seven current schemes are still loaded directly from `backend/seed_data/schemes.json`; they have no source-registry rows, source documents, rule provenance, or populated Phase 1 source/version fields.

The central design recommendation is therefore to **extend, not replace**, the existing concepts:

* retain `tbl_scheme_source`, `tbl_scheme_source_document`, `tbl_scheme_source_content`, `tbl_scheme_rule_provenance`, and `tbl_scheme_ingestion_run` as the source/audit spine;
* keep published rules in `tbl_scheme_eligibility_rule` and preserve the deterministic engine as the only authority that computes citizen eligibility;
* add an explicit candidate/review layer and an immutable published-scheme-version layer before any automatic ingestion is allowed to publish;
* replace the evaluator's current Boolean-only runtime outcome with a true three-valued result (`ELIGIBLE`, `NOT_ELIGIBLE`, `UNKNOWN`) in a later implementation phase. The database has fields prepared for this, but the current endpoint does not populate them.

## 2. Current architecture inventory

| Area | Actual component | Current role | Phase 3A finding |
| --- | --- | --- | --- |
| Scheme catalogue | `SchemeMaster` / `tbl_scheme_master` | One mutable row per seeded scheme; holds public metadata and active status | Has initial source/version columns but cannot preserve historical published versions. |
| Rules | `SchemeRuleGroup`, `SchemeEligibilityRule` | Two-level AND/OR rule tree | Simple but real DSL; values are strings and parameter resolution is hard-coded. |
| Required documents | `SchemeDocumentMaster` | Scheme-level required/optional document list | Not associated with a particular rule and not evaluated. |
| Sources | `SchemeSource` | Registry of named external sources | Exists, unused by seed/API; lacks authority and fetch-policy detail. |
| Snapshots/content | `SchemeSourceDocument`, `SchemeSourceContent` | Versioned document metadata and text content variants | Good start; cannot safely store arbitrary binary PDFs/HTTP metadata and content variants are unique per document/version. |
| Evidence | `SchemeRuleProvenance` | Links a published rule to source-document text/page/section | Good published-rule evidence spine; needs offsets/quote identity and candidate-rule support. |
| Ingestion runs | `SchemeIngestionRun` | Counters/status for future source runs | No adapter, item-level outcomes, configuration snapshot, or run API/service. |
| Citizen facts | `ProfileFact`, registry in `profile_mapping.py` | Typed normalized facts with provenance; AGE is derived | The future fact registry should be formally exposed to scheme-rule validation. |
| Eligibility | `EligibilityEngine` | Directly resolves 14 named citizen parameters and returns `(bool, details, reason)` | Deterministic and explainable, but Boolean-only and not source/version aware. |
| Persistence/results | `EligibilityAssessment` | Stores one latest result per citizen/scheme | Schema has status/missing evidence fields but route/repository only use the legacy Boolean fields. |
| APIs | `/api/v1/schemes`, `/eligibility`, `/recommendations` | Read schemes, evaluate active schemes, present stored results | No source, ingestion, candidate, review, publishing, version, or evidence APIs. |
| Seed/testing | `schemes.json`, `scripts/seed.py`, tests | Manual seed data and baseline tests | No ingestion or lifecycle tests beyond ORM smoke coverage. |

## 3. Existing scheme database model

### `tbl_scheme_master` (`SchemeMaster`)

* **Purpose/current use:** published catalogue row used by `SchemeRepository.get_all_active()`, scheme routes, the eligibility loop, assessments, recommendations, and the seed script.
* **Primary key:** `scheme_id` UUID.
* **Columns:** `scheme_name` (required), `department_name`, `scheme_category`, `description`, `benefit_description`, `start_date`, `status` (default `ACTIVE`), `official_source_url`, `application_url`, `last_verified_at`, `group_combining_operator` (default `AND`), and `target_persona`.
* **Phase 1 additions:** nullable `official_scheme_identifier`, `source_type`, `source_name`, `source_url`, `application_window_type`, `end_date`, `scheme_version` (default 1), `last_updated_at`, and `last_verified_at_ts`.
* **Relationships/FKs:** parent of groups, denormalized direct rules, documents, assessments; referenced optionally by source documents with `ON DELETE SET NULL`.
* **Constraints/indexes:** UUID PK; indexes `ix_scheme_category`, `ix_scheme_status`, and `ix_scheme_target_persona`. There is no unique scheme code/identifier constraint and no check constraint for statuses/operators/categories.
* **Missing for scalable published data:** stable scheme identity separated from version identity; immutable version rows; effective validity, application-window start/end and rule-effective dates as separate concepts; source snapshot FK; supersession; publication/review state; change summary/diff; canonical geography; structured benefit; government identifier uniqueness scoped to authority; and deterministic version selection.

`scheme_version` is only an integer on the same mutable catalogue row. It does not prevent changing the row/rules in place, so it is not sufficient scheme versioning.

### `tbl_scheme_rule_group` (`SchemeRuleGroup`)

* **Purpose/current use:** represents a named first-level group of eligibility rules; evaluator iterates groups ordered by `group_priority`.
* **PK/FK:** `group_id` UUID; required `scheme_id` -> scheme master, `ON DELETE CASCADE`.
* **Columns:** `group_name`, required `intra_group_operator`, `group_priority` default 1.
* **Relationships:** one scheme, many rules ordered by `rule_priority`.
* **Constraints/indexes:** no unique group name/priority per scheme and no group-table index in migration `0001`; no operator check.
* **Gap:** cannot identify exclusion vs inclusion/group semantics, nest expressions, date a group, preserve a source expression, or distinguish a candidate group from a published group.

### `tbl_scheme_eligibility_rule` (`SchemeEligibilityRule`)

* **Purpose/current use:** one leaf comparison, evaluated from a hard-coded parameter resolver.
* **PK/FKs:** `rule_id` UUID; required denormalized `scheme_id` -> master and `group_id` -> rule group, both cascading on scheme/group deletion.
* **Columns:** `parameter_name`, `operator`, `required_value` (all required strings), `rule_description`, `rule_priority`, diagnostic `failure_stage_code`, and `remedy_template`.
* **Relationships:** belongs to scheme and group; provenance rows exist conceptually but the ORM relation is only from provenance to rule.
* **Constraints/indexes:** indexes `ix_rule_scheme` and `ix_rule_group`; no validation that group belongs to the denormalized scheme, no value type/unit, no uniqueness, no operator check.
* **Gap:** rule structure has no declared fact code/data type/unit/requirement type/effective dates/status, does not model unsupported/ambiguous rules, and cannot express nested logic, aggregations, relations, document evidence, or application window predicates safely.

### `tbl_scheme_document_master` (`SchemeDocumentMaster`)

* **Purpose/current use:** public scheme document list returned in detail/recommendation responses.
* **PK/FK:** `document_id` UUID; required `scheme_id` -> scheme master, `ON DELETE CASCADE`.
* **Columns:** `document_type`, `mandatory_flag` (default true), `description`.
* **Relationships:** belongs to a scheme.
* **Constraints/indexes:** no uniqueness or index is defined; document type has comments but no controlled database registry/check.
* **Gap:** no document requirement ID/version/status, rule/group association, alternate-documents semantics, issuing authority, expiry, evidence requirements, citizen document/evidence record, or verification result.

## 4. Existing source model

### `tbl_scheme_source` (`SchemeSource`)

* **Purpose:** source registry introduced by migration `0003`; no service/repository/API currently reads or writes it.
* **PK:** `source_id` UUID.
* **Columns:** `source_name`, constrained `source_type` (`GOVERNMENT_API`, `GOVERNMENT_WEBSITE`, `GOVERNMENT_PORTAL`, `GOVERNMENT_PDF`, `OTHER_AUTHORIZED_SOURCE`), `base_url`, `authority_name`, `status` (`ACTIVE` comment only), `created_at`, `updated_at`.
* **Relationships:** one-to-many source documents and ingestion runs; both cascade on source delete.
* **Constraints/indexes:** `ck_scheme_source_type`; `uq_scheme_source_name`; no other index.
* **Assessment:** sufficient as the seed of a registry, but source name is not a durable identity and it lacks explicit authoritative/official flag and basis, publisher identity/jurisdiction, default language, precedence/priority, source-specific fetch/auth/rate policy, lifecycle reason, canonical URL uniqueness, or current-source metadata.

### `tbl_scheme_source_document` (`SchemeSourceDocument`)

* **Purpose:** a retrieved authoritative document/snapshot, optionally discovered before a scheme link.
* **PK/FKs:** `source_document_id` UUID; `source_id` required -> source (`CASCADE`); nullable `scheme_id` -> current scheme master (`SET NULL`).
* **Columns:** `document_name`, `document_url`, `document_type`, `language` default `en`, integer `version` default 1, `retrieved_at`, `published_at`, `content_hash`, `processing_status`, timestamps.
* **Relationships:** source, optional scheme, contents (cascade delete), rule provenance rows.
* **Constraints/indexes:** unique `(source_id, document_name, version)`; indexes on source and scheme FK. The database does **not** enforce the documented SHA-256 length or status/document-type values.
* **Assessment:** this is closest to a raw snapshot record. It needs an immutable retrieval identity and URI/canonical URL policy, MIME type/charset/byte size/HTTP status/ETag/Last-Modified/request metadata, source-observed update time, binary-object reference, retrieval outcome/error, and a document-level logical identity separate from each snapshot. Its current unique key can collide for two different URLs with the same name/version and does not prevent reusing a content hash.

### `tbl_scheme_source_content` (`SchemeSourceContent`)

* **Purpose:** preserves `RAW`, `NORMALIZED`, and `EXTRACTED_TEXT` textual content variants for a source document.
* **PK/FK:** `content_id` UUID; required `source_document_id` -> source document (`CASCADE`).
* **Columns:** constrained `content_type`, `raw_content`, `normalized_content`, language, `processing_status`, `extraction_version`, `retrieved_at`, timestamps.
* **Constraints/indexes:** `ck_scheme_content_type`; unique `(source_document_id, content_type, language)`; index on document FK.
* **Assessment:** supports text audit trails, but a PDF/API JSON/HTML byte stream cannot reliably be represented by text columns alone. Store raw bytes in durable object storage (or an explicitly bounded binary store), record object URI/content digest/MIME on the snapshot, and keep this table (or a successor) for textual derivatives. The unique variant key also prevents retaining multiple extraction-pipeline outputs for the same language without overwriting/replacing a record.

### `tbl_scheme_rule_provenance` (`SchemeRuleProvenance`)

* **Purpose:** links a published structured rule to source text and document; this is existing scheme-rule evidence, not citizen-document evidence.
* **PK/FKs:** `rule_provenance_id` UUID; `rule_id` -> eligibility rule (`CASCADE`); source document -> source document (`RESTRICT`).
* **Columns:** `source_text`, `source_page`, `source_section`, `source_reference`, `extraction_method`, numeric `extraction_confidence`, `verification_status`, `verified_at`, `created_at`.
* **Indexes:** rule and source-document indexes. No uniqueness constraint, allowing multiple evidence entries per rule.
* **Assessment:** reuse for published rules after versioning is in place. Add immutable content reference/variant ID, start/end text offsets or stable selector, quote hash, extraction run/candidate link, reviewer/review rationale, and constraint/validation of status/confidence. It cannot evidence an unsupported candidate because it requires a published rule ID.

### `tbl_scheme_ingestion_run` (`SchemeIngestionRun`)

* **Purpose:** one future ingestion attempt against a source.
* **PK/FK:** `ingestion_run_id` UUID; required `source_id` -> source (`CASCADE`).
* **Columns:** start/completion time, `status` default `RUNNING`, discovered/created/updated/failed counters, `error_summary`, created time.
* **Constraints/indexes:** index on source; no status check or run-level idempotency/configuration/content snapshot.
* **Assessment:** keep as an operational run log, but it needs adapter type/version, trigger, actor, request/configuration snapshot, run outcome timestamps, immutable item-level result/error records, and a link to produced candidate batches. `records_updated` must not mean an in-place update of a published scheme.

## 5. Existing rule model and eligibility engine

### Evaluation path as implemented

```text
active SchemeMaster
  -> ordered SchemeRuleGroup(s)
    -> ordered SchemeEligibilityRule(s)
      -> EligibilityEngine._resolve_parameter(citizen, parameter_name)
        -> EligibilityEngine._apply_operator(actual, operator, required_value)
          -> bool per rule -> bool per group -> bool per scheme
            -> evaluation_details JSON + reason
              -> eligibility_result Boolean persisted in EligibilityAssessment
```

`POST /api/v1/eligibility/evaluate/{citizen_id}` gets a citizen with the three legacy profiles plus all profile facts, queries every scheme whose `status == "ACTIVE"`, evaluates each one in Python, and upserts one row per `(citizen_id, scheme_id)`. The upsert currently sends only `eligibility_result`, `reason`, and `evaluation_details`.

### Exact supported facts/parameters

The engine supports these parameter names only: `age`, `gender`, `citizen_type`, `annual_income`, `poverty_category`, `land_holding_size`, `is_bpl_card_holder`, `is_income_tax_payer`, `employment_status`, `social_category`, `education_level`, `disability_status`, `area_type`, and `state`.

`age` first uses an open `ProfileFact` with `fact_code == AGE`, parses it as an integer, and otherwise calculates age from `CitizenMaster.date_of_birth`. The others are read directly from identity or legacy demographic/financial/location profiles. Most normalized Phase 2 facts and domain tables—including district, pincode, occupation, structured education/employment/agriculture/disability data, family members, assets, document-possession facts, and derived `SENIOR_CITIZEN`, `MINORITY_STATUS`, `WIDOW_STATUS`, `SELF_EMPLOYED`, tenancy flags—are **not** consumed by the engine today.

### Operators, data types, and semantics

* Supported operators: `<`, `<=`, `>`, `>=`, `==`, `!=`, `IN`.
* `IN` expects a comma-separated string and uses exact string membership after trimming list values. It does not type-coerce its list.
* Required values are strings. For Boolean actual values, `true`, `1`, and `yes` mean true; for integer/float actual values the requirement is parsed numerically. Parse failure produces false.
* Only runtime Python types determine coercion. There is no declared rule `data_type`, amount currency, land-area unit, date type, or fact registry lookup.
* Rules inside a group use `intra_group_operator == "AND"` for `all`; every other value is treated as OR. Groups use the same pattern through `group_combining_operator`.
* Empty groups pass; a scheme with no groups passes. Group/rule priority orders display/evaluation but does not short-circuit.
* Any `None` actual fails. Unknown parameters log a warning and return `None`, therefore also fail. There is no separate unsupported-rule state.
* Failures are collected from **all** failed rule leaves, including a failed leaf in an OR group that itself passed. The resulting reason may therefore overstate exclusions.
* Rule descriptions and raw actual/required/operator/passed values form the per-rule explanation. There is no fact provenance, source-rule evidence, document check, engine version, rule version, or decision-time timestamp in the runtime result.

### Current gaps relevant to automatic ingestion

The engine has no explicit exclusion semantics, dates/window checks, geography below state/area type, document checks, units/currencies, quantifiers for family members, rule-effective dates, or nested expression support. It equates unavailable information with a failed rule; it does not distinguish known false from unknown, so automatic ingestion must not send unsupported/missing facts into published runtime rules until a tri-state evaluator exists.

`EligibilityAssessment` already defines `ELIGIBLE`, `NOT_ELIGIBLE`, `POTENTIALLY_ELIGIBLE`, and `INSUFFICIENT_INFORMATION`, plus `missing_facts`, `missing_documents`, `confidence_score`, and `assessment_version`. These were added in migration `0003` and covered by an ORM test, but they have no database check and are unused by the evaluator, repository upsert, schemas, or endpoints. The existing unique assessment row also overwrites historical results and ties to a mutable scheme row.

## 6. Existing document model

The scheme-side document catalogue is described in section 3. It represents only a generic required/optional list. It has no upload, storage, verification, or citizen-evidence model. The profile registry can normalize possession flags such as `HAS_AADHAAR`, `HAS_RATION_CARD`, `HAS_INCOME_CERTIFICATE`, `HAS_CASTE_CERTIFICATE`, `HAS_DOMICILE_CERTIFICATE`, `HAS_BONAFIDE_CERTIFICATE`, `HAS_MARKSHEET`, `HAS_LAND_RECORDS`, and `HAS_BANK_ACCOUNT`, but the eligibility engine neither reads them nor links them to `SchemeDocumentMaster`.

`ProfileFactProvenance.document_id` is deliberately an unconstrained UUID placeholder for a future citizen document store; it is not a link to `tbl_scheme_document_master` or a source document. Thus scheme evidence and citizen application evidence remain correctly separate but neither is complete.

## 7. Existing scheme API, repositories, and services

* `GET /api/v1/schemes/`: returns all `ACTIVE` master rows using `SchemeResponse` (which exposes only pre-Phase-1 public fields).
* `GET /api/v1/schemes/{scheme_id}`: returns a scheme plus groups/rules/documents. It does not expose Phase 1 source fields, source documents, rule provenance, or a scheme version.
* `SchemeRepository`: only `get_all_active` and `get_by_id`; both use `selectinload` for groups/rules/documents. It has no pagination, filter, source, version, or candidate query.
* `SchemeService`: a pass-through wrapper around that repository.
* `POST /api/v1/eligibility/evaluate/{citizen_id}`: evaluates all active schemes and persists one assessment each.
* `GET /api/v1/recommendations/{citizen_id}`: returns already-stored assessments split by legacy Boolean into eligible/ineligible lists. It does no ranking/recommendation calculation.

No API exposes source registration, retrieval, ingestion runs, snapshots, extraction, candidate metadata/rules, validation, review, publication, diffs, or rule evidence. No source-ingestion repository/service exists.

## 8. Existing seed data analysis

`backend/seed_data/schemes.json` contains seven manually maintained seed schemes. `backend/scripts/seed.py` constructs master/groups/rules/documents directly; it ignores `start_date`, `last_verified_at`, `target_persona`, diagnostic fields, and all Phase 1 source/version fields even when the JSON contains them. It checks neither scheme name nor code despite its comment saying it skips existing rows; it inserts every run and does no deduplication.

| Scheme | Structured metadata and rules | Documents | Known dates/URLs | Missing/unstructured observations |
| --- | --- | --- | --- | --- |
| PM Kisan Samman Nidhi (PM-KISAN) | Agriculture; ministry; benefit text; `citizen_type=FARMER`, `land_holding_size<=2.0`, tax-payer false | Aadhaar, land record, bank passbook (all required) | Start `2019-02-24`; official and application URLs | No scheme code; geography/free-text applicability; no stored source record or evidence. |
| PM Awas Yojana Gramin (PMAY-G) | Housing; ministry; BPL/AAY and rural rules | Aadhaar, bank passbook, BPL card | Official URL only | No start/application/verification date, rule source, geography beyond `RURAL`. |
| NSP Post-Matric Scholarship for SC Students | Education; ministry; SC, post-matric proxy education set, income cap | Aadhaar, caste certificate, income certificate, marksheet | Official URL only | No window/date, institution/course detail, source evidence, application URL. |
| Indira Gandhi National Old Age Pension (IGNOAPS) | Pension; ministry; age >=60, BPL/AAY | Aadhaar, BPL card | Official URL only | Benefit tiers are free text, not structured; no dates/app URL/evidence. |
| PM Ujjwala Yojana 2.0 (PMUY) | Energy; ministry; female, age >=18, BPL/AAY | Aadhaar, BPL card, ration card | Official URL only | No dates/app URL/evidence; BPL is a rule proxy rather than proven card category. |
| Ayushman Bharat PM-JAY | Healthcare; National Health Authority; BPL/AAY proxy | Aadhaar, ration card | Official URL only | Text explicitly calls the rule a proxy for SECC criteria; this cannot be treated as authoritative imported eligibility. |
| PM SVANidhi | Employment; ministry; self-employed proxy and income cap | Aadhaar, bank passbook | Official URL only | Both rules are described as proxies/typical targets, not verified official rule representations; no dates/app URL/evidence. |

Across all seven entries, name, department, category, description, benefit description, status, official source URL, group/rule tree, and document type/mandatory flag are structured JSON. Eligibility descriptions/remedies, benefits, and much operational scheme information are free text. Rules/documents are hardcoded in a seed file. AGE is derived from DOB; the other current rule values are read from profile data. No seed entry has `official_scheme_identifier`, registry source linkage, source snapshot, content hash, scheme version lineage, raw source material, provenance, publishing/review record, rule effective dates, or document verification data. Only PM-KISAN has `start_date` and `application_url`; although the JSON supplies `last_verified_at` and `target_persona` for all/most entries, the current seed script does not persist them.

## 9. Existing tests and migrations

The migration chain is exactly `0001_initial_schema -> 0002_persona_and_diagnostics -> 0003_phase1_database_foundation`. `0003` is additive and creates the source/content/provenance/run tables, profile/domain tables, and the richer assessment columns.

Relevant coverage:

* `test_eligibility_engine.py` checks one eligible PM-KISAN-shaped Boolean evaluation.
* `test_age_consistency.py` checks AGE derivation, fallback, and that unavailable age currently causes a Boolean failure.
* `test_phase1_foundation.py` ORM-smoke-tests creating a source, document/content variants, rule provenance, ingestion run, and assessment status fields. It does not execute ingestion.
* `test_phase2b_normalization.py` checks typed facts/provenance, derived AGE, unmapped data reporting, and other profile normalization.
* API/form tests cover existing citizen/form flows, not source ingestion/publishing.

There are no tests for source-change detection, source uniqueness/canonicalisation, content hashes, adapters, parser/extractor output, candidate validation, review, publishing, scheme version selection, evidence offsets, automatic eligibility-rule generation, document verification, tri-state runtime results, or backward-compatible versioned assessment history.

## 10. Exact gaps

1. Existing source tables are passive infrastructure; nothing creates or consumes them in production flows.
2. Published scheme data is mutable and has no stable identity/version split.
3. `SchemeMaster.scheme_version` alone cannot retain historical rules or explain which source version produced a decision.
4. There is no candidate layer; an LLM/API/parser would otherwise have to write directly to published scheme/rule tables.
5. The rule DSL is stringly typed, uses a hard-coded resolver, lacks unit/date/evidence/status fields, and has no formal fact registry contract.
6. Unsupported/ambiguous extraction cannot be represented safely.
7. Missing citizen data returns false rather than `UNKNOWN` despite prepared assessment fields.
8. Required documents are informational only; no rule linkage or citizen evidence/verification exists.
9. Source content preservation is text-only and lacks binary-object/HTTP metadata and immutable extraction-version variants.
10. Source authority/precedence and publisher/jurisdiction language metadata are insufficient for a registry at scale.
11. Scheme API responses omit source/version/evidence information and repositories load all active schemes without pagination/filtering.
12. Seed data includes two explicitly proxy/typical rule descriptions, demonstrating why ingestion must retain source evidence and review rather than treating text as truth.

## 11. Proposed target architecture

```text
Official source registry (existing SchemeSource, extended)
  -> immutable raw snapshot (extend SchemeSourceDocument + content/object reference)
    -> extraction artifact (extend SchemeSourceContent; versioned output)
      -> candidate scheme / candidate version (NEW)
        -> candidate groups, rules, document requirements (NEW)
          -> evidence references (extend provenance / NEW candidate evidence)
            -> automated validation + review (NEW)
              -> immutable published scheme version (NEW, becomes runtime target)
                -> deterministic eligibility engine (extend; never LLM-decided)
                  -> versioned tri-state eligibility result
                    -> future recommendation/ranking layer
```

LLM/NLP/API parsing may create **candidate** structured metadata/rules and confidence metadata. Only validated and published canonical rules become evaluable. Extraction confidence never changes a citizen's eligibility outcome.

## 12. Source registry design

Reuse `tbl_scheme_source`; do not create a duplicate registry. In a later migration, minimally add a durable canonical source identity (`canonical_base_url` or equivalent), `publisher_name`, `publisher_jurisdiction`, `authoritative_status` and `authority_basis`, default language, precedence/priority, `status_reason`, and source retrieval configuration reference. Preserve `source_name` as display name, not identity.

Source type should retain existing canonical values and add `MANUAL_ADMIN` only if manual entry is intentionally treated as an adapter/source. A source status needs a controlled lifecycle such as enabled, paused, retired, blocked; "official" must be explicit and reviewable rather than inferred solely from a `.gov` hostname.

Do not store secrets/API keys in this table. Store a secret reference in platform configuration and capture only a redacted configuration/version identifier on each run.

## 13. Raw snapshot design

Use `tbl_scheme_source_document` as the retrieval snapshot record but distinguish a logical source resource from a retrieved immutable snapshot. The minimum extension can either add a logical-resource key and snapshot sequence to the existing table or add a small `scheme_source_resource` parent table; choose the latter only if a single government endpoint commonly yields multiple independently versioned resources.

Each snapshot should retain: source ID; requested/canonical URL; retrieval timestamp; source-published and source-last-updated time when observed; SHA-256 of exact bytes; MIME type, charset, byte length; HTTP status, ETag, Last-Modified, and selected safe headers; raw-object URI/key; retrieval outcome; and parser/extraction version. Raw bytes must be immutable and content-addressed/deduplicated in object storage; HTML/JSON/plain text may additionally be preserved in `tbl_scheme_source_content`, while PDF bytes must not be coerced into `Text`.

For evidence, an extracted content artifact needs a stable content-variant ID, page number for PDFs, heading/section or DOM/JSON selector, optional start/end character offsets, exact quote/snippet, and quote/content hash. Never overwrite a raw snapshot or silently replace an extracted artifact; a new retrieval or extractor produces a new row/version.

## 14. Evidence design

Retain `tbl_scheme_rule_provenance` as published-rule evidence. Extend it or introduce a generic evidence-reference table that can attach the same immutable locator to a candidate metadata field, candidate group/rule/document requirement, validation finding, and published rule. The reference must point to a source snapshot/content variant—not merely a mutable URL—and contain the exact source quote plus locator metadata.

One rule may have several supporting or conflicting evidence references. Evidence status should be reviewed independently of extraction confidence. A rule with no adequate evidence must block publication or be explicitly retained as `UNSUPPORTED`, never dropped.

Citizen evidence is a separate later model: it should record a citizen-owned document/verification artifact and attach it to a `document_requirement` and/or fact provenance. Do not reuse government source document rows for citizen uploads.

## 15. Scheme versioning design

The target needs a stable logical scheme and immutable published versions:

```text
Scheme identity (stable official identifier + authority)
  -> Scheme version 1 (rules/documents/metadata/source snapshot)
  -> Scheme version 2 (new source snapshot; supersedes v1)
  -> Scheme version 3
```

Recommended future shape:

* retain `tbl_scheme_master` temporarily as the public/current compatibility record, then evolve it into stable scheme identity or add `tbl_scheme_version` with an explicit FK to it;
* every rule group, rule, document requirement, and source linkage belongs to a `scheme_version_id`, not merely a mutable master row;
* a published version is immutable; a changed source produces a candidate version, validation/review, then a new version; it never updates old published rules;
* include `version_number`, lifecycle status, `published_at`, `publication_date`, `effective_from`, `effective_to`, `superseded_by_version_id`, source snapshot/batch, and change summary/diff.

Keep three concepts distinct: **scheme validity** (`effective_from/to`), **application window** (open/close range and recurring/window policy), and **rule validity** (rule/group effective range). A source publication date is evidence metadata, not necessarily any of those dates.

Existing `scheme_version`, `start_date`, `end_date`, and `application_window_type` can be mapped forward but cannot supply this history by themselves. Existing active seed rows should migrate as version 1 with an explicit legacy/manual provenance, rather than manufacturing official evidence.

## 16. Canonical rule DSL

The existing leaf (`parameter_name`, operator, string required value) is the v0 basis. The future published canonical leaf should at minimum declare:

```json
{
  "fact_code": "ANNUAL_HOUSEHOLD_INCOME",
  "operator": "LTE",
  "value": 300000,
  "data_type": "DECIMAL",
  "unit": "INR_PER_YEAR",
  "requirement_type": "ELIGIBILITY",
  "effective_from": "2026-04-01",
  "evidence_refs": ["..."],
  "status": "SUPPORTED"
}
```

This is illustrative, not a mandate to store JSON instead of normalized columns. Groups should retain explicit AND/OR; introduce `NOT`/exclusion as an explicit typed predicate or group rather than encoding it only in rule prose. Values must be typed canonical data, not arbitrary strings. A fact registry determines valid fact code, data type, cardinality, unit/currency conversion, source policy, and resolver.

Required capability mapping: numeric/categorical/Boolean and age are partly supported today; income and state/area type are partly supported; date comparisons, district/local-body geography, household aggregation/relationships, occupation, detailed education/agriculture/disability/assets, document requirements, windows, explicit exclusions, and most derived facts are not safely supported at runtime. The profile registry already provides a strong starting list of canonical citizen facts; a separate published fact-definition registry is needed before general ingestion.

## 17. Natural-language rule extraction contract

Each parser/LLM output must create a candidate record, never `SchemeEligibilityRule` directly. A candidate rule/requirement must retain: original text; snapshot/content locator and quote; extraction method/model/prompt or parser version; confidence; candidate status; validation state/findings; normalized proposed structure; unresolved terms; and reviewer decision/rationale.

For example, "resident of Maharashtra and annual family income should not exceed Rs 3 lakh" can produce two candidate AND leaves only after the extractor resolves authoritative terms and units. Confidence is triage metadata. It is not an operator, a threshold, or a substitute for a fact. Ambiguous text such as "deserving families" or a rule that references an unavailable certificate category must remain an explicit `UNSUPPORTED`/`NEEDS_REVIEW` candidate with its evidence; it must not vanish from the candidate scheme.

## 18. Validation pipeline

```text
candidate batch
  -> schema validation
  -> fact registry + data-type/operator/unit validation
  -> evidence locator/quote/hash validation
  -> semantic checks (contradictions, dates, group completeness)
  -> automated policy checks
  -> human/system review
  -> publish immutable version
```

Automatic checks can validate required fields, UUID/FK relationships, enum membership, numeric/date parsing, compatible fact/operator/data type, known unit conversions, all evidence locators resolving inside the immutable extracted content, quote-hash consistency, duplicate rules, impossible ranges, and no unresolved `UNSUPPORTED` leaf in a publishable path.

Review must decide ambiguous legal/administrative meaning, whether a source is authoritative/current, mapping of government terminology to fact codes, proxy acceptability, hierarchy/conflict between documents, complex exclusions, document requirements, and extracted change significance. Publication must be blocked by malformed evidence, unknown fact code, incompatible operator/type/unit, missing source snapshot, unresolved required candidate rule, unreviewed policy-required change, or contradictory mandatory rules. `UNKNOWN` is a runtime result for missing citizen evidence; `UNSUPPORTED` is a scheme-definition state and should block a deterministic eligibility claim.

## 19. Publishing lifecycle

Existing statuses are not sufficient: source status is `ACTIVE/INACTIVE/RETIRED`, scheme master status is `ACTIVE/INACTIVE/EXPIRED`, source-document processing is `PENDING/PROCESSING/PROCESSED/FAILED`, and run status is `RUNNING/COMPLETED/FAILED/CANCELLED`. Preserve those meanings rather than overloading them.

Use a candidate-version lifecycle such as `DISCOVERED -> FETCHED -> EXTRACTED -> VALIDATION_FAILED | REVIEW_REQUIRED -> VALIDATED -> PUBLISHED -> SUPERSEDED | ARCHIVED`. `PUBLISHED` is the only state visible to deterministic runtime evaluation. A validation failure should retain evidence and findings. Published historical versions remain readable after supersession; `ARCHIVED` does not erase them.

## 20. Unsupported and UNKNOWN requirements

The desired runtime contract is three-valued:

* `ELIGIBLE`: every required evaluable condition is true and no exclusion is true.
* `NOT_ELIGIBLE`: a required evaluable condition is known false or an exclusion is known true.
* `UNKNOWN`: no known disqualifier exists, but a required fact/document/verification is unavailable, stale, unsupported for the runtime DSL, or otherwise cannot be determined.

Current behavior returns false for absent values and unknown parameter names, which conflates `NOT_ELIGIBLE` and `UNKNOWN`. The existing assessment columns `eligibility_status`, `missing_facts`, and `missing_documents` are the natural compatibility starting point. In a later phase, extend the engine to return typed rule outcomes (`PASS`, `FAIL`, `UNKNOWN`, `UNSUPPORTED`), apply three-valued AND/OR logic, populate assessment status/evidence, and update the API/schema/recommendations. Do not do this in Phase 3A.

For the ration-card example, a missing `RATION_CARD_CATEGORY` fact must yield an `UNKNOWN` requirement result and list that fact/document need, not false. Unsupported rules should never reach publishable engine input; if legacy data requires them to coexist, the scheme/version must be marked not fully deterministically assessable and return `UNKNOWN`, with the unsupported evidence visible.

## 21. Future document architecture

Keep `tbl_scheme_document_master` as the eventual predecessor of versioned `document_requirement` records. A requirement needs type, mandatory/optional/alternative relationship, applicable rule/group, description, issuing authority, accepted evidence types, validity/expiry/verification policy, effective dates, provenance, and version status. A citizen-evidence layer then records submitted/linked proof, secure storage reference, hashes, extraction/verification result, issuer/date/expiry where appropriate, and fact links. The rule can require a document, a verified document fact, or both—these must be distinct.

No full upload/verification system is part of this phase.

## 22. Geography architecture

Today, citizen location contains free-text `state`, `district`, `village_city`, and `area_type`; the engine reads only `state` and `area_type`. Schemes have no structured geographic scope. Use a canonical geography reference hierarchy (India -> state/UT -> district -> local body/region/constituency) and versioned scheme geography applicability records with `include/exclude`, level, canonical code, and evidence. Retain human-readable labels for display. Do not introduce GIS, Mapbox, or QGIS here. Geographic evaluator support should be introduced only alongside canonical codes and an explicit missing/unknown policy.

## 23. Change detection

For each retrieval, canonicalise the source resource URL, preserve its raw snapshot, compute a content hash over exact bytes, and compare both hash and meaningful HTTP/source metadata to the latest snapshot. A changed hash, relevant metadata change, or source update indication creates a new snapshot and candidate version; it never mutates the published version. A structured metadata/rule diff should compare normalized candidate data with the latest published version and present the evidence/field/rule changes to review.

Equivalent content at a new URL should still be preserved as a retrieval event but may deduplicate the byte object by hash. Identical content should record successful observation without producing a candidate scheme revision. Never treat a retrieval failure as proof a government scheme is expired.

## 24. Ingestion adapter architecture

All future adapters should implement one normalized boundary, for example:

```text
discover(source configuration) -> resource references
fetch(resource) -> immutable snapshot + retrieval metadata
extract(snapshot) -> versioned normalized/extracted content artifacts
propose(artifacts) -> candidate schemes/rules/documents/evidence, never published rules
```

* **Government API:** preserve request-safe metadata, response bytes/JSON, pagination/cursor and API version; map records to candidates with JSON-path evidence.
* **HTML/web page/portal:** preserve HTML bytes, canonical URL, HTTP metadata and DOM/heading/text selectors.
* **PDF:** preserve original bytes; extract page-addressable text/OCR artifacts and page/coordinate or character-span evidence.
* **JSON:** preserve raw response plus normalized JSON; evidence uses JSON Pointer/path and quote/value hash.
* **Manual/admin:** capture author/role, timestamp, input form/version, attestations and attached source evidence; it follows the same candidate/validation/review/publish flow and never bypasses it.

Adapters should be idempotent for the same source resource/content digest, emit structured item-level results to the ingestion run, and not make eligibility decisions.

## 25. Scale considerations

At 10 schemes, the current all-active query and in-process loop are adequate. At 100, they remain workable but require pagination/cache discipline for catalogue endpoints and query instrumentation. At 1,000, loading every scheme/rule/document for every citizen evaluation, sequential Python evaluation, and one assessment upsert per scheme become material; evaluate prefiltered candidate sets and batch/paginate deliberately. At 10,000+, version-aware filtering, fact/rule indexes, work queues, partitioning/retention for snapshots and assessments, object storage for content, asynchronous extraction, bounded API responses, and review workflows become necessary.

Risks are not just performance: raw PDF/HTML storage can grow rapidly; source hashes need indexes/deduplication; versioned rules multiply rows; evidence joins can be expensive; and the current `UNIQUE(citizen_id, scheme_id)` assessment model loses version/time history. Do not prematurely denormalize or introduce search/vector infrastructure; first build clear source, version, and lifecycle boundaries.

## 26. Future testing strategy

Create fixtures for a small official API JSON payload, a saved HTML page, a two-page PDF with page-specific eligibility text, changed/unchanged snapshots, conflicting official documents, an ambiguous rule, and citizens with present/missing/verified facts/documents.

Tests should cover:

* source registry validation, adapter idempotency, fetch errors, content hashes, metadata capture, and raw snapshot immutability;
* HTML/PDF/JSON extraction with stable evidence locators and quote/hash verification;
* candidate schema, fact/operator/type/unit validation, unsupported-rule retention, and semantic contradictions;
* review decision/audit trail, publish blockers, immutable publication, supersession, and rollback/archival visibility;
* source/rule/metadata change detection including a byte-identical retrieval and a changed source URL;
* deterministic rule evaluation for all supported DSL types, explicit exclusions, dates/geography/documents, and tri-state AND/OR cases;
* `UNKNOWN` for missing fact/document and `UNSUPPORTED` scheme definitions; never silently false;
* source-to-rule evidence and citizen-evidence separation;
* migration from seven legacy seed rows into baseline version 1 with no invented official provenance;
* compatibility of current scheme detail, eligibility, recommendation, and form/profile API behaviour during staged rollout.

## 27. Migration strategy

Use additive, reversible migrations as `0003` did. First introduce candidate/review/version tables and indexes without changing current endpoints. Backfill each existing master scheme as a manually seeded legacy baseline version only after an explicit migration plan; preserve source URLs as unverified references, not authoritative snapshot evidence. Keep legacy master/rule/document readers working through a compatibility projection or current-published-version view. Introduce tri-state assessment fields in runtime only after data/API migration and backfill policy are approved. Do not delete existing rule rows or repurpose `scheme_id` in place until all consumers are version-aware.

## 28. Existing table -> future architecture mapping

| Existing table | Future role | Required direction |
| --- | --- | --- |
| `tbl_scheme_master` | Stable scheme identity/current compatibility projection | Extend or introduce version child; stop mutating published rules in place. |
| `tbl_scheme_rule_group` | Published version expression group | Move/attach to scheme version; add explicit type/status/effective period as needed. |
| `tbl_scheme_eligibility_rule` | Published canonical leaf rule | Extend/migrate to typed fact DSL with version/evidence links. |
| `tbl_scheme_document_master` | Published document requirement precursor | Version it and support rule association/evidence policy. |
| `tbl_scheme_source` | Source registry | Extend authority, identity, policy, language, precedence. |
| `tbl_scheme_source_document` | Logical resource/retrieval snapshot precursor | Preserve immutable bytes/HTTP metadata and strengthen logical identity/versioning. |
| `tbl_scheme_source_content` | Extracted/normalized text artifact | Keep textual variants; add binary object ref and extraction artifact version history. |
| `tbl_scheme_rule_provenance` | Published-rule evidence | Extend locator/reviewer/version links; add candidate equivalent/generic reference. |
| `tbl_scheme_ingestion_run` | Operational ingestion-run log | Add adapter/config/batch/item outcome audit. |
| `tbl_profile_fact` + registry | Citizen fact source/validator input | Formalize a fact-definition registry for rule validation and resolution. |
| `tbl_profile_fact_provenance` | Citizen fact provenance | Keep separate from scheme-source evidence. |
| `tbl_eligibility_assessment` | Versioned result/evidence record | Make scheme-version aware and populate tri-state fields; retain legacy compatibility initially. |

## 29. Proposed new tables/columns only where genuinely necessary

Necessary additions for the target design, deferred to implementation planning:

1. **NEW `scheme_version` (or equivalent version child):** immutable version identity, scheme FK, number/status/effective/publication/supersession/source-batch/diff metadata. This is necessary because current `scheme_version` scalar cannot preserve historical rule sets.
2. **NEW candidate batch/version/group/rule/document requirement records:** isolate extraction from published runtime data and retain unsupported/ambiguous candidates.
3. **NEW validation finding and review decision/audit records:** validation/review needs durable, attributable decisions, not a single status string.
4. **NEW ingestion item/result record:** `SchemeIngestionRun` counters cannot explain an individual resource/candidate error or retry/idempotency result.
5. **NEW/extended source snapshot binary metadata:** object key/URI, MIME/size/HTTP metadata and canonical resource identity are necessary to preserve PDFs and audit retrievals.
6. **NEW generic candidate evidence reference or extended provenance:** candidate rules need evidence before a `rule_id` exists; locators need immutable content variant and offsets/hash.
7. **NEW fact-definition registry:** typed source of truth for fact code/data type/unit/cardinality/resolver support is required before generic rule validation.
8. **NEW versioned document requirement and later citizen-evidence records:** necessary for rule-to-document-to-citizen-evidence linkage.
9. **Extend assessment with scheme-version linkage/history strategy:** necessary to say which published scheme version produced a result. This may be a new assessment-run/history table if the current one-row upsert remains the "latest" projection.
10. **NEW scheme geography applicability/reference records:** necessary for clean state/district/local-body inclusion/exclusion without GIS.

Fields already present and to reuse where suitable: `official_scheme_identifier`, source URL/type/name, application window type/end date, scheme version number, update/verification timestamps, source/document content hash, language/retrieval/published dates, source text/page/section/reference, extraction method/confidence, verification status, and assessment missing-fact/document/status fields.

## 30. Recommended implementation phases after 3A

1. **3B — source/snapshot hardening:** source registry extension, immutable raw snapshot/object storage contract, ingestion-run/item audit, no rule publication.
2. **3C — candidate extraction and evidence:** adapter interface with one controlled source type first; candidate metadata/rules/documents, evidence locators, validation findings; no direct writes to published rules.
3. **3D — version/review/publish:** immutable scheme versions, review workflow, source/rule diffs, compatibility projection for current APIs.
4. **3E — deterministic DSL/runtime evolution:** fact registry, typed rules, three-valued engine, dates/geography/documents as deliberately supported capabilities, scheme-versioned results.
5. **3F — scale and operations:** queues/scheduling, change detection, source health, indexes/retention/pagination, observability.
6. **3G — recommendation:** build ranking/relevance strictly downstream of published eligibility results.

## 31. Risks and open questions

* Confirm which government authorities and jurisdictions are in scope and what policy establishes "authoritative" status.
* Obtain legal/operational rules for source access, rate limits, robots/terms, PDF retention, and storing personally sensitive citizen evidence.
* Define owner/reviewer roles, required dual review, publication authority, correction/rollback procedure, and SLA for source changes.
* Define canonical geography codes and terminology mappings per state/UT before adding geographic rules.
* Decide which fact sources satisfy a rule (self-declared vs document-verified vs government verified) and how freshness/expiry affects `UNKNOWN`.
* Resolve the current seed's proxy/typical rules before representing them as officially published eligibility; provenance must make the distinction visible.
* Define unit/currency rules, household membership/aggregation policy, and rule semantics for conflicting source documents.
* Decide source-content object storage, encryption/retention, content-addressing, and access-control boundaries before storing raw PDFs/HTML.
* Decide whether currently stored assessments are a latest-result cache, audit history, or both; this controls the versioned assessment migration.

## Final architecture boundary

```text
ALL PUBLISHED SCHEME VERSIONS
  -> deterministic eligibility evaluation
    -> ELIGIBLE | NOT_ELIGIBLE | UNKNOWN
      -> future recommendation/ranking
```

Recommendation may prioritize or explain relevant schemes; it must never create, suppress, or alter an eligibility outcome. LLM/NLP extraction remains upstream in the candidate/review workflow and is never an eligibility decision-maker.

---

STATUS: PHASE 3A AUDIT COMPLETE  
CODE CHANGES: NONE  
DATABASE CHANGES: NONE  
MIGRATIONS: NONE
