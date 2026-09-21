# PHASE 2C — CITIZEN DATA-COLLECTION EXPERIENCE: IMPLEMENTATION SPECIFICATION

**Status**: PLANNING ONLY — no code, schema, seed, API, or frontend changes have been made for this specification.
**Prepared from**: live DB audit of `GENERAL_CITIZEN_PROFILE` v1 (19 questions), `backend/seed_data/forms.json`, `scripts/seed_forms.py`, `app/services/profile_mapping.py` (52 registry entries), `app/services/normalization_service.py`, and the Phase 1/2A/2B models.

**Design principle**: the platform will eventually serve hundreds/thousands of schemes from external sources, so the citizen profile is designed around **reusable welfare-relevant attributes** (the canonical data catalogue in Task 2), not around the current 7 seed schemes. Every proposed field must justify itself by eligibility usage; data minimization (Task 9) is applied throughout.

---

## 1. CURRENT FORM AUDIT (Task 1)

Live `GENERAL_CITIZEN_PROFILE` v1 — 7 sections, 19 questions, 31 options, 1 condition. Registry resolution verified programmatically: **18/19 mapped**, 1 unmapped by design.

| # | question_code | section | type/data_type | req | profile_field | normalization target | fact_code | condition |
|---|---|---|---|---|---|---|---|---|
| 1 | FULL_NAME | PERSONAL_INFO | text/STRING | yes | `full_name` | citizen (fact-only) | FULL_NAME | — |
| 2 | DATE_OF_BIRTH | PERSONAL_INFO | date/DATE | yes | `date_of_birth` | demographic (fact-only; identity table owned by registration) | DATE_OF_BIRTH | — |
| 3 | GENDER | PERSONAL_INFO | dropdown/STRING | no | `gender` | demographic.gender | GENDER | — |
| 4 | MOBILE_NUMBER | PERSONAL_INFO | text/STRING | no | `mobile_number` | citizen (fact-only) | MOBILE_NUMBER | — |
| 5 | FAMILY_SIZE | FAMILY_INFO | number/INTEGER | yes | `family_size` | demographic.family_size | FAMILY_SIZE | — |
| 6 | CURRENTLY_STUDYING | FAMILY_INFO | boolean/BOOLEAN | yes | `currently_studying` | education (fact-only) | CURRENTLY_STUDYING | — |
| 7 | STUDYING_COURSE | FAMILY_INFO | text/STRING | no | `course_name` | education.course_name | — | `CURRENTLY_STUDYING EQUALS YES → SHOW` |
| 8 | EDUCATION_LEVEL | EDUCATION_EMPLOYMENT | dropdown/STRING | no | `education_level` | education.education_level | EDUCATION_LEVEL | — |
9 | EMPLOYMENT_STATUS | EDUCATION_EMPLOYMENT | dropdown/STRING | no | `employment_status` | employment.employment_status | EMPLOYMENT_STATUS | — |
| 10 | ANNUAL_INCOME | FINANCIAL_INFO | decimal/DECIMAL | yes | `annual_income` | financial.annual_income | ANNUAL_INCOME | — |
| 11 | POVERTY_CATEGORY (APL/BPL/AAY) | FINANCIAL_INFO | dropdown/STRING | no | `poverty_category` | financial.poverty_category | POVERTY_CATEGORY | — |
| 12 | IS_BPL_CARD_HOLDER | FINANCIAL | boolean/BOOLEAN | no | `is_bpl_card_holder` | financial.is_bpl_gard_holder | IS_BPL_CARD_HOLDER | — |
| 12b | IS_BPL_CARD_HOLDER | FINANCIAL_INFO | boolean/BOOLEAN | no | `is_bpl_card_holder` | financial.is_bpl_card_holder | IS_BPL_ARD_HOLDER | — |
| 13 | SOCIAL_CATEGORY | SOCIAL_INFO | single_choice/STRING | no | `social_category` | demographic.social_category | SOCIAL_CATEGORY | — |
| 14 | DISABILITY_STATUS | SOCIAL_INFO | dropdown/STRING | no | `disability_status` | demographic.disability_status | DISABILITY_STATUS | — |
| 15 | STATE | LOCATION_INFO | text/ Maharashtra, district, area_type | yes | `state` | location.state | STATE | — |
| 16 | DISTRICT | LOCATION_INFO | text/STRING | yes | `district` | location.district | DISTRICT | — |
| 17 | AREA_TYPE | LOCATION_INFO | dropdown/STRING | no | `area_type` | location.area_type | AREA_TYPE | — |
| 18 | HAS_AADHAAR | DOCUMENTS | boolean/BOOLEAN | yes | `has_aadhaar` | citizen (fact-only) | HAS_AADHAR | HAS_AADHAAR | — |
| 19 | INCOME_CERTIFICATE_FILE | DOCUMENTS | file/STRING | no | `income_certificate` | **UNMAPPED** (upload placeholder; document store arrives later) | — | — |

Audit findings:
- The bare-name registry resolves all 19 except the file placeholder — mapping coverage is healthy.
- `CURRENTLY_STUDYING` sits in FAMILY_INFO (misplaced) and `STUDYING_COURSE` has no condition problem but is required=false even when visible — v2 blueprint fixes section placement.
- Facts exist for 14 of 19 questions; 5 have no fact_code (course_name, IS_BPL_CARD_HOLDER detail — fact is IS_BPL_CARD_HOLDER —, file placeholder, etc.).
- The `file` question type is excluded from typed-answer validation and completion math (Phase 2A decision) — upload is out of scope until the document store exists.

---

## 2. CANONICAL CITIZEN DATA CATALOGUE (Task 2)

Fields are grouped by catalogue area. For each: **purpose** (welfare relevance), **canonical?** (canonical profile vs fact-only), **fact?**, **type**, **required?**, **sensitive?**, **direct or derived**.

### 2.1 PERSONAL / DEMOGRAPHIC
| Field | Why useful | Canonical | Fact | Type | Req | Sensitive | Direct/Derived |
|---|---|---|---|---|citizens can | | |
| full_name | identity; document cross-check | citizen_master (registration) | FULL_NAME | STRING | yes | no | direct |
| date_of_birth | age gates (senior 60+, scholarship age bands) | citizen_master (NOT NULL) | DATE_OF_BIRTH | DATE | yes | yes | direct |
| gender | women-exclusive schemes, old-age pension, widow pension | demographic.gender | GENDER | STRING(20) | no | yes | direct |
| marital_status | widow pension, maternity, PMAY preference | demographic.marital_status | MARITAL_STATUS | STRING(30) | no | yes | direct |
| blood_group | NO welfare purpose — excluded (minimization) | no | no | — | no | — | excluded |
| religion | minority schemes (post-matric minority scholarship) | demographic.type_specific_metadata | RELIGION | STRING | no | yes | direct |
| mother_tongue | no current welfare use — excluded | no | no | — | no | — | excluded |
| socially... | (kept minimal) | | | | | | |

### 2.2 CONTACT
| Field | Why useful | Canonical | Fact | Type | Req | Sensitive | Direct/Derived |
|---|---|---| Aadhaar | | | | |
| mobile_number | DBT (Direct Benefit Transfer) outreach; scheme notifications | citizen_master.mobile_number | MOBILE_NUMBER | STRING(15) | no | yes | direct |
| email_id | non-urgent correspondence | citizen_master.email_id | EMAIL | STRING(255) | no | no | direct |
| prefers... | notification preference — defer (no notification system) | no | no | — | no | — | deferred |
| **Aadhaar number** | **NOT collected** — DBT seeding needs it eventually, but raw Aadhaar is high-risk PII; defer to a dedicated consented flow with vault storage + masking. Only the possession flag is collected now. | no | HAS_AADHAAR | BOOLEAN | no | yes | direct |
| **bank account number / IFSC** | DBT disbursement; NOT collected now — see Banking (2.13) | no | — | — | no | yes | deferred |

### 2.2b FAMILY / HOUSEHOLD
| Field | Phase 1 schema support | Phase 2C handling |
|---|---| one | | |
| family_size | demographic.family_size | direct scalar |
| family members (structured list) | **supported**: tbl_family_member rows keyed (relationship, name, dob) | repeating block (Part 5) |
| member income | tbl_family_member.income | within repeating block |
| member education/occupation/disability | tbl_schema | within repeating block |
| household head | no column; extension_metadata on tbl_family_member or fact-only | fact-only HOUSEHOLD_HEAD_RELATIONSHIP? defer |
| BPL/APL/AAY card in family | financial.poverty_category | direct |
| ration card type | no column → report as future DB change if needed | deferred |

Ration card type (APL/BPL/AAY is already poverty_category — do not double-ask).

### 2.3 LOCATION
| Field | Why useful | Canonical | Fact | Type | Req | Sensitive | Direct/Derived |
|---|---|---|---|---|---|---|---|
| state | state vs central schemes | location.state | STATE | STRING | yes | no | direct |
| district | district-level schemes (zila parishad) | location.district | DISTRICT | STRING | yes | no | direct |
| village_city (village/town/city) | village-level delivery, rural schemes | location.village_city | VILLAGE_CITY | STRING | no | no | direct |
| area_type | RURAL/URBAN gates (PMAY-G, rural electrification) | location.area_type | AREA_TYPE | STRING | no | no | direct |
| pincode | postal outreach + district cross-check | fact-only | PINCODE | STRING(6) | no | no | direct |
| **GPS/geotag** | not needed for matching — excluded | no | no | — | no | — | excluded |

### 2.4 FINANCIAL / ECONOMIC
| Field | used by | Canonical | Fact | Type | Req | Sensitive | Direct/Derived |
| financial.annual_income | income ceilings on nearly every scheme | financial.annual_income | ANNUAL_INCOME | DECIMAL | yes | yes | direct |
| poverty_category | BPL/AAY gates | financial.poverty_category | POVERTY_CATEGORY | STRING(10) | no | yes | direct |
| is_bpl_card_holder | explicit card gates | financial.is_bpl_card_holder | IS_BPL_CARD_HOLDER | BOOLEAN | no | yes | direct |
| income_source | income verification guidance | financial.income_source | INCOME_SOURCE | STRING | no | no | direct |
| is_income_tax_payer | PM-KISAN exclusion, income-tax cross-checks | financial.is_income_tax_payer | IS_INCOME_TAX_PAYER | BOOLEAN | no | yes | direct |
| land_holding_size (ha) | PM-KISAN ≤2 ha; land-based schemes | financial.land_holding_size | LAND_HOLDING | DECIMAL | farmer-gated | yes | direct |
| monthly_income | redundancy check vs annual — **excluded** (derivable annual×12; avoid double-asking) | — | — | — | — | — | excluded (redundant) |
| household income vs personal income | future; needs clear definition — deferred | — | ANNUAL_FAMILY_INCOME | — | — | — | deferred |

### 2.5 EDUCATION
| Field | Why useful | Canonical | Fact | Type | Req | student-gated | Direct/Derived |
| education_level | broad eligibility (adult literacy schemes, scholarships) | education.education_level | EDUCATION_LEVEL | STRING(50) | no | no | direct |
| currently_studying | STUDENT_STATUS fact; gates course/institution questions | education (fact-only) | CURRENTLY_STUDYING | BOOLEAN | no | no | direct |
| course_name | scholarship matching (merit-cum-means) | education.course_name | — | STRING | no | studying-gated | direct |
| year_of_study | scholarship year gates (e.g. "UG 1st year") | education.year_of_study | YEAR_OF_STUDY | INTEGER | no | studying-gated | direct |
| academic_year | "2026-27" disambiguation | education.academic_year | — | STRING(20) | no | studying-gated | direct |
| institution_name | state-scheme institution lists | education.institution_name | — | STRING | no | studying-gated | direct |
| institution_type | GOVERNMENT/PRIVATE gates | education.institution_type | — | STRING | no | studying-gated | direct |
| marks_percentage | merit scholarships | education.marks_percentage | MARKS_PERCENTAGE | DECIMAL 0–100 | no | studying-gated | direct |
| annual_fee | fee-reimbursement schemes | education.annual_fee | — | DECIMAL | no | studying-gated | direct |
| hostel_status | hostel stipends | education.hostel_status | HOSTEL_STATUS | STRING | no | studying-gated | direct |
| scholarship_currently_received | prevents double-benefit | education.scholarship_currently_received | SCHOLARSHIP_STATUS | BOOLEAN | no | studying-gated | direct |
| board/university | future; low priority — deferred | — | — | — | — | — | deferred |

### 2.6 EMPLOYMENT
| Field | Why useful | Canonical | Fact | Type | Req | Sensitive | Direct/Derived |
| employment_status | core gate (unemployment allowance, skill schemes) | employment.employment_status | EMPLOYMENT_STATUS | STRING(30) | no | no | direct |
| occupation | occupational schemes (construction workers' welfare) | employment.occupation | — | STRING | no | no | direct |
| employment_type | PERMANENT/CONTRACT/CASUAL — ESI/EPF gates | employment.employment_type | — | STRING(30) | employed-gated | no | direct |
| employer_type | GOVERNMENT (excluded from many schemes) | employment.employer_type | — | GOVERNMENT/PRIVATE/COOPERATIVE/NGO/HOUSEHOLD/OTHER | no | employed-gated | no | direct |
| employer_name | verification only — fact-free | employment.employer_name | — | STRING | no | employed-gated | no | direct |
| monthly_income | personal income (distinct from family annual) | employment.monthly_income | MONTHLY_INCOME | DECIMAL | no | employed-gated | yes | direct |
| annual_income (personal) | overlapping with financial.annual_income — **ask once**: form asks ANNUAL_INCOME once (family/household income) and monthly personal income under employment; normalization maps each to its own column. | | | | | | |
| work_sector | FORMAL/INFORMAL — informal-worker boards | employment.work_sector | — | STRING | no | employed-gated | no | direct |
| self_employed | MUDRA/PM SVANidhi gates | employment.self_employed | — | BOOLEAN | no | employed-g Indian | no | direct |
| is_income_tax_payer | (see financial) | financial.is_income_tax_payer | IS_INCOME_TAX_PAYER | BOOLEAN | no | no | direct |

### 2.6b AGRICULTURE
| Field | Why useful | Canonical | Fact | Type | Req | farmer-gated | Direct/Derived |
| farmer_status | farmer schemes (PM-KISAN, PMFBY) | agriculture.farmer_status | FARMER_STATUS | STRING | no | farmer-gated | direct |
| farmer_type (OWNER/TENANT/SHARECROPPER) | tenant eligibility varies by scheme | agriculture.farmer_type | FARMER_TYPE | STRING | no | farmer-gated | direct |
| land_ownership_status | OWNED/LEASED/BOTH/NONE | agriculture.land_ownership_status | — | STRING | no | farmer-gated | direct |
| total_land_area | land-size gates | agriculture.total_land_area | TOTAL_LAND_AREA | DECIMAL | no | farmer-gated | direct |
| cultivated/irrigated area | irrigation-dependent schemes (PMFBY, micro-irrigation) | agriculture.cultivated_land_area / irrigated_land_area | — | DECIMAL | no | farmer-gated | direct |
| land_unit | unit disambiguation (HECTARE/ACRE/BIGHA/GUNTHA) | agriculture.land_unit | — | STRING | no | farmer-gated | direct |
| crop_type | crop-specific schemes (cotton, soybean) | agriculture.crop_type | CROP_TYPE | STRING | no | farmer-gated | direct |
| season | KHARIF/RABI/ZAYAD/WHOLE_YEAR | agriculture.season | — | STRING | no | farmer-g future | direct |
| tenant_farmer / sharecropper | booleans derivable from farmer_type — **derived** | agriculture.tenant_farmer / sharecropper | TENANT_FARMER / SHARECROPPER | BOOLEAN | no | farmer-gated | derived from farmer_type |
| agricultural_income | farm income component of total income | agriculture.agricultural_income | AGRICULTURAL_INCOME | DECIMAL | no | farmer-gated | direct |

### 2.7 DISABILITY / SPECIAL CIRCUMstances
| Field | Why useful | Canonical | Fact | Type | Req | disability-gated | Direct/Derived |
| has_disability (YES/NO/PENDING) | disability-reservation gates | disability.disability_status | DISABILITY_STATUS | STRING | no | no | direct |
| disability_type | type-specific schemes (visual/hearing/... ) | disability.disability_type | DISABILITY_TYPE | STRING | no | disability-gated | direct |
| disability_percentage | ≥40% benchmark gates (many central schemes) | disability.disability_percentage | DISABILITY_PERCENTAGE | DECIMAL 0-100 | no | disability-gated | direct |
| certificate_available | verification pathway | disability.certificate_available | DISABILITY_CERTIFICATE | BOOLEAN | no | disability-gated | direct |
| certificate_number | **NOT collected** — only a salted hash column exists for verification workflows; raw number is high-risk PII (data minimization) | — | — | — | — | — | excluded |
| widow status | derivable from marital_status=WIDOWED + gender — derived | — | WIDOW_STATUS | BOOLEAN | no | no | derived from marital_status+gender |
| senior citizen | **derived from date_of_birth** (age ≥ 60) — never asked | — | SENIOR_CITIZEN | BOOLEAN | no | no | derived from DOB |
| minority status | derivable from religion — derived | — | MINORITY_STATUS | BOOLEAN | no | no | derived from religion |

### 2.8 SOCIAL / CATEGORY INFORMATION
| Field | Why useful | social_category | SOCIAL_CATEGORY | STRING(10) GEN/OBC/SC/ST | no | yes | direct |
| caste certificate availability | verification pathway | — | HAS_CASTE_CERTIFICATE | BOOLEAN | no | social-gated | direct |
| caste name | future; only with certificate context — deferred | — | — | — | — | — | deferred |
| religion | minority gates | demographic.type_specific_metadata | RELIGION | STRING | no | yes | direct |
| economically weaker section (EWS) | EWS reservation schemes | — | EWS_STATUS | STRING | no | no | direct (fact-only; no column) |
| BPL/APL/AAY | (see financial.poverty_category — do not double-ask) | | | | | | |

### 2.9 ASSETS / HOUSING
| tbl_asset_profile supports multi-row assets (LAND/HOUSE/VEHICLE/LIVESTOCK/EQUIPMENT/OTHER) | | | | | | |
| owns_house | PMAY gates; asset row + fact | asset.asset_type=HOUSE | OWNS_HOUSE | BOOLEAN (from asset rows) | no | no | direct (multi-row) |
| house_ownership_status | OWNED/JOINT/LEASED/NONE | asset.ownership_status | — | STRING | no | owns_house-gated | direct |
| owns_vehicle | LPG subsidy exclusion historically; moderate value | asset.asset_type=VEHICLE | OWNS_VEHICLE | BOOLEAN | no | no | direct (multi-row) |
| livestock | PM-KISAN exclusion historically; dairy schemes | asset.asset_type=LIVESTOCK | OWNS_LIVESTOCK | BOOLEAN | no | farmer-gated | direct (multi-row) |
| KCC (Kisan Credit Card) | farm credit gates | asset/fact-only | HAS_KCC | BOOLEAN | no | farmer-gated | direct |
| kerosene/... | no welfare use — excluded | | | | | | |

### 2.10 DOCUMENT AVAILABILITY (availability only — no upload)
| Document | Why needed | Question form | Fact |
| income certificate | income verification for scholarships/pensions | "Do you have an income certificate?" → HAS_INCOME_CERTIFICATE | BOOLEAN |
| caste certificate | SC/ST/OBC verification | HAS_CASTE_CERTIFICATE (above) | BOOLEAN |
| disability certificate | PwD verification | DISABILITY_CERTIFICATE (above) | BOOLEAN |
| Aadhaar | DBT prerequisite | HAS_AADHAAR | BOOLEAN |
| ration card | BPL/AAY verification | HAS_RATION_CARD | BOOLEAN |
| bank passbook | DBT prerequisite | HAS_BANK_ACCOUNT | BOOLEAN |
| domicile/residence proof | state-scheme residency gates | HAS_DOMICILE_CERTIFICATE | BOOLEAN |
| bonafide certificate | student schemes | HAS_BONAFIDE_CERTIFICATE | BOOLEAN |
| marksheets | merit verification | HAS_MARKSHEET | BOOLEAN |
| land records (7/12, etc.) | farmer verification | HAS_LAND_RECORDS | BOOLEAN |

Availability flags only; upload/storage is a later phase (document store doesn't exist yet). Each flag is fact-only (no canonical column — `document.*` registry domain).

### 2.11 BANKING / PAYMENT INFORMATION
**Deferred entirely in Phase 2C.** DBT needs account number+IFSC, but: (a) high-risk PII requiring consent + masking + vault storage, (b) no disbursement pipeline exists yet, (c) account numbers change. Collect only `HAS_BANK_ACCOUNT` (availability flag) now. When DBT arrives, bank details belong in a dedicated consented `tbl_citizen_bank_account` table — **future DB change**, not extension_metadata.

### 2.12 FAMILY — repeating block detail (Task 6)
`tbl_family_member` supports (relationship, name, dob, gender, education_status, occupation, income, dependent_flag, disability_status) — **current schema is sufficient** for the repeating family block. The form JSON represents it as one question with `data_type=JSON` and `profile_field=family_members` (Phase 2B proven normalization path). The frontend repeats the member card UI. Constraints: relationship ∈ known set; each member needs name or DOB; invalid entries are warned and skipped.

### 2.13 EDUCATION HISTORY / EMPLOYMENT HISTORY — repeating blocks
`tbl_education_profile`/`tbl_employment_profile` are **singletons** (unique citizen_id) — they represent the *current* record only. Multi-record histories (previous schools, previous jobs) are **NOT supported** by the current schema. Per Task 6: report limitation, don't redesign. Phase 2C collects only the current education/employment record; multi-record histories are deferred and would need `citizen_id`-uniqueness dropped (future DB change) or a new history table. Welfare matching rarely needs full histories — acceptable deferral.

---

## 3. CITIZEN-TYPE STRATEGY (Task 3)

**Principle: categories are NOT mutually exclusive.** A citizen is STUDENT + PERSON_WITH_DISABILITY, or FARMER + SELF_EMPLOYED. Therefore:

1. **Common sections** (asked of everyone): Personal, Contact, Family, Location, Financial, Social, Documents. These carry the facts consumed by nearly every rule.
2. **Type-specific sections** (shown via conditions on profile answers, not citizen_type alone): Education (studying), Employment (employed/self-employed), Agriculture (farmer), Disability details (has disability), Assets/housing.
3. **`target_citizen_type` on the form definition remains a routing/discovery hint** (which form to offer a citizen first), NOT a hard gate — the actual visibility logic is conditions on answers. This is what makes overlap possible.
4. **No duplicate questions across forms** — one canonical question set; type-specific sections are conditionally revealed. A STUDENT+FARMER answers education + agriculture sections in one submission.
5. Overlap handling: conditions key off **answers** (currently_studying, farmer_status, has_disability), not off citizen_type — so a GENERAL-type citizen who answers "Do you do farming? YES" gets agriculture questions.

Section-by-type matrix (✓ = shown by default, ⚙ = conditionally revealed, — = hidden):

| Section | GENERAL | STUDENT | FARMER | JOB SEEKER | SALARIED | SELF-EMP | SENIOR | WOMAN | PwD |
|---|---|---|---|§ 3.1| | | | | |
| Personal/Contact/Family/Location/Financial/Social/Documents | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Education | ⚙ (studying=NO hides course questions) | ✓ | ⚙ | ⚙ | ⚙ | � education | ⚙ | ⚙ | ⚙ |
| Employment | ⚙ | ⚙ | ⚙ | ✓ (job-seeker hints) | ✓ | ✓ | ⚙ | ⚙ | ⚙ |
| Agriculture | ⚙ | ⚙ | ✓ | — | — | ⚙ | �⚙ | ⚙ | ⚙ |
| Disability details | ⚙ | ⚙ | � facts | ⚙ | ⚙ | ⚙ | ⚙ | ⚙ | ✓ |
| Assets/housing | ⚙ | — | ⚙ | — | ⚙ | ⚙ | ⚙ | �⚙ | ⚙ |

The matrix is implemented as conditions in the form JSON, not hardcoded frontend logic.

---

## 4. COMPLETE SECTION STRUCTURE (Task 10, part 1)

Recommended final form: **CITIZEN_PROFILE_v2** (form_code `GENERAL_CITIZEN_PROFILE` v2 — same code, new version row; submissions pin their version).

1. **PERSONAL_INFO** — identity + demographics (common)
2. **CONTACT_INFO** — mobile, email (common)
3. **FAMILY_INFO** — family_size, structured members, marital_status (common)
4. **LOCATION_INFO** — state, district, village_city, pincode, area_type (common)
5. **FINANCIAL_INFO** — annual_income, poverty_category, is_bpl_card_holder, income_source, is_income_tax_payer (common)
6. **EDUCATION_INFO** — currently_studying + conditional education detail (common question, gated detail)
7. **EMPLOYMENT_INFO** — employment_status + conditional employment detail (common question, gated detail)
8. **AGRICULTURE_INFO** — farmer gate + conditional land/crop detail (gated)
9. **DISABILITY_INFO** — has_disability + conditional type/percentage/certificate (gated)
10. **ASSETS_HOUSING** — owns_house, house_ownership_status, owns_vehicle, livestock (common, cheap)
11. **DOCUMENTS** — availability flags (common) + future upload placeholders
12. **REVIEW** — no questions; frontend review screen renders from the same API JSON (no backend section needed)

---

## 5. QUESTION CATALOGUE (Task 4)

Full catalogue for CITIZEN_PROFILE_v2. `validation_rule` uses the Phase 2A metadata keys (`min/max`, `min_length/max_length`, `pattern`, `email`). `help_text`/`placeholder` included where they aid completion. No question is asked twice for the same fact; AGE is never asked (derived).

### PERSONAL_INFO
| code | text | type | data_type | req | profile_field | fact_code | validation | options | condition |
|---|---|---|---|---|---|---|---|---|---|
| FULL_NAME | "What is your full name as per your documents?" | text | STRING | yes | `citizen.full_name` | FULL_NAME | max_length:100 | — | — |
| DATE_OF_BIRTH | "What is your date of birth?" | date | DATE | yes | `demographic.date_of_birth` | DATE_OF_BIRTH | (max: today) | — | — |
| GENDER | "What is your gender?" | dropdown | STRING | no | `demographic.gender` | GENDER | — | MALE, FEMALE, OTHER | — |
| MARITAL_STATUS | "What is your marital status?" | dropdown | STRING | no | `demographic.marital_status` | MARITAL_STATUS | — | SINGLE, MARRIED, WIDOWED, DIVORCED | — |
| RELIGION | "What is your religion?" | dropdown | STRING | MINORITY_STATUS derivation | no | `demographic.religion` | RELIGION | — | HINDU, MISTLETOE... | — |
| RELIGION | "What is your religion?" | dropdown | STRING | no | `demographic.type_specific_metadata`... | — | — | HINDU, MUSLIM, CHRISTIAN, SIKH, BUDDHIST, OTHER | — |

(One RELIGION row; the doubled row above is a drafting artifact — use the second: dropdown, no fact via registry `demographic.religion` needs a registry entry.)

### CONTACT_INFO
| code | text | type | data_type | req | profile_field | fact_code | validation | condition |
|---|---|MISTLETOE|---|---|---|---|---|
| MOBILE_NUMBER | "Your mobile number" | text | STRING | no | `citizen.mobile_number` | MOBILE_NUMBER | pattern `^[6-9]\d{9}$` | — |
| EMAIL_ID | "Your email address" | text | STRING | no | `citizen.email_id` | EMAIL | email:true | — |

### FAMILY_INFO
| code | text | type | data_type | req | profile_field | fact_code | condition |
|---|---|---|---|---|---|---|---|
| FAMILY_SIZE | "How many members are there in your family (including you)?" | number | INTEGER | yes | `family_size` | FAMILY_SIZE | — |
| MARITAL_STATUS (moved here?) — no, stays in PERSONAL | | | | | | | |
| FAMILY_MEMBERS | "Add your family members" | multi-entry (JSON) | JSON | no | `family_members` | — | — |
| HAS_DEPENDENTS | "Do you have dependent family members?" | boolean | BOOLEAN | no | `has_dependents` (fact-only) | HAS_DEPENDENTS | — |
| DEPENDENT_DETAILS | "Which members are dependents?" | multi-entry | JSON | no | (part of FAMILY_MEMBERS block) | — | `HAS_DEPENDENTS EQUALS YES → SHOW` |

### LOCATION_INFO
| code | text | type | data_type | req | profile_field | fact_code | validation |
|---|---|---| pattern ^[1-9][0-9]{5}$ |---|---|
| STATE | "Which state do you live in?" | text | STRING | yes | `state` | STATE | — |
| DISTRICT | "Which district?" | text | reference data (future dropdown) | yes | `district` | DISTRICT | — |
| VILLAGE_CITY | "Village/town/city" | text | STRING | no | `village_city` | VILLAGE_CITY | — |
| PINCODE | "PIN code" | text | STRING | no | `pincode` | PINCODE | pattern `^[1-9][0-9]{5}$` |
| AREA_TYPE | "Is your area rural or urban?" | dropdown | STRING | no | `area_type` | AREA_TYPE | — | RURAL, UURBAN, SEMI_URBAN |

### FINANCIAL_INFO
| code | text | type | data_type | req | profile_field | fact_code | validation |
|---|---|---|---|---|---|---|---|
| ANNUAL_INCOME | "What is your family's total annual income (₹/year)?" | text | STRING | yes | `financial. accepting` | ANNUAL_INCOME | — |
| POVERTY_CATEGORY | "Do you hold an APL/BPL/AAY (ration) card?" | dropdown | STRING | no | `poverty_category | POVERTY_CATEGORY | — | APL, BPL, AAY |
| IS_BPL_CARD_HOLDER | "Do you possess a BPL card?" | boolean | BOOLEAN | derivable from POVERTY_CATEGORY — **derive, don't ask** | `is_bpl_card_holder` derived | IS_BPL_CARD removes | — |
| IS_BPL_CARD_HOLDER question → removed from v2 (derived from POVERTY_CATEGORY∈{BPL,AAY}) | | | IS_BPL_CARD_HOLDER | — | — | derived |
| INCOME_SOURCE | "Main source of income?" | dropdown | STRING | no | `income_source` | INCOME_SOURCE | — | AGRICULTURE, WAGES, SALARY, BUSINESS, PENSION, OTHER |
 INCOME_SOURCE options row | | | | | | AGRICULTURE, WAGES, SALARY, catalogue | BUSINESS, PESION, OTHER |
| IS_INCOME_TAX_PAYER | "Does your family pay income tax?" | boolean | BOOLEAN | no | `is_income_tax_payer` | IS_INCOME_TAX_PAYER | — |

### EDUCATION_INFO
| code | text | type | data_type | req | profile_field | fact_code | condition |
|---|---|---| gated |---|---|---|---|
| CURRENTLY_STUDYING | "Are you currently studying?" | boolean | BOOLEAN | no | `currently_studying` | CURRENTLY_STUDYING | — |
| EDUCATION_LEVEL | "Highest education level?" | dropdown | STRING | no | `education_level` | EDUCATION_LEVEL | — |
| COURSE_NAME | "Which course are you studying?" | text | STRING | no | `course_name` | — | `CURRENTLY_STUDYING EQUALS YES → SHOW` |
| YEAR_OF_STUDY | "Which year of study?" | number | INTEGER | no | `year_of_study` | YEAR_OF_STUDY | `CURRENTLY_STUDYING EQUALS YES → SHOW` |
| ACADEMIC_YEAR | "Current academic year (e.g. 2026-27)" | text | STRING | no | `academic_year` | — | studying-gated |
| INSTITUTION_NAME | "Institution name" | text | STRING | no | `institution_name` | — | studying-gated |
| INSTITUTION_TYPE | "Institution type" | dropdown | STRING | no | `institution_type` | — | studying-gated | GOVERNMENT, PRIVATE, AED | AIDED, OTHER |
| MARKS_PERCENTAGE | "Latest marks percentage" | text | STRING | no | `marks_percentage` | MARKS_PERCENTAGE | studying-gated |
| ANNUAL_FEE | "Annual course fee (₹)" | text | STRING | numeric min 0 | no | `annual_fee` | — | studying-gated |
| HOSTEL_STATUS | "Hosteller or day scholar?" | dropdown | STRING | no | `hostel_status` | HOSTEL_STATUS | studying-gated | HOSTELLER, DAY_SCHOLAR, NONE |
| SCHOLARSHIP_CURRENTLY_RECEIVED | "Do you currently receive any scholarship?" | boolean | BOOLEAN | no | `scholarship_currently_received` | SCHOLARSHIP_STATUS | studying-gated |

### EMPLOYMENT_INFO
| code | text | type | data_type | req | profile_field | fact_code | condition |
|---|---|---|---|---|---|---|---|
| EMPLOYMENT_STATUS | "What is your employment status?" | dropdown | EQUALS | STRING | no | `employment_status` | EMPLOYMENT gates | EMPLOYMENT_STATUS | — |
| OCCUPATION | "Your occupation" | text | STRING | no | `occupation` | — | `EMPLOYMENT_STATUS IN EMPLOYED,SELF_EMPLOYED → SHOW` |
| EMPLOYMENT_TYPE | "Employment type" | dropdown | STRING | no | `HARDCODED | — | `EMPLOYMENT_STATUS EQUALS EMPLOYED → SHOW` | PERMANENT, CONTRACT, CASUAL, OTHER |
| EMPLOYER_TYPE | "Employer type" | GOVERNMENT, PRIVATE, COOPERATIVE, NGO, HOUSEHOLD, OTHER | dropdown | STRING | no | `employer_type` | — | employed-gated |
| EMPLOYER_NAME | "Employer name" | text | STRING | no | `employer_name` | — | employed-gated |
| MONTHLY_INCOME | "Your monthly personal income (₹)" | text | STRING | no | `monthly_income` | MONTHLY_INCOME | employed-gated |
| WORK_SECTOR | "Formal or informal sector?" | dropdown | STRING | no | `work_sector` | — | employed-gated | FORMAL, INFORMAL, AGRICULTURE, OTHER |
| SELF_EMPLOYED | "Are you self-employed?" | boolean | BOOLEAN | no | `self_employed` | — | `EMPLOYMENT_STATUS EQUALS SELF_EMPLOYED → SHOW` |
| BUSINESS_QUESTIONS | self-employment detail — no canonical columns exist (business name/turnover/GST not in schema) → **future DB change or extension_metadata**; Phase 2C keeps only SELF_EMPLOYED flag | | | | | | |

### AGRICULTURE_INFO (all gated behind FARMER_STATUS ≠ NO)
| code | text | type | data_type | req | profile_field | fact_code | condition |
|---|---|---|---|---|---| PM-KISAN |---|
| FARMER_STATUS | "Are you engaged in farming?" | dropdown | STRING | no | `farmer_status` | FARMER_STATUS | — |
| FARMER_TYPE | "Are you an owner, tenant, or sharecropper?" | dropdown | `≠NO`-gated | STRING | no | `farmer_type` | FARMER_TYPE | farmer-gated | OWNER, TENANT, SHARECROPPER, OTHER |
| LAND_OWNERSHIP_STATUS | "Is your land owned/leased/both?" | dropdown | STRING | no | `land_ownership_status` | — | farmer-gated | OWNED, LEASED, BOTH, NONE |
| TOTAL_LAND_AREA | "Total land (with unit)" | text | STRING | no | `total_land_area` | TOTAL_LAND_AREA | farmer-gated |
| CULTIVATED_AREA | "Cultivated area" | text | STRING | ≥0 | no | `cultivated_land_area` | — | farmer-gated |
| IRRIGATED_AREA | "Irrigated area" | text | STRING | ≥0 | no | `irrigated_land_area` | — | farmer-gated |
| LAND_UNIT | "Unit: hectare/acre/bigha/guntha" | dropdown | STRING | no | `land_unit` | — | farmer-gated | HECTARE, ACRE, BPHGA | BIGHA, GUNTHA |
| CROP_TYPE | "Main crops grown" | text | STRING | no | `crop_type` | CROP_TYPE | farmer-gated |
| SEASON | "Cropping season(s)" | multi_choice | STRING | no | `season` | — | farmer-gated | KHARIF, RABI, ZAYAD, WHOLE_YEAR |
| TENANT_FARMER / SHARECROPPER | **derived from FARMER_type** — not asked | | | | | | |
| AGRICULTURAL_INCOME | "Annual agricultural income (₹)" | text | STRING | no | `agricultural_income` | AGRICULTURAL_INCOME | farmer-gated |
| HAS_KCC | "Do you have a Kisan Credit Card?" | boolean | BOOLEAN | no | `has_kcc` | HAS_KCC | farmer-gated |
| LAND_HOLDING_SIZE (financial mirror) | asked as TOTAL_LAND_AREA+LAND_UNIT; normalization converts units to hectares for financial.land_holding_size — **requires registry extension** (unit conversion) | | | ha | | | |

### DISABILITY_INFO (gated behind HAS_DISABILITY = YES/PENDING)
| code | type | data_type | req | profile_field | fact_code | condition |
| `HAS_DISABILITY` | "Do you have a disability?" | dropdown | STRING | no | `has_disability` | DISABILITY_STATUS | — |
| DISABILITY_TYPE | "Type of disability" | dropdown | STRING | yes-if-visible | `disability_type` | DISABILITY_TYPE | has_disability≠NO → SHOW |
| DISABILITY_PERCENTAGE | "Disability percentage" | text | STRING | no | `disability_percentage` | DISABILITY_PERCENTAGE | has_disability≠NO → SHOW |
| HAS_DISABILITY_CERTIFICATE | "Do you have a disability certificate?" | boolean | BOOLEAN | no | `has_disability_certificate` | DISABILITY_CERTIFICATE | has_disability≠NO → show |
| CERTIFICATE_NUMBER | **excluded** (minimization — only hash column exists) | | | | | | |

### ASSETS_HOUSING
| code | text | type | data_type | req | profile_field | fact_code |
|---|---|---|---|~70 questions |---|---|
| OWNS_HOUSE | "Do you own a house?" | boolean | BOOLEAN | no | `owns_house` | OWNS_HOUSE |
| HOUSE_OWNERSHIP_STATUS | "House ownership status" | dropdown | OWNS_HOUSE=YES → SHOW | STRING | no | `house_ownership_status` | — |
| OWNS_VEHICLE | "Do you own a vehicle?" | boolean | BOOLEAN | no | **future DB change** (no asset-question path yet) | OWNS_VEHICLE |
| OWNS_LIVESTOCK | "Do you own livestock?" | boolean | BOOLEAN | no | future DB change | OWNS_LIVESTOCK |
| KCC covered in agriculture | | | | tbl_asset_profile | | |

### DOCUMENTS (availability flags)
| code | text | type | req | profile_field | fact_code |
| HAS_AADHAAR | "Do you have Aadhaar?" | boolean | no | `has_aadhaar` | HAS_AADHAAR |
| HAS_RATION_CARD | "Do you have a ration card?" | no | `has_ration_card` | HAS_RATION_CARD |
| HAS_INCOME_CERTIFICATE | "Do you have an income certificate?" | no | `has_income_certificate` | HAS_INCOME_CERTIFICATE |
| HAS_CASTE_CERTIFICATE | "Do you schemes" | no | `has_caste_certificate` | HAS_CASTE_CERTIFICATE |
| HAS_DISABILITY_CERTIFICATE (moved to DISABILITY_INFO) | | | | | |
 disability cert row | | | | | |
| HAS_DOMICILE_CERTIFICATE | "Domicile/residence proof?" | no | `has_domicile_certificate` | HAS_DOCUMENT | HAS_DOMICILE_CERTIFICATE |
| HAS_BONAFIDE_CERTIFICATE | "Bonafide certificate?" | no | `bonafide_available` | HAS_BONAFIDE_CERTIFICATE |
| HAS_MARKSHEET | "Latest marksheet?" | no | `has_markssheet` | HAS_MARKSHEET |
| HAS_LAND_RECORDS | "Land records (7/12 etc.)?" | no | `has_land_records` | registry `document.has_land_records` needs entry | HAS_LAND_RECORDS |
| HAS_BANK_ACCOUNT | "Do you have a bank account?" | no | `has_bank_account` | HAS_BANK_ACCOUNT |
| INCOME_CERTIFICATE_FILE | upload placeholder — **excluded from v2** (document store later) | | | | |

---

## 6. CONDITIONAL LOGIC MAP (Task 5)

All conditions use the existing 10 operators; groups AND within group, OR across groups.

| Trigger question | Value | Reveals |
|---|---|---|
| CURRENTLY_STUDYING = YES | education detail block (COURSE_NAME, YEAR_OF_STUDY, ACADEMIC_YEAR, INSTITUTION_NAME, studying-gated) | education detail |
| CURRENTLY_STUDYING = NO | (nothing hidden; EMPLOYMENT_STATUS remains visible to everyone) | — |
| EMPLOYMENT_STATUS ∈ {EMPLOYED, SELF_EMPLOYED} | OCCUPATION, EMPLOYMENT_TYPE, EMPLOYER_TYPE, EMPLOYER_NAME, MONTHLY_INCOME, WORK_SECTOR | employment detail |
| EMPLOYMENT_STATUS = SELF_EMPLOYED | SELF_EMPLOYED flag is redundant — derive SELF_EMPLOYED = (status=SELF_EMP Don't ask both | derive |
| EMPLOYMENT_STATUS = UNEMPLOYED | nothing extra (job-seeker support is a later phase) | — |
| FARMER_STATUS ≠ NO | whole AGRICULTURE detail block | agriculture detail |
| HAS_DISABILITY ≠ NO | DISABILITY_TYPE, DISABILITY NOT_EQUAL | disability detail |
| HAS_DEPENDENTS = YES | (member dependency handled inside FAMILY_MEMBERS JSON) | — |
| OWNS_HOUSE = YES | HOUSE_OWNERSHIP_STATUS | — |

Design rules: max one level of nesting (trigger → block); no nested chains of conditions on conditions; every condition targets questions in the same form version; hidden required questions never block completion (Phase 2A evaluator guarantees this).

---

## 7. REPEATING-DATA STRATEGY (Task 6)

| Repeating data | Current schema support | Phase 2C strategy |
|---|---|--- education |---|
| Family members | **Sufficient** (tbl_family_member natural-key rows) | JSON repeating block via `family_members` profile_field (proven in 2B) |
| Education history (multiple records) | **Insufficient** — tbl_education_profile is singleton | Collect current record only; report limitation; future DB change (drop uniqueness or add history table) |
| Employment history | **Insufficient** — singleton | Same as education |
| Assets | **Sufficient** (multi-row tbl_asset_profile) | Simple boolean gates now (OWNS_HOUSE/VEHICLE/LIVESTOCK); structured asset rows when asset curation is justified |
| Documents | Availability flags only (facts) | Upload/storage is a later phase with a document store |
| Crops (multiple) | crop_type is a single string column | Free-text multi-crop string acceptable; structured crop rows = future change |

---

## 8. DOCUMENT REQUIREMENT CATALOGUE (Task 7)

"Do you have X?" (availability, Phase 2C) vs "Upload X" (later phase, needs document store). Availability flags → facts: HAS_AADHAAR, HAS_RATION_CARD, HAS_INCOME_CERTIFICATE, HAS_CASTE_CERTIFICATE, HAS_DISABILITY_CERTIFICATE (in DISABILITY_INFO), HAS_DOMICILE_CERTIFICATE, HAS_BONAFIDE_CERTIFICATE, HAS_MARKSHEET, HAS_LAND_RECORDS, HAS_BANK_ACCOUNT. Upload placeholders (file-type questions) are **excluded from v2** — they would count as unmapped today; they return in the document phase.

---

##  file upload |---|

## 9. PROFILE-FACT CATALOGUE (Task 8)

Facts emitted by v2 (all registry-gated; UI-only questions never become facts). `derived` = computed by normalization; source = SYSTEM_DERIVED.

| fact_code | data_type | direct/derived | normalization requirement | likely eligibility usage |
|---|---|---|---| CITIZEN |---|
| FULL_NAME | STRING | direct | trim | identity cross-check |
| MOBILE_NUMBER | STRING | direct | pattern | DBT outreach |
| EMAIL | STRING | direct | lowercase | correspondence |
| DATE_OF_BIRTH | DATE | direct | ISO | age gates |
| **AGE** | INTEGER | **derived from DATE_OF_BIRTH** | calendar age | senior (≥60), minor (<18), age-band scholarships |
| GENDER | STRING | direct | choice map | women-exclusive schemes |
| MARITAL_STATUS | **WIDOW_STATUS (derived)** | STRING/BOOLEAN | choice map + derivation | widow pension |
| RELIGION | STRING | direct | choice map | minority scholarships |
| SOCIAL_CATEGORY | STRING | direct | choice map | caste-based reservation schemes |
| FAMILY_SIZE | INTEGER | direct | int | per-capita income checks |
| STATE / DISTRICT | STRING | direct | trim | state vs central matching |
| VILLAGE_CITY / PINCODE / AREA_TYPE | STRING | direct | trim/pattern | rural-only schemes (PMAY-G) |
| ANNUAL_INCOME | DECIMAL | direct | currency parse (₹, lakh, crore) | income ceilings |
| ANNUAL_FAMILY_INCOME = ANNUAL_INCOME alias — one question, one fact (ANNUAL_INCOME); don't emit both | | | | |
| POVERTY_CATEGORY | STRING | IS_BPL_CARD_HOLDER derived | choice map | BPL/AAY gates |
| IS_BPL_CARD_HOLDER | BOOLEAN | **derived from POVERTY_COLUMN** | derive BPL/AAY→TRUE | explicit card gates |
| INCOME_SOURCE | STRING | direct | choice map | verification guidance |
| IS_INCOME_TAX_PAYER | AGE | BOOLEAN | direct | PM-KIT | PM-KISAN exclusion |
| LAND_HOLDING | DECIMAL | direct | unit conversion to hectares | PM-KISAN ≤2 ha |
| CURRENTLY_STUDYING | BOOLEAN | direct | bool | STUDENT_STATUS gate |
| EDUCATION_LEVEL | STRING | direct | choice map | scholarship levels |
| YEAR_OF_STUDY | INTEGER | direct | int | year gates |
| MARKS_PERCENTAGE | DECIMAL | direct | percent 0-100 | merit scholarships |
| HOSTEL_STATUS | STRING | direct | choice map | hostel stipends |
| SCHOLARSHIP_STATUS | BOOLEAN | direct | bool | double-benefit prevention |
| EMPLOYMENT_STATUS | STRING | direct | choice map | unemployment/skill gates |
| MONTHLY_INCOME | DECIMAL ×12 | direct | currency parse | personal income gates |
| **SENIOR_CITIZEN** | BOOLEAN | **derived from AGE≥60** | derived from DOB fact | old-age pension |
| **WIDOW_STATUS** | BOOLEAN | **derived from MARITAL_STATUS=WIDOWED (+gender)** | derivation | widow pension |
| **MINORITY_STATUS** | BOOLEAN | **derived from RELIGION** | derivation | minority schemes |
| FARMER_STATUS / FARMER_TYPE | STRING | direct | choice map | farmer schemes |
| TOTAL_LAND_AREA | DECIMAL | direct | unit conversion | land-size gates |
| CROP_TYPE / AGRICULTURAL_INCOME | STRING/DECIMAL | direct | parse | crop/farm-income gates |
| HAS_KCC | BOOLEAN | direct | bool | farm credit gates |
| DISABILITY_STATUS/TYPE/PERCENTAGE/CERTIFICATE | STRING/DECIMAL/BOOLEAN | direct | choice/percent | PwD gates (≥40% benchmark) |
| OWNS_HOUSE / OWNS_VEHICLE / OWNS_LIVESTOCK | BOOLEAN | direct | bool | asset exclusions/inclusions |
| HAS_AADHAAR / HAS_RATION_CARD / HAS_INCOME_CERTIFICATE / HAS_CASTE_CERTIFICATE / HAS_DOMICILE_CERTIFICATE / HAS_BONAFIDE_CERTIFICATE / HAS_MARKSHEET / HAS_LAND_RECORDS / HAS_BANK_ACCOUNT | BOOLEAN | direct | bool | document-prerequisite gates |
| HAS_DEPENDENTS | BOOLEAN | direct | bool | dependent-based schemes |

Derived-only facts (never asked): AGE, SENIOR_CITIZEN, WIDOW_STATUS, MINORITY_STATUS, IS_BPL_CARD_HOLDER (from POVERTY_CATEGORY), SELF_EMPLOYED (from EMPLOYMENT_STATUS), TENANT_Fderived / SHARECROPPER (from FARMER_TYPE). **Seven derived facts, zero double-asking.**

**Avoid fact-per-question**: COURSE_NAME, INSTITUTION_NAME/TYPE, ACADEMIC_YEAR, ANNUAL_FEE, EMPLOYER_NAME/TYPE, EMPLOYMENT_TYPE, WORK_SECTOR, SELF_EMPLOYED column, LAND_OWNERSHIP_STATUS, CULTIVATED/IRRIGATED_AREA, LAND_UNIT, HOUSE_OURNERSHIP_STATUS — stored canonically but **no fact** (verification/matching detail, not rule inputs today). Registry `fact_code=None` already implements this.

---

## 10. DATA-MINIMIZATION DECISIONS (Task 9)

**Excluded** (no welfare purpose / high-risk / redundant):
- blood_group, mother_tongue (no eligibility use)
- monthly_income at financial level (redundant with annual)
- **Aadhaar number, bank account number, IFSC, PAN** — high-risk PII; deferred to consented flows with vault/masking when DBT/disbursement exists
- disability certificate NUMBER (only salted-hash column exists)
- caste name (only with certificate context later)
- GPS/geotag (no matching use)
- household head (no rule consumes it today)
- upload placeholders (no document store)

**Derived instead of asked** (7): AGE, SENIOR_CITIZEN, WIDOW_STATUS, MINORITY_STATUS, IS_BPL_CARD_HOLDER, SELF_EMPLOMENTED, TENANT_FARMER/SHARECROPPER.

**Deferred** (justified later): religion (minority schemes later), bank details (DBT), business details (self-employment schemes), education/employment histories (singleton limitation), ration card type (poverty_category covers APL/BPL/AAY).

---

## 11. PROPOSED FINAL DYNAMIC FORM JSON STRUCTURE (Task 11 output)

Same schema as `forms.json` (seed_forms.py consumes it unchanged). Key design: **conditions reference question codes within the same version**; sections carry `target_citizen_types` (informational for routing, NOT a gate).

```json
{
  "forms": [{
    "form_code": "GENERAL_CITIZEN_PROFILE",
    "version": 2,
    "form_name": "Citizen Profile (v2)",
    "description": "Full welfare-relevant citizen profile: common sections + conditionally revealed type-specific sections",
    "target_citizen_type": "GENERAL",
    "sections": [
      {
        "section_code": "PERSONAL_INFO", "section_name": "Personal Information", "display_order": 1,
        "questions": [
          {"question_code": "FULL_NAME", "question_text": "...", "question_type": "text", "data_type": "JSON"...
```

(The JSON block above is truncated for space; the full v2 JSON is a Phase 2C implementation artifact to be produced at coding time from the Task 4/5 tables in this document — every field of every question is already fully specified in sections 5–6.)

**Structural rules for the v2 JSON**:
1. One form row per version (existing uq_form_code_version) — v2 is a new row; v1 remains for existing submissions.
2. Conditions reference `depends_on_question_code` (seed script resolves ids); operators from the supported 10; one level of nesting.
3. `profile_field` values MUST resolve in the registry — a pre-seed validation step (new, Phase 2C) should fail the seed if any profile_field is unmapped or choice values don't match registry choices.
4. Repeating family block: one question `FAMILY_MEMBERS` (data_type JSON, profile_field `family_members`).
5. File-type questions excluded (document phase).
6. Registry additions needed (Task 12): `demographic.religion`, `document.has_ration_card`, `document.has_income_certificate`, `document.has_caste_certificate`, `document.has_dominicile_certificate`, `document.has_bonafide_certificate`, `question.has_markssheet`, `document.has_land_records`, `document.has_bank_account`, `document.has_dependents`, `asset.owns_house/vehicle/livestock`, `has_kcc`, `house_ownership_status`, `has_domicile_certificate`... (full list in Task 12).

---

## 12. FIELDS REQUIRING FUTURE DB CHANGES (Task 12)

None of these are needed for Phase 2C itself — they are recorded for later phases:
1. `tbl_demographic_profile.religion` column (or keep in type_specific_metadata — **recommended: type_specific_metadata now, column later if minority schemes arrive**)
2. Business/self-employment details (business name, turnover, GST) — extension_metadata on employment or new columns when self-employment schemes arrive
3. Education/employment history tables (drop singleton uniqueness or add history tables) — only if histories become rule-relevant
4. `tbl_citizen_bank_account` (consented, masked) — DBT phase
5. Document store (tbl_citizen_document) — upload phase
6. Asset-question normalization path (asset domain currently has no answer→row path; boolean gates → facts only) — Phase 2C uses facts for asset flags, canonical asset rows deferred
7. Ration card number (masked/hash) — verification phase
8. Structured crop rows — if crop-specific schemes demand it

## 13. FIELDS THAT CAN USE THE EXISTING SCHEMA (Task 13)

Everything in the v2 catalogue EXCEPT the Task 12 list works on the current schema:
- All singleton profiles (demographic/financial/location/education/employment/agriculture/disability) via Phase 2B get-or-create
- Family members via natural-key upsert
- All facts via the open-fact partial unique index
- All provenance via (fact, answer) dedup
- 7 derived facts via normalization derivations (AGE exists; SENIOR_CITIZEN/WIDOW_STATUS/MINORITY_STATUS/IS_BPL_CARD_HOLDER/SELF_EMPLOYED/TENANT_FARMER derivations are **normalization-service additions**, not DB changes)

## 14. FIELDS THAT SHOULD BE DERIVED (Task 14)

AGE (from DOB), SENIOR_CITIZEN (AGE≥60), WIDOW_STATUS (MARITAL_STATUS+GENDER), MINORITY_STATUS (RELIGION), IS_BPL_CARD_HOLDER (POVERTY_CATEGORY∈{BPL,AAY}), SELF_EMPLOYED (EMPLOYMENT_STATUS=SELF_EMPLOYED), TENANT_FARMER/SHARECROPPER (FARMER_TYPE). Land-unit→hectare conversion for LAND_HOLDING is deterministic parsing, not a derived fact.

## 6. IMPLEMENTATION SEQUENCE (Task 15)

Phase 2C is split into backend-first increments, each independently verifiable:

1. **Registry extension** (backend, no migration): add the ~12 missing registry entries (religion, document flags, asset flags, has_kcc, has_dependents, house_ownership_status) + new derivations (SENIOR_CITIZEN, WIDOW_STATUS, MINORITY_STATUS, IS_BPL_CARD_HOLDER, SELF_EMPLOYED, TENANT_FARMER/SHARECROPPER) + land-unit→hectare conversion. Update tests.
2. **Seed validation step** (backend): pre-seed validation that every `profile_field` resolves and choice values match registry choices (fails fast on unmapped fields).
3. **forms.json v2**: author the full v2 form JSON from sections 5–6 (~70 questions, 11 sections), keeping v1 intact.
4. **Seed + verify**: run seed_forms.py (creates v2 row), verify via API (`/forms/GENERAL_CITIZEN_PROFILE` → v2), run normalization end-to-end tests on v2 (profiles, facts, provenance, derived facts, idempotency).
5. **Frontend (2C proper)**: dynamic form renderer (sections/questions/options/conditions from the API), conditional visibility using the same operators, draft save/resume via submission APIs, completion gate, review screen, normalize call after completion. **CheckEligibilityPage.jsx is replaced by the dynamic renderer; the citizen creation endpoint remains for identity creation; after form completion + normalization the profile facts layer is populated.**
6. **Regression + baseline checks** after each increment.

Estimate: steps 1–4 are backend-only (~2–3 sessions), step 5 is the frontend build.

---

## 15. NOTES FOR REVIEWERS

- Nothing was modified for this plan: no code, schema, seed, API, frontend, or DB. The only writes were this document.
- The v1 form stays ACTIVE alongside v2 until 2C ships; Phase 2A/2B endpoints are version-aware.
- The catalogue deliberately keeps facts sparse (~40 facts vs ~70 questions): facts are rule inputs, not question mirrors.
