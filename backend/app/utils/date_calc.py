"""
Canonical date helpers.

`calculate_age` is the SINGLE age calculation for the whole application:
normalization derives the AGE profile fact with it, and the eligibility
engine consumes that fact (falling back to it only when no fact exists).
Never re-derive age inline elsewhere.
"""

from __future__ import annotations

from datetime import date


def calculate_age(date_of_birth: date, today: date | None = None) -> int:
    """
    Completed-birthday age in whole years.

    Standard deterministic rule:
      age = today.year - birth.year - (birthday has not occurred yet this year)

    Leap-day birthdays (Feb 29) count as occurring on Mar 1 in non-leap
    years, matching how PostgreSQL and most civil systems treat them.
    """
    if today is None:
        today = date.today()
    had_birthday = (today.month, today.day) >= (date_of_birth.month, date_of_birth.day)
    return today.year - date_of_birth.year - (0 if had_birthday else 1)
