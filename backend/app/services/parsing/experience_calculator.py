"""
Deterministic calculation of total work experience years.

The LLM is unreliable at arithmetic — it frequently miscounts overlapping
employment periods.  This module parses the structured experience dates
produced by the extractor and computes the true non-overlapping duration
using an interval-merge algorithm.

Algorithm:
    1. Parse each experience entry's start_date / end_date into (year, month).
    2. Convert to a linear month index for easy arithmetic.
    3. Sort intervals by start.
    4. Merge overlapping or adjacent intervals.
    5. Sum merged interval durations → total months → total years (rounded to 1 dp).
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

import structlog

from app.schemas.candidate_profile import CandidateProfile

logger = structlog.get_logger(__name__)

# ─── Date parsing ──────────────────────────────────────────────────────────

_YYYY_MM = re.compile(r"^(\d{4})-(\d{1,2})$")
_YYYY = re.compile(r"^(\d{4})$")
_MM_DD_YYYY = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})$")


def _parse_date_to_months(date_str: str | None) -> int | None:
    """
    Convert a date string to a linear month index (year * 12 + month).

    Supports:
        - "YYYY-MM"     → exact month
        - "YYYY"        → defaults to January (start) — caller decides bias
        - "MM/DD/YYYY"  → exact month
        - "Present"     → current month
        - None / empty  → None (unparseable)
    """
    if not date_str or not isinstance(date_str, str):
        return None

    date_str = date_str.strip()

    if date_str.lower() in ("present", "current", "now", "ongoing"):
        now = datetime.now(timezone.utc)
        return now.year * 12 + now.month

    m = _YYYY_MM.match(date_str)
    if m:
        year, month = int(m.group(1)), int(m.group(2))
        month = max(1, min(12, month))
        return year * 12 + month

    m = _MM_DD_YYYY.match(date_str)
    if m:
        month, _, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        month = max(1, min(12, month))
        return year * 12 + month

    m = _YYYY.match(date_str)
    if m:
        year = int(m.group(1))
        return year * 12 + 1  # default to January

    return None


# ─── Interval merge ────────────────────────────────────────────────────────


def _merge_intervals(intervals: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """
    Merge overlapping or adjacent (start, end) intervals.

    Input intervals are inclusive month indices.
    """
    if not intervals:
        return []

    sorted_intervals = sorted(intervals, key=lambda x: x[0])
    merged: list[tuple[int, int]] = [sorted_intervals[0]]

    for start, end in sorted_intervals[1:]:
        prev_start, prev_end = merged[-1]
        if start <= prev_end + 1:
            # Overlapping or adjacent — extend
            merged[-1] = (prev_start, max(prev_end, end))
        else:
            merged.append((start, end))

    return merged


# ─── Public API ────────────────────────────────────────────────────────────


def compute_total_experience_years(profile: CandidateProfile) -> float:
    """
    Deterministically compute total non-overlapping work experience years
    from the structured experience entries in a CandidateProfile.

    Returns years rounded to 1 decimal place.
    """
    intervals: list[tuple[int, int]] = []

    for exp in profile.experience:
        start = _parse_date_to_months(exp.start_date)
        end = _parse_date_to_months(exp.end_date)

        if start is None and end is None:
            continue

        # If only end is known, skip (can't compute duration without start)
        if start is None:
            continue

        # If end is missing but we have start, assume "Present"
        if end is None:
            now = datetime.now(timezone.utc)
            end = now.year * 12 + now.month

        # Guard against reversed dates
        if end < start:
            start, end = end, start

        intervals.append((start, end))

    if not intervals:
        return 0.0

    merged = _merge_intervals(intervals)
    total_months = sum(end - start for start, end in merged)
    total_years = round(total_months / 12.0, 1)

    logger.info(
        "experience_years_computed",
        raw_intervals=len(intervals),
        merged_intervals=len(merged),
        total_months=total_months,
        total_years=total_years,
    )

    return total_years
