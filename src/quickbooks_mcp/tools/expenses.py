"""Expense query tools (free tier).

Provides access to QuickBooks purchase/expense data with filtering
and category/vendor grouping.
"""

from __future__ import annotations

import logging
from collections import defaultdict

from mcp.server import Server

from quickbooks_mcp.client.qbo_client import QBOClient
from quickbooks_mcp.client.query_builder import QueryBuilder
from quickbooks_mcp.utils.formatting import (
    PeriodType,
    format_currency,
    format_date,
    format_date_range,
)
from quickbooks_mcp.utils.money import Money

logger = logging.getLogger(__name__)


def register_expense_tools(server: Server, qbo: QBOClient) -> None:
    """Register all expense-related tools with the MCP server."""

    @server.tool()
    async def list_expenses(
        date_from: str = "",
        date_to: str = "",
        vendor_name: str = "",
        category: str = "",
        min_amount: float = 0,
        max_amount: float = 0,
        limit: int = 25,
    ) -> str:
        """List recent expenses and purchases with optional filters.

        Args:
            date_from: Start date filter in YYYY-MM-DD format.
            date_to: End date filter in YYYY-MM-DD format.
            vendor_name: Filter by vendor/payee name (partial match).
            category: Filter by expense category/account name.
            min_amount: Minimum expense amount filter.
            max_amount: Maximum expense amount filter (0 = no limit).
            limit: Maximum results to return (default: 25, max: 100).

        Returns:
            Formatted list of expenses with date, vendor, amount, and category.
        """
        limit = min(max(1, limit), 100)

        qb = QueryBuilder("Purchase").select(
            ["Id", "TxnDate", "TotalAmt", "EntityRef", "AccountRef",
             "PaymentType", "PrivateNote"]
        )

        if date_from:
            qb.where("TxnDate", ">=", date_from)
        if date_to:
            qb.where("TxnDate", "<=", date_to)
        if min_amount > 0:
            qb.where("TotalAmt", ">=", str(min_amount))
        if max_amount > 0:
            qb.where("TotalAmt", "<=", str(max_amount))

        qb.order_by("TxnDate", "DESC").limit(limit)

        expenses = await qbo.query(qb.build())

        if not expenses:
            return "No expenses found matching your criteria."

        # Filter by vendor name in-memory (QBO doesn't support LIKE on EntityRef)
        if vendor_name:
            vendor_lower = vendor_name.lower()
            expenses = [
                e for e in expenses
                if vendor_lower in (e.get("EntityRef", {}).get("name", "")).lower()
            ]

        if not expenses:
            return f"No expenses found for vendor matching '{vendor_name}'."

        total = Money.sum([Money.from_qbo(e.get("TotalAmt", 0)) for e in expenses])

        lines: list[str] = [f"Found {len(expenses)} expense(s) | Total: {total}\n"]

        for exp in expenses:
            vendor = exp.get("EntityRef", {}).get("name", "Unknown vendor")
            account = exp.get("AccountRef", {}).get("name", "")
            payment_type = exp.get("PaymentType", "")
            note = exp.get("PrivateNote", "")

            desc_parts = [payment_type, account]
            if note:
                desc_parts.append(note[:40])
            description = " | ".join(p for p in desc_parts if p)

            lines.append(
                f"  {format_date(exp.get('TxnDate'))} | {vendor} | "
                f"{format_currency(exp.get('TotalAmt'))} | {description}"
            )

        return "\n".join(lines)

    @server.tool()
    async def get_top_expenses(
        period: str = "this_month",
        group_by: str = "category",
        limit: int = 10,
    ) -> str:
        """Get top expenses grouped by category or vendor.

        Args:
            period: Time period - this_month, last_month, this_quarter, this_year
                (default: this_month).
            group_by: Group results by 'category' or 'vendor' (default: category).
            limit: Number of top entries to show (default: 10).

        Returns:
            Ranked expense breakdown with totals and percentages.
        """
        period_type: PeriodType = period if period in (  # type: ignore[assignment]
            "this_month", "last_month", "this_quarter",
            "last_quarter", "this_year", "last_year",
        ) else "this_month"

        start_date, end_date = format_date_range(period_type)

        qb = (
            QueryBuilder("Purchase")
            .select(["Id", "TotalAmt", "EntityRef", "AccountRef", "Line", "TxnDate"])
            .where("TxnDate", ">=", start_date)
            .where("TxnDate", "<=", end_date)
            .limit(500)
        )

        expenses = await qbo.query(qb.build())

        if not expenses:
            return f"No expenses found for {period.replace('_', ' ')}."

        # Group expenses
        groups: dict[str, Money] = defaultdict(lambda: Money(0))

        for exp in expenses:
            if group_by == "vendor":
                key = exp.get("EntityRef", {}).get("name", "Unknown Vendor")
            else:
                # Group by account/category from line items or account ref
                key = exp.get("AccountRef", {}).get("name", "Uncategorized")
                # If we have line items, use the account from the first line
                line_items = exp.get("Line", [])
                for line in line_items:
                    detail = line.get("AccountBasedExpenseLineDetail", {})
                    acct = detail.get("AccountRef", {}).get("name")
                    if acct:
                        key = acct
                        break

            amount = Money.from_qbo(exp.get("TotalAmt", 0))
            groups[key] = groups[key] + amount

        # Sort by amount descending
        sorted_groups = sorted(groups.items(), key=lambda x: x[1], reverse=True)[:limit]

        grand_total = Money.sum(list(groups.values()))

        period_label = period.replace("_", " ").title()
        lines: list[str] = [
            f"Top Expenses by {group_by.title()} ({period_label})",
            f"Total: {grand_total}\n",
        ]

        for rank, (name, amount) in enumerate(sorted_groups, 1):
            pct = (
                float(amount.amount) / float(grand_total.amount) * 100
                if grand_total > 0
                else 0
            )
            bar = "█" * int(pct / 5)
            lines.append(f"  {rank:2d}. {name:<30} {amount!s:>12}  ({pct:5.1f}%) {bar}")

        return "\n".join(lines)
