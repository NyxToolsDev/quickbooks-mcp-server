"""Financial report tools (premium tier).

Provides access to QuickBooks standard financial reports including
P&L, Balance Sheet, Cash Flow, and aging reports.
"""

from __future__ import annotations

import logging
from typing import Any

from mcp.server import Server

from quickbooks_mcp.client.qbo_client import QBOClient
from quickbooks_mcp.utils.formatting import (
    PeriodType,
    format_currency,
    format_date_range,
)
from quickbooks_mcp.utils.license import require_premium, validate_license
from quickbooks_mcp.utils.money import Money

logger = logging.getLogger(__name__)


def register_report_tools(server: Server, qbo: QBOClient, license_key: str) -> None:
    """Register all financial report tools with the MCP server.

    All report tools require a valid premium license.

    Args:
        server: The MCP server instance.
        qbo: The QuickBooks API client.
        license_key: The Lemon Squeezy license key.
    """

    async def _check_premium() -> str | None:
        """Validate premium access, returning an error message if denied."""
        error = require_premium(license_key)
        if error is not None:
            return error
        # If no cached result, validate async
        if license_key:
            status = await validate_license(license_key)
            if not status.is_premium:
                return status.error
        return require_premium(license_key)

    @server.tool()
    async def get_profit_and_loss(
        period: str = "this_month",
        date_from: str = "",
        date_to: str = "",
        accounting_method: str = "Accrual",
    ) -> str:
        """Get a Profit & Loss (Income Statement) report.

        Shows revenue, expenses, and net income/loss for the specified period.
        Requires a premium license.

        Args:
            period: Time period - this_month, last_month, this_quarter, last_quarter,
                this_year, last_year, or custom (default: this_month).
            date_from: Start date for custom period (YYYY-MM-DD).
            date_to: End date for custom period (YYYY-MM-DD).
            accounting_method: Accrual or Cash (default: Accrual).

        Returns:
            Formatted P&L report with income, expense categories, and net income.
        """
        premium_error = await _check_premium()
        if premium_error:
            return premium_error

        period_type: PeriodType = period if period in (  # type: ignore[assignment]
            "this_month", "last_month", "this_quarter",
            "last_quarter", "this_year", "last_year", "custom",
        ) else "this_month"

        start_date, end_date = format_date_range(period_type, date_from, date_to)

        params: dict[str, str] = {
            "start_date": start_date,
            "end_date": end_date,
            "accounting_method": accounting_method,
        }

        report = await qbo.get_report("ProfitAndLoss", params=params)
        return _format_financial_report(report, "Profit & Loss", start_date, end_date)

    @server.tool()
    async def get_balance_sheet(
        as_of_date: str = "",
        accounting_method: str = "Accrual",
    ) -> str:
        """Get a Balance Sheet report as of a specific date.

        Shows assets, liabilities, and equity. Requires a premium license.

        Args:
            as_of_date: Report date in YYYY-MM-DD format (default: today).
            accounting_method: Accrual or Cash (default: Accrual).

        Returns:
            Formatted Balance Sheet with assets, liabilities, equity, and totals.
        """
        premium_error = await _check_premium()
        if premium_error:
            return premium_error

        params: dict[str, str] = {
            "accounting_method": accounting_method,
        }
        if as_of_date:
            params["date_macro"] = ""
            params["end_date"] = as_of_date

        report = await qbo.get_report("BalanceSheet", params=params)
        date_label = as_of_date or "today"
        return _format_financial_report(report, "Balance Sheet", end_date=date_label)

    @server.tool()
    async def get_cash_flow(
        period: str = "this_month",
        date_from: str = "",
        date_to: str = "",
    ) -> str:
        """Get a Cash Flow Statement.

        Shows operating, investing, and financing cash flows. Requires a premium license.

        Args:
            period: Time period - this_month, last_month, this_quarter, last_quarter,
                this_year, last_year, or custom (default: this_month).
            date_from: Start date for custom period (YYYY-MM-DD).
            date_to: End date for custom period (YYYY-MM-DD).

        Returns:
            Formatted Cash Flow Statement with operating, investing, and financing sections.
        """
        premium_error = await _check_premium()
        if premium_error:
            return premium_error

        period_type: PeriodType = period if period in (  # type: ignore[assignment]
            "this_month", "last_month", "this_quarter",
            "last_quarter", "this_year", "last_year", "custom",
        ) else "this_month"

        start_date, end_date = format_date_range(period_type, date_from, date_to)

        params: dict[str, str] = {
            "start_date": start_date,
            "end_date": end_date,
        }

        report = await qbo.get_report("CashFlow", params=params)
        return _format_financial_report(report, "Cash Flow Statement", start_date, end_date)

    @server.tool()
    async def get_accounts_receivable_aging(
        as_of_date: str = "",
    ) -> str:
        """Get an Accounts Receivable Aging report.

        Shows outstanding customer invoices grouped by aging buckets
        (Current, 1-30, 31-60, 61-90, 91+ days). Requires a premium license.

        Args:
            as_of_date: Report date in YYYY-MM-DD (default: today).

        Returns:
            AR aging by customer with current, 30, 60, 90+ day buckets and totals.
        """
        premium_error = await _check_premium()
        if premium_error:
            return premium_error

        params: dict[str, str] = {}
        if as_of_date:
            params["end_date"] = as_of_date

        report = await qbo.get_report("AgedReceivableDetail", params=params)
        return _format_aging_report(report, "Accounts Receivable Aging", as_of_date)

    @server.tool()
    async def get_accounts_payable_aging(
        as_of_date: str = "",
    ) -> str:
        """Get an Accounts Payable Aging report.

        Shows outstanding vendor bills grouped by aging buckets
        (Current, 1-30, 31-60, 61-90, 91+ days). Requires a premium license.

        Args:
            as_of_date: Report date in YYYY-MM-DD (default: today).

        Returns:
            AP aging by vendor with current, 30, 60, 90+ day buckets and totals.
        """
        premium_error = await _check_premium()
        if premium_error:
            return premium_error

        params: dict[str, str] = {}
        if as_of_date:
            params["end_date"] = as_of_date

        report = await qbo.get_report("AgedPayableDetail", params=params)
        return _format_aging_report(report, "Accounts Payable Aging", as_of_date)


def _format_financial_report(
    report: dict[str, Any],
    title: str,
    start_date: str = "",
    end_date: str = "",
) -> str:
    """Format a QuickBooks financial report into readable text.

    Args:
        report: The raw report data from the QBO API.
        title: Report title.
        start_date: Report start date for display.
        end_date: Report end date for display.

    Returns:
        Formatted report string.
    """
    header_data = report.get("Header", {})
    report_name = header_data.get("ReportName", title)
    date_label = header_data.get("DateMacro", "")

    lines: list[str] = [report_name]

    if start_date and end_date:
        lines.append(f"Period: {start_date} to {end_date}")
    elif end_date:
        lines.append(f"As of: {end_date}")
    elif date_label:
        lines.append(f"Period: {date_label}")

    lines.append(f"{'=' * 60}\n")

    # Parse rows recursively
    rows = report.get("Rows", {}).get("Row", [])
    _parse_report_rows(rows, lines, indent=0)

    return "\n".join(lines)


def _parse_report_rows(
    rows: list[dict[str, Any]],
    lines: list[str],
    indent: int = 0,
) -> None:
    """Recursively parse and format report rows.

    Args:
        rows: List of row dicts from the QBO report.
        lines: Output lines list to append to.
        indent: Current indentation level.
    """
    prefix = "  " * indent

    for row in rows:
        row_type = row.get("type", "")

        if row_type == "Section":
            # Section header
            header = row.get("Header", {})
            header_data = header.get("ColData", [])
            if header_data:
                section_name = header_data[0].get("value", "")
                if section_name:
                    lines.append(f"{prefix}{section_name}")
                    lines.append(f"{prefix}{'─' * (50 - indent * 2)}")

            # Nested rows
            nested_rows = row.get("Rows", {}).get("Row", [])
            if nested_rows:
                _parse_report_rows(nested_rows, lines, indent + 1)

            # Section summary
            summary = row.get("Summary", {})
            summary_data = summary.get("ColData", [])
            if summary_data:
                label = summary_data[0].get("value", "")
                value = summary_data[-1].get("value", "") if len(summary_data) > 1 else ""
                if label:
                    amount = format_currency(value) if value else ""
                    lines.append(f"{prefix}{'─' * (50 - indent * 2)}")
                    lines.append(f"{prefix}{label:<40} {amount:>12}")
                    lines.append("")

        elif row_type == "Data":
            col_data = row.get("ColData", [])
            if col_data:
                label = col_data[0].get("value", "")
                value = col_data[-1].get("value", "") if len(col_data) > 1 else ""
                if label:
                    amount = format_currency(value) if value else ""
                    lines.append(f"{prefix}  {label:<38} {amount:>12}")

        else:
            # Generic row
            col_data = row.get("ColData", [])
            if col_data:
                label = col_data[0].get("value", "")
                value = col_data[-1].get("value", "") if len(col_data) > 1 else ""
                if label and value:
                    amount = format_currency(value)
                    lines.append(f"{prefix}{label:<40} {amount:>12}")


def _format_aging_report(
    report: dict[str, Any],
    title: str,
    as_of_date: str = "",
) -> str:
    """Format an aging report into readable text with bucket summaries.

    Args:
        report: The raw report data from the QBO API.
        title: Report title.
        as_of_date: Report date for display.

    Returns:
        Formatted aging report string.
    """
    header_data = report.get("Header", {})
    report_name = header_data.get("ReportName", title)

    lines: list[str] = [report_name]
    if as_of_date:
        lines.append(f"As of: {as_of_date}")
    lines.append(f"{'=' * 70}\n")

    # Parse columns to get aging bucket names
    columns = report.get("Columns", {}).get("Column", [])
    col_names = [col.get("ColTitle", "") for col in columns]

    # Format header row
    if col_names:
        header_line = f"{'Name':<25}"
        for col_name in col_names[1:]:
            header_line += f" {col_name:>10}"
        lines.append(header_line)
        lines.append(f"{'─' * 70}")

    # Parse data rows
    rows = report.get("Rows", {}).get("Row", [])
    totals: dict[str, Money] = {}

    for row in rows:
        row_type = row.get("type", "")

        if row_type == "Section":
            header = row.get("Header", {})
            header_data = header.get("ColData", [])
            if header_data:
                entity_name = header_data[0].get("value", "")
                if entity_name:
                    lines.append(f"\n{entity_name}")

            nested_rows = row.get("Rows", {}).get("Row", [])
            for nested_row in nested_rows:
                col_data = nested_row.get("ColData", [])
                if col_data:
                    _format_aging_data_row(col_data, col_names, lines)

            summary = row.get("Summary", {})
            summary_data = summary.get("ColData", [])
            if summary_data:
                _format_aging_data_row(summary_data, col_names, lines, bold=True)

        elif row_type == "Data":
            col_data = row.get("ColData", [])
            if col_data:
                _format_aging_data_row(col_data, col_names, lines)

    # Grand total
    grand_total_rows = report.get("Rows", {}).get("Row", [])
    for row in grand_total_rows:
        if row.get("group") == "GrandTotal" or row.get("type") == "Section":
            summary = row.get("Summary", {})
            if summary:
                summary_data = summary.get("ColData", [])
                if summary_data:
                    label = summary_data[0].get("value", "")
                    if "total" in label.lower():
                        lines.append(f"\n{'=' * 70}")
                        _format_aging_data_row(summary_data, col_names, lines, bold=True)

    return "\n".join(lines)


def _format_aging_data_row(
    col_data: list[dict[str, Any]],
    col_names: list[str],
    lines: list[str],
    bold: bool = False,
) -> None:
    """Format a single aging data row.

    Args:
        col_data: Column data values.
        col_names: Column header names.
        lines: Output lines list to append to.
        bold: Whether this is a summary/total row.
    """
    if not col_data:
        return

    label = col_data[0].get("value", "")
    if not label:
        return

    prefix = ">>> " if bold else "    "
    line = f"{prefix}{label:<25}"

    for i, col in enumerate(col_data[1:], 1):
        value = col.get("value", "")
        if value:
            line += f" {format_currency(value):>12}"
        else:
            line += f" {'':>12}"

    lines.append(line)
