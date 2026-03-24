"""Formatting utilities for currency, dates, and display output."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Literal

from quickbooks_mcp.utils.money import Money

# Period type used across tools
PeriodType = Literal[
    "this_month", "last_month", "this_quarter", "last_quarter",
    "this_year", "last_year", "custom",
]


def format_currency(amount: float | int | str | Money | None) -> str:
    """Format an amount as a USD currency string.

    Args:
        amount: The numeric amount.

    Returns:
        Formatted string like "$1,234.56".
    """
    if amount is None:
        return "$0.00"
    money = Money.from_qbo(amount) if not isinstance(amount, Money) else amount
    return str(money)


def format_date(date_str: str | None, fmt: str = "%b %d, %Y") -> str:
    """Format a date string from QBO format (YYYY-MM-DD) to human-readable.

    Args:
        date_str: Date in YYYY-MM-DD format.
        fmt: Output format string.

    Returns:
        Formatted date string, or "N/A" if input is None.
    """
    if not date_str:
        return "N/A"
    try:
        dt = datetime.strptime(date_str[:10], "%Y-%m-%d")
        return dt.strftime(fmt)
    except (ValueError, TypeError):
        return date_str


def format_date_range(
    period: PeriodType,
    date_from: str | None = None,
    date_to: str | None = None,
) -> tuple[str, str]:
    """Convert a named period to a (start_date, end_date) tuple in YYYY-MM-DD format.

    Args:
        period: Named period or "custom".
        date_from: Start date for custom period.
        date_to: End date for custom period.

    Returns:
        Tuple of (start_date, end_date) strings.

    Raises:
        ValueError: If custom period is selected without providing dates.
    """
    today = date.today()

    if period == "custom":
        if not date_from or not date_to:
            raise ValueError("date_from and date_to are required for custom period")
        return date_from, date_to

    if period == "this_month":
        start = today.replace(day=1)
        end = today

    elif period == "last_month":
        first_of_this_month = today.replace(day=1)
        end = first_of_this_month - timedelta(days=1)
        start = end.replace(day=1)

    elif period == "this_quarter":
        quarter_start_month = ((today.month - 1) // 3) * 3 + 1
        start = today.replace(month=quarter_start_month, day=1)
        end = today

    elif period == "last_quarter":
        quarter_start_month = ((today.month - 1) // 3) * 3 + 1
        this_quarter_start = today.replace(month=quarter_start_month, day=1)
        end = this_quarter_start - timedelta(days=1)
        last_q_start_month = ((end.month - 1) // 3) * 3 + 1
        start = end.replace(month=last_q_start_month, day=1)

    elif period == "this_year":
        start = today.replace(month=1, day=1)
        end = today

    elif period == "last_year":
        start = today.replace(year=today.year - 1, month=1, day=1)
        end = today.replace(year=today.year - 1, month=12, day=31)

    else:
        start = today.replace(day=1)
        end = today

    return start.isoformat(), end.isoformat()


def days_between(date_str: str, reference: date | None = None) -> int:
    """Calculate days between a date string and a reference date.

    Args:
        date_str: Date in YYYY-MM-DD format.
        reference: Reference date (defaults to today).

    Returns:
        Number of days difference (positive if date_str is in the past).
    """
    ref = reference or date.today()
    try:
        dt = datetime.strptime(date_str[:10], "%Y-%m-%d").date()
        return (ref - dt).days
    except (ValueError, TypeError):
        return 0


def truncate(text: str, max_length: int = 50) -> str:
    """Truncate a string with ellipsis if it exceeds max_length."""
    if len(text) <= max_length:
        return text
    return text[: max_length - 3] + "..."
