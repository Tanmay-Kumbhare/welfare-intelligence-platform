/**
 * profileValidation.js
 *
 * Centralised, reusable validation helpers for the citizen profile fields
 * (registration + profile-edit forms).
 *
 * Rules:
 *   - Names allow alphabetic chars and spaces (Indian names may be multi-word).
 *   - Email uses a standard "has local@domain.tld" check; not overly strict.
 *   - Mobile must be exactly 10 digits.
 *   - Pincode must be exactly 6 digits.
 *   - Annual income must be a non-negative number.
 *   - DOB must be a valid past date; age is derived, never stored independently.
 *
 * Every validator returns null when valid, or a human-readable error string.
 */

// ─── Regexes ──────────────────────────────────────────────────────────────────

/** Alphabetic characters and inner spaces only. */
const NAME_RE = /^[A-Za-z]+(?:\s[A-Za-z]+)*$/;

/** Exactly 10 digits — no letters, no separators. */
const MOBILE_RE = /^\d{10}$/;

/** Standard email: local@domain.tld */
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/** Exactly 6 digits. */
const PINCODE_RE = /^\d{6}$/;

// ─── Name validators ──────────────────────────────────────────────────────────

/**
 * Validate first name.
 * Required; min 2 chars; alphabetic + spaces only.
 */
export function validateFirstName(value) {
  const v = (value || "").trim();
  if (!v) return "First name is required.";
  if (v.length < 2) return "First name must be at least 2 characters.";
  if (!NAME_RE.test(v))
    return "Please enter a valid first name. Numbers and special characters are not allowed.";
  return null;
}

/**
 * Validate middle name.
 * Optional; if provided, min 2 chars; alphabetic + spaces only.
 */
export function validateMiddleName(value) {
  const v = (value || "").trim();
  if (!v) return null; // optional — empty is fine
  if (v.length < 2) return "Middle name must be at least 2 characters.";
  if (!NAME_RE.test(v))
    return "Please enter a valid middle name. Numbers and special characters are not allowed.";
  return null;
}

/**
 * Validate last name.
 * Required; min 2 chars; alphabetic + spaces only.
 */
export function validateLastName(value) {
  const v = (value || "").trim();
  if (!v) return "Last name is required.";
  if (v.length < 2) return "Last name must be at least 2 characters.";
  if (!NAME_RE.test(v))
    return "Please enter a valid last name. Numbers and special characters are not allowed.";
  return null;
}

/**
 * Compose full_name from parts (sent to the backend which stores full_name).
 * Middle name is omitted when blank.
 */
export function buildFullName(firstName, middleName, lastName) {
  const parts = [
    (firstName || "").trim(),
    (middleName || "").trim(),
    (lastName || "").trim(),
  ].filter(Boolean);
  return parts.join(" ");
}

/**
 * Split an existing full_name back into { firstName, middleName, lastName }.
 * Best-effort for the edit-profile flow where the DB stores a single string.
 *   1 token  → first=token, middle="", last=""
 *   2 tokens → first=tokens[0], middle="", last=tokens[1]
 *   3+ tokens → first=tokens[0], middle=tokens[1..n-2], last=tokens[n-1]
 */
export function splitFullName(fullName) {
  const parts = (fullName || "").trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return { firstName: "", middleName: "", lastName: "" };
  if (parts.length === 1) return { firstName: parts[0], middleName: "", lastName: "" };
  if (parts.length === 2)
    return { firstName: parts[0], middleName: "", lastName: parts[1] };
  return {
    firstName: parts[0],
    middleName: parts.slice(1, -1).join(" "),
    lastName: parts[parts.length - 1],
  };
}

// ─── Contact validators ───────────────────────────────────────────────────────

/**
 * Validate mobile number.
 * Required; exactly 10 digits; no letters or separators.
 */
export function validateMobile(value) {
  const v = (value || "").trim();
  if (!v) return "Mobile number is required.";
  if (!MOBILE_RE.test(v))
    return "Please enter a valid 10-digit mobile number.";
  return null;
}

/**
 * Validate email address (optional field on profile, but required on register
 * because it is the login credential — call-site decides required vs. optional).
 */
export function validateEmail(value, { required = false } = {}) {
  const v = (value || "").trim();
  if (!v) {
    return required ? "Email address is required." : null;
  }
  if (!EMAIL_RE.test(v)) return "Please enter a valid email address.";
  return null;
}

// ─── DOB / age ────────────────────────────────────────────────────────────────

/**
 * Validate date of birth.
 * Required; must be a valid past date (not today, not future).
 */
export function validateDob(value) {
  if (!value) return "Date of birth is required.";
  const dob = new Date(value);
  if (isNaN(dob.getTime())) return "Please enter a valid date of birth.";
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  if (dob >= today) return "Date of birth cannot be in the future.";
  return null;
}

/**
 * Calculate age in completed years from a DOB string (YYYY-MM-DD).
 *
 * Mirrors the canonical backend calculate_age() in app/utils/date_calc.py:
 *   - Completed-birthday math: if the birthday hasn't occurred yet this year,
 *     subtract 1 from the year difference.
 *   - Feb-29 birthdays: (today.month, today.day) >= (2, 29) → treated as
 *     occurring on Mar-1 in non-leap years, consistent with Python logic.
 *
 * Returns null for invalid/missing DOB.
 */
export function calculateAge(dobValue) {
  if (!dobValue) return null;
  const dob = new Date(dobValue);
  if (isNaN(dob.getTime())) return null;
  const today = new Date();
  const hadBirthday =
    today.getMonth() > dob.getMonth() ||
    (today.getMonth() === dob.getMonth() &&
      today.getDate() >= dob.getDate());
  return today.getFullYear() - dob.getFullYear() - (hadBirthday ? 0 : 1);
}

// ─── Financial validators ─────────────────────────────────────────────────────

/**
 * Validate annual income.
 * Optional; if provided must be a non-negative number.
 * Zero is permitted.
 */
export function validateIncome(value) {
  const v = String(value ?? "").trim();
  if (v === "") return null; // optional
  // Reject non-numeric / mixed input (letters, currency symbols stored as text)
  if (!/^-?\d+(\.\d+)?$/.test(v)) return "Please enter a valid income amount.";
  if (Number(v) < 0) return "Income cannot be negative.";
  return null;
}

// ─── Location validators ──────────────────────────────────────────────────────

/**
 * Validate pincode.
 * Optional; if provided must be exactly 6 digits.
 */
export function validatePincode(value) {
  const v = (value || "").trim();
  if (!v) return null; // optional
  if (!PINCODE_RE.test(v)) return "Please enter a valid 6-digit pincode.";
  return null;
}

// ─── Batch helpers ────────────────────────────────────────────────────────────

/**
 * Run all profile field validators at once.
 * Returns { field: message|null }; null means valid.
 *
 * @param {object} fields
 */
export function validateProfileFields(fields) {
  return {
    firstName: validateFirstName(fields.firstName),
    middleName: validateMiddleName(fields.middleName),
    lastName: validateLastName(fields.lastName),
    mobile_number: validateMobile(fields.mobile_number),
    email: validateEmail(fields.email, { required: fields._emailRequired }),
    date_of_birth: validateDob(fields.date_of_birth),
    annual_income: validateIncome(fields.annual_income),
  };
}

/** Returns true only when every value in the errors object is null/undefined. */
export function hasNoErrors(errors) {
  return Object.values(errors).every((v) => v === null || v === undefined);
}
