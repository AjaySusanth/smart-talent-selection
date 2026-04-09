"""
Deterministic experience calculator (Task 3.6).

Replaces inaccurate LLM calculations by parsing date strings and
calculating durations mathematically.
"""

from __future__ import annotations

import re
from datetime import date
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from app.schemas.candidate_profile import Experience

logger = structlog.get_logger(__name__)


def _parse_date(date_str: str | None, is_end_date: bool = False) -> date | None:
    """
    Parse 'YYYY-MM', 'YYYY', or 'Present' into a datetime.date object.
    
    If is_end_date is True and only YYYY is provided, defaults to year-end (Dec 31).
    Otherwise defaults to year-start (Jan 1).
    """
    if not date_str or not isinstance(date_str, str):
        return None

    clean = date_str.strip().lower()
    if clean == "present":
        return date.today()

    # Match YYYY-MM
    match_ym = re.match(r"^(\d{4})-(\d{1,2})$", clean)
    if match_ym:
        year = int(match_ym.group(1))
        month = int(match_ym.group(2))
        return date(year, month, 1)

    # Match YYYY
    match_y = re.match(r"^(\d{4})$", clean)
    if match_y:
        year = int(match_y.group(1))
        if is_end_date:
            return date(year, 12, 31)
        return date(year, 1, 1)

    return None


def calculate_total_years(experiences: list[Experience]) -> float:
    """
    Calculate total years of experience from a list of entries.
    
    Note: This is a simple sum of durations. It doesn't subtract 
    overlapping periods (common for interns with overlapping projects/internships).
    """
    total_days = 0
    
    for exp in experiences:
        start = _parse_date(exp.start_date)
        end = _parse_date(exp.end_date, is_end_date=True)
        
        if not start or not end:
            continue
            
        # Ensure end is after start to avoid negative experience
        if end < start:
            logger.warning(
                "invalid_experience_dates", 
                company=exp.company, 
                start=exp.start_date, 
                end=exp.end_date
            )
            continue
            
        delta = end - start
        total_days += delta.days

    # Convert days to years (approx)
    years = total_days / 365.25
    
    # Return rounded to 1 decimal place (e.g. 2.5)
    return round(float(years), 1)
