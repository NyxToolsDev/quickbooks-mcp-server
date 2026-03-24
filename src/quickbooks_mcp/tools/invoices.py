"""Invoice query tools (free tier).

Provides natural-language access to QuickBooks invoice data including
listing, filtering, detail retrieval, and overdue tracking.
"""

from __future__ import annotations

import logging
from typing import Any

from mcp.server import Server

from quickbooks_mcp.client.qbo_client import QBOClient
from quickbooks_mcp.client.query_builder import QueryBuilder
from quickbooks_mcp.utils.formatting import days_between, format_currency, format_date

logger = logging.getLogger(__name__)


def register_invoice_tools(server: Server, qbo: QBOClient) -> None:
    """Register all invoice-related tools with the MCP server.

    Args:
        server: The MCP server instance.
        qbo: The QuickBooks API client.
    """

    @server.tool()
    async def list_invoices(
        status: str = "All",
        date_from: str = "",
        date_to: str = "",
        customer_name: str = "",
        limit: int = 25,
    ) -> str:
        """List invoices with optional filters.

        Args:
            status: Filter by status - Open, Paid, Overdue, or All (default: All).
            date_from: Start date filter in YYYY-MM-DD format.
            date_to: End date filter in YYYY-MM-DD format.
            customer_name: Filter by customer name (partial match).
            limit: Maximum number of invoices to return (default: 25, max: 100).

        Returns:
            Formatted list of invoices with number, customer, amount, due date, and status.
        """
        limit = min(max(1, limit), 100)

        qb = QueryBuilder("Invoice").select(
            ["Id", "DocNumber", "CustomerRef", "TotalAmt", "Balance",
             "DueDate", "TxnDate", "MetaData"]
        )

        if status.lower() == "open":
            qb.where("Balance", ">", "0")
        elif status.lower() == "paid":
            qb.where("Balance", "=", "0")

        if date_from:
            qb.where("TxnDate", ">=", date_from)
        if date_to:
            qb.where("TxnDate", "<=", date_to)
        if customer_name:
            qb.where("CustomerRef.name", "LIKE", f"%{customer_name}%")

        qb.order_by("TxnDate", "DESC").limit(limit)

        invoices = await qbo.query(qb.build())

        if not invoices:
            return "No invoices found matching your criteria."

        lines: list[str] = [f"Found {len(invoices)} invoice(s):\n"]

        for inv in invoices:
            inv_status = _invoice_status(inv)
            # Filter out non-overdue if specifically asking for overdue
            if status.lower() == "overdue" and inv_status != "OVERDUE":
                continue

            customer = inv.get("CustomerRef", {}).get("name", "Unknown")
            lines.append(
                f"  #{inv.get('DocNumber', 'N/A')} | {customer} | "
                f"Total: {format_currency(inv.get('TotalAmt'))} | "
                f"Balance: {format_currency(inv.get('Balance'))} | "
                f"Due: {format_date(inv.get('DueDate'))} | "
                f"Status: {inv_status}"
            )

        if status.lower() == "overdue":
            overdue_lines = [l for l in lines[1:] if l]  # noqa: E741
            if not overdue_lines:
                return "No overdue invoices found."
            total = len(overdue_lines)
            return f"Found {total} overdue invoice(s):\n" + "\n".join(overdue_lines)

        return "\n".join(lines)

    @server.tool()
    async def get_invoice_details(invoice_id: str) -> str:
        """Get full details for a specific invoice including line items.

        Args:
            invoice_id: The QuickBooks invoice ID.

        Returns:
            Detailed invoice information including line items, amounts,
            tax, customer info, and payment history.
        """
        invoice = await qbo.get("invoice", invoice_id)

        customer = invoice.get("CustomerRef", {}).get("name", "Unknown")
        status = _invoice_status(invoice)

        lines: list[str] = [
            f"Invoice #{invoice.get('DocNumber', 'N/A')}",
            f"{'=' * 50}",
            f"Customer:    {customer}",
            f"Date:        {format_date(invoice.get('TxnDate'))}",
            f"Due Date:    {format_date(invoice.get('DueDate'))}",
            f"Status:      {status}",
            f"",
            f"Line Items:",
        ]

        line_items = invoice.get("Line", [])
        for item in line_items:
            if item.get("DetailType") == "SalesItemLineDetail":
                detail = item.get("SalesItemLineDetail", {})
                desc = item.get("Description", "No description")
                qty = detail.get("Qty", 1)
                unit_price = detail.get("UnitPrice", 0)
                amount = item.get("Amount", 0)
                lines.append(
                    f"  - {desc}\n"
                    f"    Qty: {qty} x {format_currency(unit_price)} = "
                    f"{format_currency(amount)}"
                )
            elif item.get("DetailType") == "SubTotalLineDetail":
                lines.append(f"  {'─' * 40}")
                lines.append(f"  Subtotal: {format_currency(item.get('Amount'))}")

        lines.append(f"")
        lines.append(f"Subtotal:    {format_currency(invoice.get('TotalAmt'))}")

        tax_detail = invoice.get("TxnTaxDetail", {})
        if tax_detail.get("TotalTax"):
            lines.append(f"Tax:         {format_currency(tax_detail['TotalTax'])}")

        lines.append(f"Total:       {format_currency(invoice.get('TotalAmt'))}")
        lines.append(f"Balance Due: {format_currency(invoice.get('Balance'))}")

        if invoice.get("PrivateNote"):
            lines.append(f"")
            lines.append(f"Memo: {invoice['PrivateNote']}")

        if invoice.get("CustomerMemo", {}).get("value"):
            lines.append(f"Customer Memo: {invoice['CustomerMemo']['value']}")

        # Payment info
        deposit = invoice.get("Deposit", 0)
        if deposit and deposit > 0:
            lines.append(f"")
            lines.append(f"Deposit Received: {format_currency(deposit)}")

        linked = invoice.get("LinkedTxn", [])
        if linked:
            lines.append(f"")
            lines.append(f"Linked Transactions:")
            for txn in linked:
                lines.append(f"  - {txn.get('TxnType', 'Unknown')} #{txn.get('TxnId', 'N/A')}")

        return "\n".join(lines)

    @server.tool()
    async def get_overdue_invoices() -> str:
        """Get all overdue invoices sorted by days past due.

        Returns:
            Overdue invoices with days overdue and total outstanding amount.
        """
        qb = (
            QueryBuilder("Invoice")
            .select(["Id", "DocNumber", "CustomerRef", "TotalAmt", "Balance", "DueDate"])
            .where("Balance", ">", "0")
            .order_by("DueDate", "ASC")
            .limit(200)
        )

        invoices = await qbo.query(qb.build())

        overdue: list[dict[str, Any]] = []
        for inv in invoices:
            due_date = inv.get("DueDate")
            if due_date and days_between(due_date) > 0:
                inv["_days_overdue"] = days_between(due_date)
                overdue.append(inv)

        if not overdue:
            return "No overdue invoices. All invoices are current."

        # Sort by most overdue first
        overdue.sort(key=lambda x: x["_days_overdue"], reverse=True)

        from quickbooks_mcp.utils.money import Money

        total_outstanding = Money.sum(
            [Money.from_qbo(inv.get("Balance", 0)) for inv in overdue]
        )

        lines: list[str] = [
            f"Overdue Invoices: {len(overdue)} total | "
            f"Outstanding: {total_outstanding}\n",
        ]

        for inv in overdue:
            customer = inv.get("CustomerRef", {}).get("name", "Unknown")
            days = inv["_days_overdue"]
            urgency = "!!!" if days > 90 else "!!" if days > 60 else "!" if days > 30 else ""
            lines.append(
                f"  #{inv.get('DocNumber', 'N/A')} | {customer} | "
                f"Balance: {format_currency(inv.get('Balance'))} | "
                f"Due: {format_date(inv.get('DueDate'))} | "
                f"{days} days overdue {urgency}"
            )

        return "\n".join(lines)


def _invoice_status(invoice: dict[str, Any]) -> str:
    """Determine the display status of an invoice."""
    balance = float(invoice.get("Balance", 0))
    if balance == 0:
        return "PAID"

    due_date = invoice.get("DueDate")
    if due_date and days_between(due_date) > 0:
        return "OVERDUE"

    return "OPEN"
