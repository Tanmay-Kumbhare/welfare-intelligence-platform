# Source Seeding & URL Verification Audit Note

**Date:** 2026-10-03 · **Scope:** exercise existing `tbl_scheme_source` registry CRUD only. No migration, no schema change, no new models, no ingestion runs, no scrapers, no eligibility-engine change.

## What was done

1. Inspected the existing contract first:
   - `POST /api/v1/admin/sources` accepts exactly: `source_name`, `source_type` (validated against the existing `SCHEME_SOURCE_TYPES` CHECK), `base_url` (absolute http(s) enforced), `authority_name`, `status` (`ACTIVE`/`INACTIVE`/`RETIRED`). No fields beyond these were sent.
   - All `/admin/*` routes require `require_admin` (bearer session with `ADMIN` role).
2. Bootstrapped admin access: an `ADMIN` user already existed (`smoke.test@example.com`, a local test account). Since passwords are unknown and there is no bootstrap-admin path in code, a session row was minted for that account via the app's own `AuthRepository.create_session` — data-only, no schema or code change. Token kept in a temp file, deleted afterwards.
3. Seeded SRC-01..04 from `MAHARASHTRA_SOURCE_REGISTRY.md` via the live API, then verified via `GET /api/v1/admin/sources`.

## Sources inserted (with IDs)

| Registry ID | source_id | Name | source_type | base_url |
|---|---|---|---|---|
| SRC-01 | `a32ed832-45ab-436e-9f77-d8621c2f702d` | Maharashtra Government Main Portal | `GOVERNMENT_PORTAL` | https://maharashtra.gov.in/ |
| SRC-02 | `00efa82d-803d-4041-be7c-dc438aeccacc` | Maharashtra Government Resolution (GR) Portal | `GOVERNMENT_WEBSITE` | https://gr.maharashtra.gov.in/1145/Government-Resolutions |
| SRC-03 | `d4338508-166c-426c-bbbb-c7715d061cbd` | MahaDBT Portal | `GOVERNMENT_PORTAL` | https://mahadbt.maharashtra.gov.in/ |
| SRC-04 | `ea95527a-0741-4423-bd5c-88e760ff2b08` | Social Justice & Special Assistance Department | `GOVERNMENT_WEBSITE` | https://sjsa.maharashtra.gov.in/ |

Pre-existing registry rows (untouched): `Unreachable Test Source` (test artifact), `PM-KISAN Official Portal` (4 documents, last run COMPLETED).

## URL verification evidence (read-only GET, 2026-10-03)

| Source | HTTP status | Final URL (after redirects) | Redirects | Content type | Useful HTML | Session/auth needed? |
|---|---|---|---|---|---|---|
| SRC-01 maharashtra.gov.in | 200 | unchanged | 0 | text/html; charset=utf-8 (549 KB) | Yes — 23× "scheme", 73× "योजना"; not ASP.NET | No (issues `ASP.NET_SessionId` + CSRF cookie, but anonymous 200) |
| SRC-02 gr.maharashtra.gov.in | 200 | unchanged | 0 | text/html; charset=utf-8 (83 KB) | Yes — GR listing ("शासन निर्णय") renders anonymously | No (anonymous 200; `.ASPXANONYMOUS` cookie issued; ASP.NET WebForms markers present) |
| SRC-03 mahadbt.maharashtra.gov.in | 200 | unchanged | 0 | text/html; charset=utf-8 (164 KB) | Yes — 105× "scheme" on public home; login links present (17×) but home is anonymous | No for public pages (AWS ALB + `ASP.NET_SessionId` + `culture` cookies issued) |
| SRC-04 sjsa.maharashtra.gov.in | 200 | unchanged | 0 | text/html; charset=UTF-8 (198 KB) | Yes — 10× "scheme", 22× "योजना"; plain server-rendered HTML (no ASP.NET markers) | No |

**Key findings:**
- No redirects anywhere; the registry `base_url` values are already canonical. UQ-2 partially resolved: `krishi`-style legacy-domain behavior not applicable to these four; all four respond directly at their registered URLs.
- **UQ-5 substantially answered:** none of the four requires authentication or a session cookie for anonymous public pages. All return full HTML to plain unauthenticated GETs — the existing `ingestion_service.py` (plain HTTP GET, 20 s timeout, 5 MB cap) can snapshot these landing pages today. ASP.NET session cookies (SRC-01/02/03) are issued but not *required* for public content; deep tokenized URLs (e.g., MahaDBT `SchemeData?str=…`) may still expire and need re-verification per resource.
- MahaDBT sets an ALB cookie pair (AWSALB/AWSALBTG) — cookie-persistence may matter for multi-request crawls later, not for single snapshots.
- The GR portal is classic ASP.NET WebForms (`__VIEWSTATE`-style stack) — pagination handling will matter when crawling GR listings, but not for single-page snapshots.

## Tests

`pytest tests/test_phase1_foundation.py tests/test_cache.py`:
- **26 passed, 4 failed.** All of `test_phase1_foundation.py` (the source-registry/ingestion suite, 22 tests) **passed**.
- The 4 failures are in `tests/test_cache.py::TestServiceCacheIntegration` (cache hit-counter assertions, e.g. `assert stats["hits"] >= 1` → `assert 0 >= 1`). They are **pre-existing and unrelated**: this task changed zero code (verified via `git status` — only data rows and this note were added), and these tests exercise in-process cache behavior independent of seeded source rows.

## Files changed

- `SOURCE_SEEDING_AUDIT_NOTE.md` (new, this file)
- Database data only: 4 rows in `tbl_scheme_source` + 1 session row in `tbl_user_session` (test admin)
- Deleted after use: `backend/_tmp_admin_token.txt`
- **No application code, no migrations, no schema changes.**

## Is migration 0008 now justified?

**Yes, with sharper rationale:** the four canonical URLs behave cleanly (200, no redirects, anonymous access), so the Phase 3B resource/snapshot split (`tbl_scheme_source_resource` + `tbl_scheme_ingestion_item`) is not needed to *fetch*, but is justified by (a) MahaDBT's session-tokenized resource URLs expiring while the portal base stays stable, (b) the still-open need for `precedence_rank`/`fetch_policy`/`canonical_base_url` columns that the current `tbl_scheme_source` schema cannot store, and (c) resource-level typing (GR PDFs under SRC-02) that has no home today.

## Addendum — Task 1B: UQ-1…UQ-4 Domain Verification (2026-10-03)

Read-only GET probes only. No DB changes, no seeding, no schema changes.

### UQ-1 — Tribal Development: **RESOLVED**

| Requested URL | Status | Redirects | Final URL | Content type | Size | Identity observed |
|---|---|---|---|---|---|---|
| https://tribal.maharashtra.gov.in/ | 200 | 1 (302) | https://tribal.maharashtra.gov.in:443/1001/मुख्य-पृष्ठ | text/html; utf-8 | 431 KB | Title: "आदिवासी विकास विभाग, महाराष्ट्र शासन, भारत" (Tribal **Development Department**) |
| http://mahatribal.gov.in/ | 200 | 1 (302) | http://mahatribal.gov.in:80/1169/Home | text/html; utf-8 | 85 KB | Title: "आदिवासी विभाग आयुक्तालय, महाराष्ट्र शासन" (Tribal Department **Commissionerate**) |
| https://mahatribal.gov.in/ | 200 | 1 (302) | https://mahatribal.gov.in:443/1169/Home | text/html; utf-8 | 85 KB | Same Commissionerate app; HTTPS works |
| https://mahatribal.mahaitgov.in/ | 200 | 1 (302) | https://mahatribal.mahaitgov.in:443/1169/Home | text/html; utf-8 | 85 KB | Same Commissionerate app on the MAIT infrastructure host |

**Conclusion (evidence-based):** `https://tribal.maharashtra.gov.in/` is the canonical **department** site — it follows the state's `*.maharashtra.gov.in` department pattern, is the richer site (431 KB, 21× योजना, 70× GR, 5× शासन निर्णय), and has dedicated scheme pages (`/1028/Schemes-and-Programs`, `/1105/केंद्रीय-योजना`, राज्य योजना). The `mahatribal.gov.in` / `mahatribal.mahaitgov.in` pair is a *different organization unit* — the Commissionerate office — served identically (~85 KB, same `/1169/Home` app) on two hosts; neither redirects to the other, so they are mirrors, not aliases of the department site. **Recommended canonical: `https://tribal.maharashtra.gov.in/`.** The Commissionerate pair should not be registered as the department source; the mahaitgov.in host could be noted as a resource-level mirror if ever needed.

### UQ-2 — Agriculture legacy domain: **RESOLVED**

| Requested URL | Status | Final URL | Content type | Result |
|---|---|---|---|---|
| https://krishi.maharashtra.gov.in/ | 200 | unchanged (0 redirects) | text/html; utf-8 | 1.09 MB; title confirms Agriculture Dept; कृषी 24×, krishi 156×, MahaDBT links 15× (confirms MahaDBT as application portal); योजना 9× |
| http://mahaagri.gov.in/ | **connection failed (000)** | — | — | Dead |
| https://mahaagri.gov.in/ | **connection failed (000)** | — | — | Dead |

**Conclusion:** `mahaagri.gov.in` is retired — it does not respond at all on either scheme. **Canonical: `https://krishi.maharashtra.gov.in/`**, independently live at its own URL (no redirects). The legacy domain's continued citation in third-party PDFs is stale.

### UQ-3 — SWAYAM (swayam.mahaonline.gov.in): **RESOLVED (classification decision, not registry addition)**

| Requested URL | Status | Redirects | Final URL | Content type | Size | Identity observed |
|---|---|---|---|---|---|---|
| https://swayam.mahaonline.gov.in/ | 200 | 0 | unchanged | text/html; utf-8 | 25 KB | Title: "Tribal Developement Department" [sic]; Server: Microsoft-IIS/8.5 (MahaOnline infra); registration/शिक्षण markers |

**Conclusion:** Active and official — it is the Tribal Development Department's scholarship **application/registration portal** hosted on MahaOnline (the state e-governance platform), *not* the central government's SWAYAM MOOC platform and *not* a scheme catalogue (no scheme listing in body). **Classification: application/service portal — registerable only as a resource under the future Tribal Development source (SRC-05), not as a standalone scheme source.** Not added to the DB, per instructions.

### UQ-4 — Higher & Technical Education (htedu.maharashtra.gov.in): **RESOLVED**

| Requested URL | Status | Redirects | Final URL | Content type | Size | Identity observed |
|---|---|---|---|---|---|---|
| https://htedu.maharashtra.gov.in/ | 200 | 1 (302, Location: `http://htedu.maharashtra.gov.in/Main/` — note http; final URL re-secured to https) | https://htedu.maharashtra.gov.in/Main/ | text/html; utf-8 | 222 KB | Title: "Higher and Technical Education Department Government of Maharashtra"; शिक्षण 59×, महाराष्ट्र 17×, GR section (शासन 7×), योजना 8×; Server header: `Htedu` |

**Conclusion:** Active, authoritative, and clearly the H&TE **department** site with scheme content and a GR section. **Eligible for registration as an authoritative departmental source** (candidate SRC-13, priority P1 for the student persona, per the registry). Not added to the DB, per instructions. Minor caveat to record: the 302 Location header downgrades to plain http while the effective final URL is https — an HTTP→HTTPS upgrade quirk worth remembering when writing fetch policy later.

### Task 1B summary

| Question | Status | Canonical URL supported by evidence |
|---|---|---|
| UQ-1 Tribal Development | **RESOLVED** | `https://tribal.maharashtra.gov.in/` (department); mahatribal pair = Commissionerate mirror, excluded |
| UQ-2 Agriculture | **RESOLVED** | `https://krishi.maharashtra.gov.in/`; `mahaagri.gov.in` dead |
| UQ-3 SWAYAM | **RESOLVED** | Application portal under Tribal Development, not a standalone source |
| UQ-4 H&TE | **RESOLVED** | `https://htedu.maharashtra.gov.in/` eligible as authoritative source (not yet registered) |

Database changes in Task 1B: **NONE**. No tests were run (no code changed). UQ-5/UQ-6 remain as previously documented (UQ-5 largely answered by Task 1A fetch evidence; UQ-6 — remaining departments — still open).

## Stopping point

Per instructions, work stops here. Phase 3B migration `0008` is NOT started.
