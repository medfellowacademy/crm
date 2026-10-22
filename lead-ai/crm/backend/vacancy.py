"""Seat-board helpers (pure, unit-tested) for the Vacancy Board page."""

from typing import Iterable, Optional


def clean_seats(seats: Optional[Iterable], total: int) -> list:
    """Sorted, de-duplicated seat numbers within 1..total (anything else dropped)."""
    out = set()
    for s in seats or []:
        try:
            n = int(s)
        except (TypeError, ValueError):
            continue
        if 1 <= n <= total:
            out.add(n)
    return sorted(out)


def toggle_seat(seats: Optional[Iterable], n: int, total: int) -> list:
    """Flip seat `n`: enrolled -> available, available -> enrolled."""
    if not isinstance(n, int) or n < 1 or n > total:
        raise ValueError("Seat number out of range")
    current = set(clean_seats(seats, total))
    current.symmetric_difference_update({n})
    return sorted(current)


def stats(total: int, seats: Optional[Iterable]) -> dict:
    enrolled = len(clean_seats(seats, total))
    return {
        "enrolled": enrolled,
        "available": max(0, total - enrolled),
        "percent": round(enrolled / total * 100) if total else 0,
    }
