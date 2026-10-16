# Maharashtra Source Registry — Design Inventory (Phase 3B Pre-Work)

> **Status:** Design-only documentation. No ingestion pipeline, scrapers, migrations, or application code are implemented by this document.
> **Scope:** Proposed `tbl_scheme_source` / `tbl_scheme_source_resource` seed inventory for Government of Maharashtra welfare schemes.
> **Verification:** Every URL below was verified via live web search on **2026-10-03**. No URLs are invented; anything unverified is explicitly marked `UNVERIFIED` and excluded from the registry until confirmed.
> **Related docs:** `PHASE_3B_TO_3F_IMPLEMENTATION_SPEC.md` (schema spec), `PHASE_3A_SCHEME_ARCHITECTURE_AUDIT.md` (audit), `PROJECT_STATE.md` (implementation state).

---

## 1. Design Principles for the Registry

1. **One row per authoritative origin, not per document.** The `tbl_scheme_source` registry holds stable sources; individual scheme pages/PDFs become `tbl_scheme_source_resource` entries under them (Phase 3B).
2. **Precedence rank decides conflict resolution.** When two sources describe the same scheme, the lower `precedence_rank` number wins. Department/GR/e-Gazette outrank aggregators (myScheme, india.gov.in).
3. **Aggregators are discovery sources, not authority sources.** myScheme and india.gov.in may *point to* a scheme but never define its rules; their records feed candidate discovery only.
4. **Marathi-first reality.** Most Maharashtra GRs and department pages are primary in Marathi with partial English. The registry records language so the extraction pipeline can plan normalization (the `tbl_scheme_source_content` table already supports `RAW` / `NORMALIZED` / `EXTRACTED_TEXT` variants per language).
5. **Only verifiable sources enter the DB.** A source is registered only after a human (or documented verification run) confirms the URL resolves.

**Legend for fields used below:**

| Field | Meaning |
|---|---|
| Authority level | `STATE` (Govt. of Maharashtra department/portal), `NATIONAL-AGGREGATOR` (central portal aggregating states), `STATE-PORTAL` (state-level shared service portal) |
| Catalogue | Contains a browsable list of schemes (names + at least summary metadata) |
| PDFs | Hosts official PDFs (GRs, guidelines, resolution circulars) |
| GRs | Hosts Government Resolutions (शासन निर्णय) |
| API | Structured data / official API / machine-readable export known or strongly indicated |
| Fetch method | Expected `fetch_policy` for the ingestion service (all fetches are read-only HTTP GET with bounded timeout/size, per existing `ingestion_service.py` invariants) |

---

## 2. Tier 1 — Authoritative Maharashtra Sources (highest precedence)

### SRC-01 — Maharashtra Government Main Portal

| Field | Value |
|---|---|
| Authority | Government of Maharashtra (General Administration) |
| Department | All departments (umbrella portal) |
| Official URL | https://maharashtra.gov.in/ |
| Source type | `GOVERNMENT_PORTAL` |
| Language | Marathi, English |
| Authority level | `STATE-PORTAL` |
| Scheme catalogue | Yes (department and schemes directory) |
| PDFs | Yes (department-published documents) |
| GRs | Links to GR portal |
| API | No known API |
| Application portal | Links outward (Aaple Sarkar, MahaDBT, department portals) |
| Fetch method | Manual/periodic HTTP GET of department directory pages (HTML) |
| Update frequency | Continuous (portal is maintained daily) |
| Priority | **P1** — canonical entry point; used for cross-verification of department names and official links |
| Notes | Verified 2026-10-03. Umbrella portal; primary value is the authoritative list of department sites, used to validate every other registry row's authority attribution. |

### SRC-02 — Government Resolutions (GR) Portal

| Field | Value |
|---|---|
| Authority | Government of Maharashtra (Mantralaya) |
| Department | All departments (GRs issued per department) |
| Official URL | https://gr.maharashtra.gov.in/1145/Government-Resolutions |
| Source type | `GOVERNMENT_WEBSITE` |
| Language | Primarily Marathi (some English) |
| Authority level | `STATE` |
| Scheme catalogue | No (GRs reference schemes but there is no scheme list) |
| PDFs | **Yes — the primary GR PDF archive** |
| GRs | **Yes — canonical source** |
| API | No known API. Third-party open mirrors exist (e.g., orgpedia's `mahGRs` GitHub repository with English translations, refreshed weekly) but they are **not** authoritative and are excluded from the registry. |
| Application portal | N/A |
| Fetch method | HTTP GET on GR search/listing pages + PDF download of individual GRs |
| Update frequency | Continuous — new GRs are published as issued (weekly digest cadence exists in third-party mirrors) |
| Priority | **P1** — the single most important evidence source: scheme launches, amendments, eligibility changes, and budget provisions in Maharashtra are formalized via GRs |
| Notes | Verified 2026-10-03 (URL corroborated by official district sites, e.g. satara.gov.in, and archive.org GR records). Every `tbl_scheme_rule_provenance` citation for a state rule change should ultimately trace to a GR PDF from here. |

### SRC-03 — MahaDBT (Direct Benefit Transfer Portal)

| Field | Value |
|---|---|
| Authority | Government of Maharashtra |
| Department | Multi-department (Agriculture, Social Justice, Tribal Development, Higher & Technical Education — all DBT schemes) |
| Official URL | https://mahadbt.maharashtra.gov.in/ |
| Scheme-data pages (verified) | https://mahadbt.maharashtra.gov.in/Farmer/SchemeData/SchemeData?str=E9DDFA703C38E51AA76CB4993576E544 (Farmer schemes) · https://mahadbt.maharashtra.gov.in/login/login · https://mahadbt.maharashtra.gov.in/home/index |
| Source type | `GOVERNMENT_PORTAL` |
| Language | Marathi, English |
| Authority level | `STATE-PORTAL` |
| Scheme catalogue | **Yes — structured per-scheme benefit/component pages**, the closest thing Maharashtra has to a machine-queriable scheme catalogue |
| PDFs | Yes (scheme guidelines uploaded to scheme pages) |
| GRs | No (GRs stay on SRC-02) |
| API | No public API; pages are server-rendered ASP.NET with opaque session tokens (`str=` parameters). Treat as structured-HTML, not API. |
| Application portal | **Yes — this IS the application portal** for agriculture DBT and most departmental DBT schemes |
| Fetch method | HTTP GET on public scheme-data listing pages; authenticated areas are out of scope |
| Update frequency | Per academic year / crop season (application windows open and close; scheme pages update with windows) |
| Priority | **P1** — best combination of catalogue + application-portal semantics in one source |
| Notes | Verified 2026-10-03. Session-token URLs may expire; the `tbl_scheme_source_resource` design (stable resource identity separate from snapshot) matters most here — the *resource* is the scheme-data listing, the *snapshot* is whatever the tokenized URL returns that day. |

### SRC-04 — Social Justice & Special Assistance Department (SJSA)

| Field | Value |
|---|---|
| Authority | Government of Maharashtra |
| Department | Social Justice & Special Assistance |
| Official URL | https://sjsa.maharashtra.gov.in/ |
| Schemes pages (verified) | https://sjsa.maharashtra.gov.in/en/schemes-programmes/ · https://sjsa.maharashtra.gov.in/en/service/special-assistance-schemes/ |
| Source type | `GOVERNMENT_WEBSITE` |
| Language | Marathi, English (dedicated `/en/` paths) |
| Authority level | `STATE` |
| Scheme catalogue | **Yes — dedicated schemes/programmes listing** (SC/OBC/SBC/Vimukta Jati scholarships, pensions, special assistance) |
| PDFs | Yes (scheme resolutions and guidelines) |
| GRs | Links/references to department GRs |
| API | No known API |
| Application portal | Departmental schemes largely flow through MahaDBT (SRC-03); certificates via Aaple Sarkar (SRC-07) |
| Fetch method | HTTP GET on schemes listing + detail pages |
| Update frequency | Monthly-ish (schemes list updated as GRs issue) |
| Priority | **P1** — highest-value departmental site for the existing VidyaSetu student/scholarship persona |
| Notes | Verified 2026-10-03. English paths make this the easiest first departmental ingestion target. |

### SRC-05 — Tribal Development Department

| Field | Value |
|---|---|
| Authority | Government of Maharashtra |
| Department | Tribal Development (आदिवासी विकास विभाग) |
| Official URL | https://tribal.maharashtra.gov.in/ (also resolves as http://mahatribal.gov.in/ and https://mahatribal.mahaitgov.in/) |
| Source type | `GOVERNMENT_WEBSITE` |
| Language | Primarily Marathi |
| Authority level | `STATE` |
| Scheme catalogue | Yes (केंद्रीय योजना / राज्य योजना — central & state scheme sections) |
| PDFs | Yes (GRs and scheme circulars) |
| GRs | Yes (department GR section, e.g. on nbtribal.in mirror — verify before registry entry) |
| API | No known API |
| Application portal | MahaDBT for DBT schemes; departmental hostels/admissions via own processes |
| Fetch method | HTTP GET on scheme sections (Marathi HTML — normalization pipeline must handle Devanagari) |
| Update frequency | Monthly-ish |
| Priority | **P2** — major welfare department, but Marathi-heavy content raises extraction effort |
| Notes | Verified 2026-10-03 (multiple official domains observed — record the canonical domain after a redirect test; see Unresolved Questions UQ-1). |

### SRC-06 — Department of Agriculture (Krishi)

| Field | Value |
|---|---|
| Authority | Government of Maharashtra |
| Department | Agriculture |
| Official URL | https://krishi.maharashtra.gov.in/ |
| Source type | `GOVERNMENT_WEBSITE` |
| Language | Marathi, English |
| Authority level | `STATE` |
| Scheme catalogue | Partial (scheme descriptions; full application catalogue lives on MahaDBT SRC-03) |
| PDFs | Yes |
| GRs | References department GRs |
| API | No known API |
| Application portal | MahaDBT (SRC-03) is the application portal for agriculture schemes |
| Fetch method | HTTP GET |
| Update frequency | Seasonal |
| Priority | **P2** — needed for farmer persona; scheme metadata itself is better sourced from MahaDBT |
| Notes | Verified 2026-10-03. Older references to `mahaagri.gov.in` exist in third-party docs; treat `krishi.maharashtra.gov.in` as canonical (verified live), see UQ-2. |

### SRC-07 — Aaple Sarkar (Citizen Services Portal)

| Field | Value |
|---|---|
| Authority | Government of Maharashtra (Rural Development & Panchayat Raj + General Administration) |
| Department | Multi-department (certificates: income, caste, domicile, senior citizen, etc.) |
| Official URLs (verified) | https://aaplesarkar.maharashtra.gov.in/ · https://aaplesarkar.mahaonline.gov.in/en (service portal) · https://aaplesarkar.mahaonline.gov.in/en/commonform/citizenservices (notified services list) |
| Source type | `GOVERNMENT_PORTAL` |
| Language | Marathi, English |
| Authority level | `STATE-PORTAL` |
| Scheme catalogue | No — it is a **certificate/service** catalogue (400+ services), which VidyaSetu needs for the document-requirements side, not scheme eligibility |
| PDFs | Some (forms, checklists) |
| GRs | No |
| API | No public API |
| Application portal | **Yes — the certificate application portal** |
| Fetch method | HTTP GET on notified-services list (documents per service) |
| Update frequency | Low (service list changes rarely) |
| Priority | **P3** — secondary source; valuable for mapping `tbl_scheme_document_master` entries to real application requirements |
| Notes | Verified 2026-10-03. Do not confuse with MahaDBT (DBT schemes) — Aaple Sarkar is certificates/right-to-service. |

### SRC-08 — Maharashtra State e-Gazette (MahaOnline)

| Field | Value |
|---|---|
| Authority | Government of Maharashtra (Directorate of Government Printing & Stationery, via MahaOnline) |
| Department | All departments (gazette publications) |
| Official URL | https://egazzete.mahaonline.gov.in/Forms/GazetteSearch.aspx |
| Source type | `GOVERNMENT_PORTAL` |
| Language | Marathi, English |
| Authority level | `STATE` |
| Scheme catalogue | No |
| PDFs | **Yes — official gazette PDFs** |
| GRs | Yes — GRs are formally gazetted; the gazette is the *legal record* of what the GR portal publishes |
| API | No known API (ASP.NET search form) |
| Application portal | N/A (also hosts name-change gazette applications — irrelevant here) |
| Fetch method | HTTP GET on gazette search results + PDF retrieval |
| Update frequency | Periodic gazette publication cycle |
| Priority | **P3** — final legal-verification tier; use when a GR's status is disputed or amended |
| Notes | Verified 2026-10-03. Note spelling: `egazzete` (two z's) is the actual verified subdomain. Lower precedence than the GR portal (SRC-02) because it is harder to search, but legally definitive. |

### SRC-09 — Women and Child Development Department

| Field | Value |
|---|---|
| Authority | Government of Maharashtra |
| Department | Women & Child Development (महिला व बाल विकास विभाग) |
| Official URL | https://womenchild.maharashtra.gov.in/ |
| Source type | `GOVERNMENT_WEBSITE` |
| Language | Primarily Marathi |
| Authority level | `STATE` |
| Scheme catalogue | Partial (women's empowerment and child schemes incl. Majhi Ladki Bahin family) |
| PDFs | Yes |
| GRs | References department GRs |
| API | No known API |
| Application portal | Dedicated scheme portals exist (e.g., https://ladakibahin.maharashtra.gov.in/ — verified referenced from the official Mumbai Suburban district site) |
| Fetch method | HTTP GET |
| Update frequency | Monthly-ish |
| Priority | **P2** — core source for the "Women" persona discovery filter that already exists in `SchemesPage.jsx` |
| Notes | Verified 2026-10-03. Individual flagship-scheme portals (like ladakibahin) should be registered as separate `tbl_scheme_source_resource` entries under this source rather than as separate sources. |

---

## 3. Tier 2 — National Aggregators (discovery + cross-verification only)

### SRC-10 — myScheme

| Field | Value |
|---|---|
| Authority | Government of India (MeitY / NeGD) |
| Department | All (central + all states incl. Maharashtra) |
| Official URL | https://www.myscheme.gov.in/ |
| Maharashtra section (verified) | https://www.myscheme.gov.in/search/state/Maharashtra |
| Source type | `GOVERNMENT_PORTAL` |
| Language | English, Hindi (multiple Indian languages) |
| Authority level | `NATIONAL-AGGREGATOR` |
| Scheme catalogue | **Yes — ~5,000+ schemes with structured attributes** (category, gender, age, income, caste, state tags) — the richest structured scheme metadata publicly available |
| PDFs | Some (linked official documents) |
| GRs | No |
| API | **No official public API.** Community scrapes exist (Kaggle/HuggingFace datasets) but are unofficial and must not be used as ingestion inputs. |
| Application portal | Links out to official application portals |
| Fetch method | HTTP GET on state-filtered search + per-scheme detail pages |
| Update frequency | Continuous (schemes added as departments onboard) |
| Priority | **P2 — as a discovery/cross-check source only.** Never the authority for a rule; every myScheme record must be reconciled with a Tier-1 source before publishing |
| Notes | Verified 2026-10-03 (Maharashtra listing shows 50+ social welfare, 27 education schemes etc.). Best first-pass source for *discovering* schemes missing from our catalogue. |

### SRC-11 — India.gov.in National Portal

| Field | Value |
|---|---|
| Authority | Government of India (NIC) |
| Department | All levels (union + states) |
| Official URLs (verified) | https://www.india.gov.in/ · https://www.india.gov.in/my-government/schemes · https://www.india.gov.in/my-government/schemes/search (5,700+ schemes indexed) |
| Source type | `GOVERNMENT_PORTAL` |
| Language | English, Hindi |
| Authority level | `NATIONAL-AGGREGATOR` |
| Scheme catalogue | Yes (searchable central/state scheme index) |
| PDFs | Some |
| GRs | No |
| API | No known API |
| Application portal | Links out |
| Fetch method | HTTP GET on scheme search pages |
| Update frequency | Continuous |
| Priority | **P4 — lowest.** Overlaps myScheme with weaker per-scheme structure; register but fetch only for cross-verification |
| Notes | Verified 2026-10-03. |

### SRC-12 — IGOD Maharashtra Schemes Directory

| Field | Value |
|---|---|
| Authority | Government of India (India Government Portal — IGOD, NIC) |
| Department | Maharashtra state listings |
| Official URL | https://igod.gov.in/sg/MH/SPMA/organizations |
| Source type | `GOVERNMENT_PORTAL` |
| Language | English |
| Authority level | `NATIONAL-AGGREGATOR` |
| Scheme catalogue | Yes — "Schemes / Programmes / Missions / Applications" directory of Maharashtra organizations |
| PDFs | Some |
| GRs | No |
| API | No known API |
| Application portal | Links out |
| Fetch method | HTTP GET |
| Update frequency | Low |
| Priority | **P4** — useful for enumerating official Maharashtra scheme portals we may have missed; not for rule content |
| Notes | Verified 2026-10-03. Registry-discovery aid: periodically scan for new official department portals to add as Tier-1 sources. |

---

## 4. Source-type mapping to the existing model

The existing `tbl_scheme_source.source_type` CHECK constraint allows exactly: `GOVERNMENT_API`, `GOVERNMENT_WEBSITE`, `GOVERNMENT_PORTAL`, `GOVERNMENT_PDF`, `OTHER_AUTHORIZED_SOURCE`. Mapping of the proposed registry:

| Proposed source | source_type value |
|---|---|
| SRC-01 Maharashtra main portal | `GOVERNMENT_PORTAL` |
| SRC-02 GR portal | `GOVERNMENT_WEBSITE` (PDFs are its resources, not its type) |
| SRC-03 MahaDBT | `GOVERNMENT_PORTAL` |
| SRC-04 SJSA | `GOVERNMENT_WEBSITE` |
| SRC-05 Tribal Development | `GOVERNMENT_WEBSITE` |
| SRC-06 Agriculture | `GOVERNMENT_WEBSITE` |
| SRC-07 Aaple Sarkar | `GOVERNMENT_PORTAL` |
| SRC-08 e-Gazette | `GOVERNMENT_PORTAL` |
| SRC-09 WCD | `GOVERNMENT_WEBSITE` |
| SRC-10 myScheme | `GOVERNMENT_PORTAL` |
| SRC-11 India.gov.in | `GOVERNMENT_PORTAL` |
| SRC-12 IGOD | `GOVERNMENT_PORTAL` |

**Observation for the 3B schema:** no proposed source uses `GOVERNMENT_API` or `GOVERNMENT_PDF` — there is no verified official API among Maharashtra scheme sources. `GOVERNMENT_PDF` will apply to *resources* (individual GR/guideline PDFs under SRC-02/08), reinforcing the Phase 3B design decision that resource-level typing belongs on `tbl_scheme_source_resource`, not on the source registry. The CHECK constraint on the source table is therefore adequate as-is.

---

## 5. Precedence ordering (proposed `precedence_rank`)

| Rank | Source | Rationale |
|---|---|---|
| 1 | SRC-02 GR portal | Formal rule changes originate here |
| 2 | SRC-04, SRC-05, SRC-06, SRC-09 (department sites) | Departmental scheme definition |
| 3 | SRC-08 e-Gazette | Legal confirmation |
| 4 | SRC-03 MahaDBT | Application semantics, benefit amounts |
| 5 | SRC-01 Maharashtra portal, SRC-07 Aaple Sarkar | Cross-verification, document requirements |
| 6 | SRC-10 myScheme | Discovery |
| 7 | SRC-11 India.gov.in, SRC-12 IGOD | Discovery, registry enumeration |

---

## 6. Explicitly excluded (with reasons)

| Candidate | Reason for exclusion |
|---|---|
| orgpedia `mahGRs` (GitHub) & mahsummary.orgpedia.in | Third-party translations of GRs. Useful as an *internal research aid* during extraction, but not an authoritative source; must never be registered or cited in provenance. |
| Kaggle / HuggingFace myScheme scrapes | Unofficial datasets, stale, unverifiable provenance. |
| District-collector sites (pune.gov.in, satara.gov.in, bhandara.gov.in, mumbaisuburban.gov.in, mumbaicity.gov.in) | Official but derivative — they republish department schemes. Use them to *verify* links (as done above), not as ingestion sources. |
| `agroorbit.com`, `napanta.com`, `indiagovschemes.com`, `eligohub.in` etc. | Private scheme-information sites. Never registered. |
| Bank product pages (e.g., Bank of Maharashtra MKSY) | Bank lending products, not government schemes. |
| MahaOnline `swayam.mahaonline.gov.in` (tribal scholarship portal) | Official, but scope and status need confirmation before registration (see UQ-3). |

---

## Phase 3B — Task 1C: Department & Authority Inventory

> Added 2026-10-03. Source-inventory only: **no DB records, no schema changes, no ingestion.** All "Verified" rows were confirmed by direct HTTP GET on 2026-10-03 (status, redirect behavior, page title, scheme-content markers). Search engines were used only to discover candidates, never as authority proof. Carried-forward origins from Tasks 1A/1B are listed but not re-probed.

### A. Verified authoritative origins (department-level sites)

| candidate_id | authority_name | organisational_type | parent_authority | canonical_url (verified) | scheme_content | language | source_relationship | priority | evidence |
|---|---|---|---|---|---|---|---|---|---|
| CAND-001 | Public Health Department | Department | Govt. of Maharashtra | https://phd.maharashtra.gov.in/en/ (200, 0 redirects) | Yes — 12× scheme markers, Schemes/Programmes nav | Bilingual | Candidate source | P1 | Homepage title + schemes nav |
| CAND-002 | National Health Mission, Maharashtra | Mission | Public Health Dept | https://nhm.maharashtra.gov.in/en/ (200) | Yes — health programmes | Bilingual | Separate organisation | P2 | Homepage title |
| CAND-003 | Labour Department | Department | Industries, Energy & Labour Dept (IELMD) | https://labour.maharashtra.gov.in/en (200, 0 redirects) | Yes — 164× "labour", Welfare Board refs | Bilingual | Candidate source | P2 | Body keyword scan |
| CAND-005 | Maharashtra Building & Other Construction Workers Welfare Board | Board | Labour Dept | https://mahabocw.in/en/ (200, 0 redirects) | Yes — worker registration + welfare schemes | Bilingual | Separate organisation | P2 | Title + body (note: `.in` domain, not `.gov.in`) |
| CAND-006 | Housing Department | Department | Govt. of Maharashtra | https://housing.maharashtra.gov.in/en/ (200, 0 redirects) | Yes — PMAY-U / AHP content | Bilingual | Candidate source | P2 | Homepage title + PMAY content |
| CAND-009 | Other Backward Bahujan Welfare Department | Department | Govt. of Maharashtra | https://obcbahujankalyan.maharashtra.gov.in/ (200, 0 redirects) | Yes — 14× scheme markers | Marathi-first | Candidate source | P1 | Title + scheme markers |
| CAND-010 | Minority Development Department | Department | Govt. of Maharashtra | https://mdd.maharashtra.gov.in/en/ (200, 0 redirects) | Yes — Schemes/Programmes nav | Bilingual | Candidate source | P1 | Nav structure |
| CAND-012 | Rural Development & Panchayat Raj Department | Department | Govt. of Maharashtra | https://rdd.maharashtra.gov.in/en/ (200, 0 redirects) | Yes — 15× scheme markers | Bilingual | Candidate source | P2 | Title + markers |
| CAND-013 | Co-operation, Marketing & Textiles Department | Department | Govt. of Maharashtra | https://mahasahakar.maharashtra.gov.in/en/ (200, 0 redirects) | Yes — 12× scheme markers | Bilingual | Candidate source | P3 | Title + markers |
| CAND-014 | Textiles Department (sub-site) | Department sub-site | Co-op, Marketing & Textiles Dept | https://mahatextile.maharashtra.gov.in/en/ (200, 0 redirects) | Yes — handloom scheme compendium + GR section | Bilingual | Candidate source (same parent as CAND-013 — keep distinct, see notes) | P3 | GR pages + handloom compendium |
| CAND-015 | Animal Husbandry & Dairying Department | Department | Govt. of Maharashtra | https://dahd.maharashtra.gov.in/en/ (200, 0 redirects) | Yes — 16× scheme markers, central+state scheme nav | Bilingual | Candidate source | P2 | Title + schemes nav |
| CAND-016 | Food, Civil Supplies & Consumer Protection Department | Department | Govt. of Maharashtra | https://mahafood.gov.in/en/ (200, 0 redirects) | Yes — 15× scheme markers; Services/forms | Bilingual | Candidate source | P2 | Title + schemes nav |
| CAND-018 | Directorate of Industries | Directorate | Industries, Energy & Labour Dept (IELMD) | https://industry.maharashtra.gov.in/en (200, 0 redirects) | Yes — incentive schemes | Bilingual | Candidate source | P3 | Body scan (Industries 24×) |
| CAND-019 | Energy Department | Department | Govt. of Maharashtra | https://energy.maharashtra.gov.in/en/ (200, 0 redirects) | Yes — 16× scheme markers (subsidy programmes) | Bilingual | Candidate source | P3 | Title + schemes nav |
| CAND-021 | Urban Development Department | Department | Govt. of Maharashtra | https://urban.maharashtra.gov.in/ (200, 0 redirects) | Partial — नगरविकास dept site | Marathi-first | Candidate source | P3 | Title |

**Carried forward (already verified in Tasks 1A/1B, not re-probed):** Maharashtra Government Main Portal (SRC-01), GR Portal (SRC-02), MahaDBT (SRC-03), SJSA (SRC-04), Tribal Development Department (canonical `tribal.maharashtra.gov.in`), Agriculture Department (`krishi.maharashtra.gov.in`), Higher & Technical Education Department (`htedu.maharashtra.gov.in` — candidate SRC-13).

### B. Verified separate commissionerates / boards / corporations

| candidate_id | authority_name | organisational_type | parent_authority | canonical_url (verified) | source_relationship | priority | evidence / notes |
|---|---|---|---|---|---|---|---|
| CAND-004 | Commissioner of Labour | Commissionerate | Labour Dept | https://mahakamgar.maharashtra.gov.in/ (200, 0 redirects) | Separate organisation | P2 | Title: "Commissioner of Labour"; welfare-scheme teasers on homepage |
| CAND-011 | Maharashtra State Minority Commission | Commission | Govt. of Maharashtra | https://msmc.maharashtra.gov.in/en/ (200, 0 redirects) | Separate organisation | P3 | Distinct org from Minority Development Dept (CAND-010) |
| CAND-007 | Maharashtra Housing & Area Development Authority (MHADA) | Corporation | Housing Dept | https://mhada.gov.in/ (200, 1 redirect → `/mr` Marathi default) | Separate organisation + application portal | P3 | Title confirms; lottery housing schemes |
| CAND-022 | Directorate of Municipal Administration | Directorate | Urban Development Dept | https://mahadma.maharashtra.gov.in/en/home/ (200, 0 redirects) | Separate organisation | P4 | 1.3 MB page; monitors AMRUT/Smart City schemes |
| CAND-023 | Maharashtra State Board of Skill, Vocational Education & Training (MSBSVET) | Board | Skills, Employment, Entrepreneurship & Innovation Dept | https://msbsvet.edu.in/ (200, 1 redirect → `/Public/Home.aspx`) | Separate organisation | P4 | `.edu.in` domain |
| CAND-024 | Maharashtra State OBC Finance & Development Corporation | Corporation | Other Backward Bahujan Welfare Dept | https://msobcfdc.in/ (200, but 1.8 KB JS shell — content client-rendered) | Separate organisation | P3 | **Partially verified** — title/identity confirmed, scheme content not confirmable via plain HTML |
| — | Tribal Development Commissionerate | Commissionerate | Tribal Development Dept | https://mahatribal.gov.in/ + https://mahatribal.mahaitgov.in/ (verified in Task 1B) | Separate organisation (mirror pair on two hosts) | P3 | Carried forward — do not collapse with the Department |
| CAND-002 | National Health Mission Maharashtra | Mission | Public Health Dept | (see section A) | Separate organisation | P2 | Listed here as well for organisational-type completeness |

### C. Verified application / service portals

Not scheme sources by themselves; future `tbl_scheme_source_resource` material.

| candidate_id | portal | verified URL | serving | evidence / notes |
|---|---|---|---|---|
| CAND-008 | Maharashtra Housing Development Corporation (Mah Housing Corp) | https://mahahousing.mahaonline.gov.in/ (200, 0 redirects; 2.4 MB) | Housing applications on MahaOnline | Title confirms |
| CAND-017 | Mahaswayam (SEEID) | https://mahaswayam.gov.in/ (200, 1 redirect → www) + sub-portals `kaushalya.mahaswayam.gov.in` (MSSDS) and `rojgar.mahaswayam.gov.in` (employment) — sub-portals **partially verified** (search-referenced, not probed) | Dept portal integrating skilling/employment/entrepreneurship | Dept-level origin with application sub-portals |
| CAND-025 | SARAL — School Education portal | https://education.maharashtra.gov.in/ (200, 0 redirects) | Admissions, pre-school registration, education services | Title: "SARAL – Government of Maharashtra Education Portal" |
| CAND-026 | Maharashtra Foreign Scholarship Portal | https://fs.maharashtra.gov.in/ (200, 0 redirects) | Overseas-scholarship applications (OBC/VJNT/SBC) | Title confirms; application portal, thin catalogue |
| CAND-027 | Sanjay Gandhi Niradhar Anudan (pension) portal | https://sas.mahait.org/ (200, **1 redirect → `https://mahadbt2.mahadbt` infra**) | Pension/financial-assistance applications | **Key finding: the legacy `mahait.org` pension portal redirects into MahaDBT v2 infrastructure** — pension applications have converged onto the MahaDBT family |
| CAND-028 | SWAYAM (Tribal scholarships) | https://swayam.mahaonline.gov.in/ (verified in Task 1B) | Tribal scholarship applications on MahaOnline | Classification confirmed in 1B — resource under Tribal source, never a standalone source |
| — | Ration card services (rcms.mahafood.gov.in) | referenced from mahafood.gov.in services page; **not probed** | PDS services | Unverified |
| — | TRTI VJNT/OBC/SBC overseas scholarship portal (vjnt-fs.trti-maha.in) | **not probed** | Scholarship applications | Unverified |
| — | MJPJAY health-insurance portal (jeevandayee.gov.in) | **UNVERIFIED — connection failed on both http and https from this network (Task 1C probes + retries)** | Cashless health-treatment portal | Scheme itself is well documented on government sources (e.g., sjsa/Wikipedia corroboration), but the canonical application portal could not be verified. Record failure; do not substitute |

### D. Supporting government sources

Carried forward unchanged from the registry (SRC-02 GR Portal, SRC-08 e-Gazette, SRC-10 myScheme, SRC-11 india.gov.in, SRC-12 IGOD). No new supporting sources were discovered in this pass; the Textiles sub-site's GR section (CAND-014) shows department-level GR archives also exist on departmental sites.

### E. Unverified / unresolved candidates

| area | status | what was attempted / what is missing |
|---|---|---|
| Water Resources Department | **UNVERIFIED** | `mahawrd.maharashtra.gov.in` connection failed (http probe returned 000). Only the regulatory authority `mwrra.maharashtra.gov.in` surfaced in discovery but was not probed. |
| Fisheries | **Unknown** | Maharashtra's Mantralaya department combines Animal Husbandry, Dairy Development **and Fisheries**; `dahd.maharashtra.gov.in` covers AH+dairy but no fisheries-specific scheme section was confirmed in this pass. |
| Medical Education & Drugs Department | **Not yet discovered** | No canonical domain surfaced in this pass's searches; needs a dedicated discovery round. |
| Health insurance administration (MJPJAY) | **UNVERIFIED** | Portal unreachable (see CAND-029 row in section C); scheme-level authority (Public Health Dept) verified separately. |
| Environment/Climate, Transport, Finance/pension authorities, Water supply/sanitation, Energy-utility subsidies (MSEDCL) | **Not attempted in this pass** | Deliberate scope limit: citizen-benefit relevance of each is lower and unproven; next inventory round should probe `transport.maharashtra.gov.in`, MSEDCL subsidy pages, and Finance Dept pension portals. |
| District-level sites | Excluded by design | District collectorates republish department schemes; they verify links but are not ingestion origins (consistent with the registry's exclusion list). |

### F. Coverage summary

- **Candidate origins investigated: 29** (26 directly HTTP-probed this pass + SWAYAM, Tribal Commissionerate, GR/departmental carried-forward items).
- **Verified (direct HTTP evidence): 24**
- **Partially verified: 3** (msobcfdc.in — JS-only shell; MSBSVET — redirect+identity only; Mahaswayam sub-portals — referenced but unprobed)
- **Unverified (probes failed): 2** (jeevandayee.gov.in / MJPJAY portal; mahawrd.maharashtra.gov.in)
- **Classified as application/service portals: 8** (Mah Housing Corp, Mahaswayam + sub-portals, SARAL, Foreign Scholarship, sas.mahait→MahaDBT-v2, SWAYAM, rcms [unverified], TRTI [unverified])
- **Classified as separate organisations (not mergeable with their parent department): 8** (Commissioner of Labour, MBOCWW Board, MHADA, Minority Commission, NHM, Mah Housing Corp, DMA, Tribal Commissionerate — plus MS-OBC-FDC and MSBSVET provisionally)
- **Remaining gaps:** Water Resources (probe failed), Medical Education (undiscovered), Fisheries content (unknown), MJPJAY portal (unreachable), Environment/Transport/Finance-pension/utility-subsidy areas (not attempted).

**Structural findings for the schema freeze:**
1. The **Department ≠ Commissionerate/Board/Corporation** pattern (first proven in Task 1B for Tribal) recurs in at least 8 more organisations. The resource model must support multiple independent origins per department.
2. **Application portals are converging on MahaDBT and MahaOnline infrastructure** (sas.mahait.org → mahadbt2.maharashtra.gov.in; SWAYAM, Mah Housing Corp on mahaonline.gov.in). Two hosting platforms dominate — this argues for platform-level fetch behavior evidence (cookies, redirects) captured once per platform, not per resource.
3. **Sibling sub-sites share CMS templates** (IELMD: labour + industry share identical boilerplate meta-descriptions). Content-based identity verification (title/body scan), not domain-string similarity, is the reliable disambiguator — the pipeline should store what was *observed* in snapshots, exactly as `tbl_scheme_source_content` is designed to.
4. Non-`.gov.in` official domains exist and verified fine (mahabocw.in, msobcfdc.in, msbsvet.edu.in) — a domain-suffix allowlist would have wrongly rejected real origins; `authoritative_status` should be evidence-based.

---

## 7. Unresolved Questions (updated after Task 1C)

- **UQ-1 — Tribal Development canonical domain:** ✅ **RESOLVED (Task 1B)** — `https://tribal.maharashtra.gov.in/` is the department; the mahatribal pair is the distinct Commissionerate.
- **UQ-2 — Agriculture legacy domain:** ✅ **RESOLVED (Task 1B)** — `https://krishi.maharashtra.gov.in/` canonical; `mahaagri.gov.in` is dead.
- **UQ-3 — SWAYAM:** ✅ **RESOLVED (Task 1B)** — application portal under Tribal Development, not a standalone source.
- **UQ-4 — H&TE department site:** ✅ **RESOLVED (Task 1B)** — `https://htedu.maharashtra.gov.in/` eligible as authoritative source.
- **UQ-5 — Fetch policy for ASP.NET portals:** largely answered (Task 1A: anonymous GETs suffice for public pages); tokenized deep URLs still need per-resource re-verification.
- **UQ-6 — Health, Labour, Housing and other departments:** **substantially resolved by Task 1C** — 29 origins inventoried, 24 verified. Residual gaps: Water Resources (probe failed), Medical Education (undiscovered), Fisheries (unknown), MJPJAY portal (unreachable), Environment/Transport/Finance-pension/utility-subsidy areas (not attempted).

---

## 8. Recommended Next Small Implementation Task

Register the Tier-1 sources (SRC-01 … SRC-04) through the **existing** admin API (`POST /api/v1/admin/sources`) as seed data — no migration, no new code, exercising the already-built source registry CRUD end-to-end and validating the UQ-1/UQ-2/UQ-5 questions with real fetches. Only after that does Phase 3B migration `0008` (`tbl_scheme_source_resource`, `tbl_scheme_ingestion_item`, additive columns) get authored, with its `canonical_base_url` / `fetch_policy` / `precedence_rank` columns informed by what was just learned.

---

*Registry design prepared 2026-10-03. All URLs verified via web search on that date. No application code or database state was modified by this document.*
