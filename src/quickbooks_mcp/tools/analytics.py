"""Financial analytics tools (premium tier).

Provides computed financial health metrics and period-over-period
comparison analytics built on top of QuickBooks report data.
"""

from __future__ import annotations

import logging
from decimal import Decimal
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


def register_analytics_tools(server: Server, qbo: QBOClient, license_key: str) -> None:
    """Register all analytics tools with the MCP server.

    All analytics tools require a valid premium license.

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
        if license_key:
            status = await validate_license(license_key)
            if not status.is_premium:
                return status.error
        return require_premium(license_key)

    @server.tool()
    async def get_financial_health(
        as_of_date: str = "",
    ) -> str:
        """Get key financial health metrics for your business.

        Calculates current ratio, quick ratio, days sales outstanding (DSO),
        monthly burn rate, and estimated cash runway. Requires a premium license.

        Args:
            as_of_date: Date for calculations in YYYY-MM-DD (default: today).

        Returns:
            Financial health dashboard with key ratios and metrics.
        """
        premium_error = await _check_premium()
        if premium_error:
            return premium_error

        # Fetch Balance Sheet for ratios
        bs_params: dict[str, str] = {}
        if as_of_date:
            bs_params["end_date"] = as_of_date

        balance_sheet = await qbo.get_report("BalanceSheet", params=bs_params)

        # Fetch P&L for burn rate calculation (last 3 months)
        from datetime import date, timedelta

        today = date.today()
        three_months_ago = today - timedelta(days=90)
        pl_params: dict[str, str] = {
            "start_date": three_months_ago.isoformat(),
            "end_date": (today if not as_of_date else date.fromisoformat(as_of_date)).isoformat(),
        }

        pnl = await qbo.get_report("ProfitAndLoss", params=pl_params)

        # Extract values from Balance Sheet
        bs_values = _extract_report_values(balance_sheet)

        current_assets = Money.from_qbo(
            bs_values.get("Total Current Assets", bs_values.get("Total Bank Accounts", 0))
        )
        current_liabilities = Money.from_qbo(
            bs_values.get("Total Current Liabilities", 0)
        )
        cash = Money.from_qbo(
            bs_values.get("Total Bank Accounts", bs_values.get("Checking", 0))
        )
        inventory = Money.from_qbo(bs_values.get("Inventory", 0))
        accounts_receivable = Money.from_qbo(
            bs_values.get("Total Accounts Receivable",
                          bs_values.get("Accounts Receivable (A/R)", 0))
        )
        total_assets = Money.from_qbo(
            bs_values.get("TOTAL ASSETS", bs_values.get("Total Assets", 0))
        )
        total_liabilities = Money.from_qbo(
            bs_values.get("TOTAL LIABILITIES", bs_values.get("Total Liabilities", 0))
        )

        # Extract P&L values
        pl_values = _extract_report_values(pnl)
        total_revenue = Money.from_qbo(
            pl_values.get("Total Income", pl_values.get("Gross Profit", 0))
        )
        total_expenses = Money.from_qbo(
            pl_values.get("Total Expenses", 0)
        )
        net_income = Money.from_qbo(
            pl_values.get("Net Income", pl_values.get("Net Operating Income", 0))
        )

        # Calculate metrics
        # Current Ratio = Current Assets / Current Liabilities
        current_ratio = (
            float(current_assets.amount) / float(current_liabilities.amount)
            if current_liabilities > 0 else float("inf")
        )

        # Quick Ratio = (Current Assets - Inventory) / Current Liabilities
        quick_assets = current_assets - inventory
        quick_ratio = (
            float(quick_assets.amount) / float(current_liabilities.amount)
            if current_liabilities > 0 else float("inf")
        )

        # Days Sales Outstanding = (AR / Revenue) * Days in period
        days_in_period = 90  # 3 months
        dso = (
            float(accounts_receivable.amount) / float(total_revenue.amount) * days_in_period
            if total_revenue > 0 else 0
        )

        # Monthly Burn Rate = Total Expenses / 3 months
        monthly_burn = total_expenses / 3

        # Cash Runway = Cash / Monthly Burn Rate (in months)
        runway_months = (
            float(cash.amount) / float(monthly_burn.amount)
            if monthly_burn > 0 else float("inf")
        )

        # Debt-to-Asset Ratio
        debt_to_asset = (
            float(total_liabilities.amount) / float(total_assets.amount)
            if total_assets > 0 else 0
        )

        # Build output
        lines: list[str] = [
            "Financial Health Dashboard",
            f"{'=' * 55}\n",
            "Liquidity Ratios:",
            f"  Current Ratio:     {current_ratio:.2f}x"
            + _ratio_indicator(current_ratio, good=1.5, warning=1.0),
            f"  Quick Ratio:       {quick_ratio:.2f}x"
            + _ratio_indicator(quick_ratio, good=1.0, warning=0.5),
            "",
            "Efficiency:",
            f"  Days Sales Outstanding (DSO): {dso:.0f} days"
            + _dso_indicator(dso),
            "",
            "Cash Position:",
            f"  Cash on Hand:      {format_currency(cash)}",
            f"  Monthly Burn Rate: {format_currency(monthly_burn)}",
            f"  Cash Runway:       {runway_months:.1f} months"
            + _runway_indicator(runway_months),
            "",
            "Leverage:",
            f"  Debt-to-Asset:     {debt_to_asset:.1%}"
            + _debt_indicator(debt_to_asset),
            "",
            "P&L Summary (Last 90 Days):",
            f"  Revenue:           {format_currency(total_revenue)}",
            f"  Expenses:          {format_currency(total_expenses)}",
            f"  Net Income:        {format_currency(net_income)}",
            "",
            "Balance Sheet Snapshot:",
            f"  Total Assets:      {format_currency(total_assets)}",
            f"  Total Liabilities: {format_currency(total_liabilities)}",
            f"  Accounts Recv:     {format_currency(accounts_receivable)}",
        ]

        return "\n".join(lines)

    @server.tool()
    async def compare_periods(
        period_1: str = "this_month",
        period_2: str = "last_month",
        date_from_1: str = "",
        date_to_1: str = "",
        date_from_2: str = "",
        date_to_2: str = "",
    ) -> str:
        """Compare financial performance between two time periods.

        Shows revenue, expenses, and net income side-by-side with
        dollar and percentage changes. Requires a premium license.

        Args:
            period_1: First period - this_month, last_month, this_quarter,
                last_quarter, this_year, last_year, or custom (default: this_month).
            period_2: Second period for comparison (default: last_month).
            date_from_1: Start date for custom period 1 (YYYY-MM-DD).
            date_to_1: End date for custom period 1 (YYYY-MM-DD).
            date_from_2: Start date for custom period 2 (YYYY-MM-DD).
            date_to_2: End date for custom period 2 (YYYY-MM-DD).

        Returns:
            Side-by-side comparison with dollar changes and percentage differences.
        """
        premium_error = await _check_premium()
        if premium_error:
            return premium_error

        # Resolve periods
        period_type_1: PeriodType = period_1 if period_1 in (  # type: ignore[assignment]
            "this_month", "last_month", "this_quarter",
            "last_quarter", "this_year", "last_year", "custom",
        ) else "this_month"

        period_type_2: PeriodType = period_2 if period_2 in (  # type: ignore[assignment]
            "this_month", "last_month", "this_quarter",
            "last_quarter", "this_year", "last_year", "custom",
        ) else "last_month"

        start_1, end_1 = format_date_range(period_type_1, date_from_1, date_to_1)
        start_2, end_2 = format_date_range(period_type_2, date_from_2, date_to_2)

        # Fetch P&L for both periods
        pnl_1 = await qbo.get_report(
            "ProfitAndLoss",
            params={"start_date": start_1, "end_date": end_1},
        )
        pnl_2 = await qbo.get_report(
            "ProfitAndLoss",
            params={"start_date": start_2, "end_date": end_2},
        )

        # Extract key values
        values_1 = _extract_report_values(pnl_1)
        values_2 = _extract_report_values(pnl_2)

        # Key metrics to compare
        metrics = [
            ("Total Income", "Revenue"),
            ("Total Cost of Goods Sold", "Cost of Goods Sold"),
            ("Gross Profit", "Gross Profit"),
            ("Total Expenses", "Total Expenses"),
            ("Net Operating Income", "Operating Income"),
            ("Net Income", "Net Income"),
        ]

        period_1_label = period_1.replace("_", " ").title()
        period_2_label = period_2.replace("_", " ").title()

        lines: list[str] = [
            "Period Comparison",
            f"{'=' * 75}",
            f"Period 1: {period_1_label} ({start_1} to {end_1})",
            f"Period 2: {period_2_label} ({start_2} to {end_2})",
            "",
            f"{'Metric':<25} {'Period 1':>12} {'Period 2':>12} {'Change':>12} {'% Chg':>8}",
            f"{'─' * 75}",
        ]

        for qbo_key, display_name in metrics:
            val_1 = Money.from_qbo(values_1.get(qbo_key, 0))
            val_2 = Money.from_qbo(values_2.get(qbo_key, 0))
            change = val_1 - val_2

            pct_change: str
            if val_2 == 0:
                pct_change = "N/A" if val_1 == 0 else "+NEW"
            else:
                pct = float(change.amount) / abs(float(val_2.amount)) * 100
                sign = "+" if pct >= 0 else ""
                pct_change = f"{sign}{pct:.1f}%"

            change_str = format_currency(change)
            if change > 0:
                change_str = f"+{format_currency(change)}"

            lines.append(
                f"  {display_name:<23} "
                f"{format_currency(val_1):>12} "
                f"{format_currency(val_2):>12} "
                f"{change_str:>12} "
                f"{pct_change:>8}"
            )

        # Add summary insight
        net_1 = Money.from_qbo(values_1.get("Net Income", 0))
        net_2 = Money.from_qbo(values_2.get("Net Income", 0))
        rev_1 = Money.from_qbo(values_1.get("Total Income", 0))
        rev_2 = Money.from_qbo(values_2.get("Total Income", 0))

        lines.append(f"\n{'─' * 75}")
        lines.append("Key Insights:")

        if rev_1 > rev_2:
            rev_growth = (
                float((rev_1 - rev_2).amount) / float(rev_2.amount) * 100
                if rev_2 > 0 else 0
            )
            lines.append(f"  Revenue grew {rev_growth:.1f}% period-over-period")
        elif rev_1 < rev_2:
            rev_decline = (
                float((rev_2 - rev_1).amount) / float(rev_2.amount) * 100
                if rev_2 > 0 else 0
            )
            lines.append(f"  Revenue declined {rev_decline:.1f}% period-over-period")
        else:
            lines.append("  Revenue was flat between periods")

        if net_1 > 0 and net_2 <= 0:
            lines.append("  Business returned to profitability")
        elif net_1 <= 0 and net_2 > 0:
            lines.append("  Business became unprofitable this period")

        # Margin comparison
        if rev_1 > 0:
            margin_1 = float(net_1.amount) / float(rev_1.amount) * 100
            lines.append(f"  Period 1 net margin: {margin_1:.1f}%")
        if rev_2 > 0:
            margin_2 = float(net_2.amount) / float(rev_2.amount) * 100
            lines.append(f"  Period 2 net margin: {margin_2:.1f}%")

        return "\n".join(lines)


def _extract_report_values(report: dict[str, Any]) -> dict[str, float]:
    """Extract key labeled values from a QBO report response.

    Recursively traverses the report rows to find summary values
    and maps them by their label name.

    Args:
        report: The raw report data from the QBO API.

    Returns:
        Dictionary mapping label names to their numeric values.
    """
    values: dict[str, float] = {}
    rows = report.get("Rows", {}).get("Row", [])
    _extract_rows_recursive(rows, values)
    return values


def _extract_rows_recursive(
    rows: list[dict[str, Any]], values: dict[str, float]
) -> None:
    """Recursively extract label-value pairs from report rows.

    Args:
        rows: List of row dicts from the QBO report.
        values: Dictionary to populate with extracted values.
    """
    for row in rows:
        row_type = row.get("type", "")

        if row_type == "Section":
            # Process header
            header = row.get("Header", {})
            header_data = header.get("ColData", [])
            if len(header_data) >= 2:
                label = header_data[0].get("value", "")
                val = header_data[-1].get("value", "")
                if label and val:
                    try:
                        values[label] = float(val)
                    except (ValueError, TypeError):
                        pass

            # Recurse into nested rows
            nested_rows = row.get("Rows", {}).get("Row", [])
            if nested_rows:
                _extract_rows_recursive(nested_rows, values)

            # Process summary
            summary = row.get("Summary", {})
            summary_data = summary.get("ColData", [])
            if len(summary_data) >= 2:
                label = summary_data[0].get("value", "")
                val = summary_data[-1].get("value", "")
                if label and val:
                    try:
                        values[label] = float(val)
                    except (ValueError, TypeError):
                        pass

        elif row_type == "Data":
            col_data = row.get("ColData", [])
            if len(col_data) >= 2:
                label = col_data[0].get("value", "")
                val = col_data[-1].get("value", "")
                if label and val:
                    try:
                        values[label] = float(val)
                    except (ValueError, TypeError):
                        pass


def _ratio_indicator(value: float, good: float, warning: float) -> str:
    """Generate a visual indicator for a financial ratio.

    Args:
        value: The ratio value.
        good: Threshold for "good" status.
        warning: Threshold for "warning" status.

    Returns:
        Status indicator string.
    """
    if value >= good:
        return "  [HEALTHY]"
    if value >= warning:
        return "  [CAUTION]"
    return "  [WARNING]"


def _dso_indicator(dso: float) -> str:
    """Generate a visual indicator for DSO.

    Args:
        dso: Days sales outstanding value.

    Returns:
        Status indicator string.
    """
    if dso <= 30:
        return "  [EXCELLENT]"
    if dso <= 45:
        return "  [GOOD]"
    if dso <= 60:
        return "  [CAUTION]"
    return "  [WARNING - High DSO]"


def _runway_indicator(months: float) -> str:
    """Generate a visual indicator for cash runway.

    Args:
        months: Estimated months of runway.

    Returns:
        Status indicator string.
    """
    if months == float("inf"):
        return "  [PROFITABLE - No burn]"
    if months >= 12:
        return "  [HEALTHY]"
    if months >= 6:
        return "  [CAUTION]"
    if months >= 3:
        return "  [WARNING]"
    return "  [CRITICAL - Less than 3 months]"


def _debt_indicator(ratio: float) -> str:
    """Generate a visual indicator for debt-to-asset ratio.

    Args:
        ratio: Debt-to-asset ratio (0 to 1+).

    Returns:
        Status indicator string.
    """
    if ratio <= 0.3:
        return "  [LOW LEVERAGE]"
    if ratio <= 0.6:
        return "  [MODERATE]"
    return "  [HIGH LEVERAGE]"
