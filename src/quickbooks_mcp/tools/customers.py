"""Customer query tools (free tier).

Provides search and summary views of QuickBooks customer data
including contact information, balances, and payment history.
"""

from __future__ import annotations

import logging

from mcp.server import Server

from quickbooks_mcp.client.qbo_client import QBOClient
from quickbooks_mcp.client.query_builder import QueryBuilder
from quickbooks_mcp.utils.formatting import format_currency, format_date
from quickbooks_mcp.utils.money import Money

logger = logging.getLogger(__name__)


def register_customer_tools(server: Server, qbo: QBOClient) -> None:
    """Register all customer-related tools with the MCP server.

    Args:
        server: The MCP server instance.
        qbo: The QuickBooks API client.
    """

    @server.tool()
    async def search_customers(
        query: str = "",
        include_inactive: bool = False,
        limit: int = 25,
    ) -> str:
        """Search customers by name or email address.

        Args:
            query: Search term to match against customer name or email (partial match).
                Leave empty to list all customers.
            include_inactive: Include inactive/archived customers (default: false).
            limit: Maximum number of customers to return (default: 25, max: 100).

        Returns:
            Customer list with name, email, phone, balance due, and status.
        """
        limit = min(max(1, limit), 100)

        qb = QueryBuilder("Customer").select(
            ["Id", "DisplayName", "PrimaryEmailAddr", "PrimaryPhone",
             "Balance", "Active", "CompanyName", "MetaData"]
        )

        if not include_inactive:
            qb.where("Active", "=", "true")

        if query:
            # QBO supports LIKE on DisplayName
            qb.where("DisplayName", "LIKE", f"%{query}%")

        qb.order_by("DisplayName", "ASC").limit(limit)

        customers = await qbo.query(qb.build())

        # If name search returned nothing, try email search
        if not customers and query and "@" in query:
            qb_email = QueryBuilder("Customer").select(
                ["Id", "DisplayName", "PrimaryEmailAddr", "PrimaryPhone",
                 "Balance", "Active", "CompanyName", "MetaData"]
            )
            if not include_inactive:
                qb_email.where("Active", "=", "true")
            qb_email.where("PrimaryEmailAddr", "LIKE", f"%{query}%")
            qb_email.order_by("DisplayName", "ASC").limit(limit)
            customers = await qbo.query(qb_email.build())

        if not customers:
            return f"No customers found matching '{query}'." if query else "No customers found."

        total_balance = Money.sum(
            [Money.from_qbo(c.get("Balance", 0)) for c in customers]
        )

        lines: list[str] = [
            f"Found {len(customers)} customer(s) | "
            f"Total Balance Due: {format_currency(total_balance)}\n"
        ]

        for cust in customers:
            name = cust.get("DisplayName", "Unknown")
            company = cust.get("CompanyName", "")
            email_data = cust.get("PrimaryEmailAddr", {})
            email = email_data.get("Address", "") if isinstance(email_data, dict) else ""
            phone_data = cust.get("PrimaryPhone", {})
            phone = phone_data.get("FreeFormNumber", "") if isinstance(phone_data, dict) else ""
            balance = Money.from_qbo(cust.get("Balance", 0))
            active = cust.get("Active", True)

            status = "" if active else " [INACTIVE]"
            company_label = f" ({company})" if company and company != name else ""

            contact_parts: list[str] = []
            if email:
                contact_parts.append(email)
            if phone:
                contact_parts.append(phone)
            contact = " | ".join(contact_parts) if contact_parts else "No contact info"

            balance_str = format_currency(balance)
            balance_flag = " ***" if balance > 0 else ""

            lines.append(
                f"  [{cust.get('Id', '?')}] {name}{company_label}{status}\n"
                f"      Contact: {contact}\n"
                f"      Balance Due: {balance_str}{balance_flag}"
            )

        return "\n".join(lines)

    @server.tool()
    async def get_customer_summary(
        customer_id: str = "",
        customer_name: str = "",
    ) -> str:
        """Get a financial summary for a specific customer.

        Includes total invoiced, total paid, outstanding balance, and
        most recent payment information. Provide either customer_id or customer_name.

        Args:
            customer_id: The QuickBooks customer ID.
            customer_name: Search by customer name (uses first match).

        Returns:
            Comprehensive financial summary for the customer.
        """
        # Resolve customer name to ID if needed
        resolved_id = customer_id
        customer_display_name = customer_name

        if not resolved_id and customer_name:
            search_qb = (
                QueryBuilder("Customer")
                .select(["Id", "DisplayName"])
                .where("DisplayName", "LIKE", f"%{customer_name}%")
                .limit(1)
            )
            results = await qbo.query(search_qb.build())
            if not results:
                return f"No customer found matching '{customer_name}'."
            resolved_id = str(results[0]["Id"])
            customer_display_name = results[0].get("DisplayName", customer_name)

        if not resolved_id:
            return (
                "Please provide either a customer_id or customer_name. "
                "Use search_customers to find customer IDs."
            )

        # Fetch customer details
        customer = await qbo.get("customer", resolved_id)
        customer_display_name = customer.get("DisplayName", customer_display_name)
        company = customer.get("CompanyName", "")

        # Fetch all invoices for this customer
        inv_qb = (
            QueryBuilder("Invoice")
            .select(["Id", "DocNumber", "TotalAmt", "Balance", "TxnDate", "DueDate"])
            .where("CustomerRef", "=", resolved_id)
            .order_by("TxnDate", "DESC")
            .limit(500)
        )
        invoices = await qbo.query(inv_qb.build())

        # Fetch payments for this customer
        pay_qb = (
            QueryBuilder("Payment")
            .select(["Id", "TotalAmt", "TxnDate", "PaymentMethodRef"])
            .where("CustomerRef", "=", resolved_id)
            .order_by("TxnDate", "DESC")
            .limit(500)
        )
        payments = await qbo.query(pay_qb.build())

        # Calculate totals
        total_invoiced = Money.sum(
            [Money.from_qbo(inv.get("TotalAmt", 0)) for inv in invoices]
        )
        total_outstanding = Money.sum(
            [Money.from_qbo(inv.get("Balance", 0)) for inv in invoices if inv.get("Balance", 0)]
        )
        total_paid = Money.sum(
            [Money.from_qbo(pay.get("TotalAmt", 0)) for pay in payments]
        )

        # Count overdue invoices
        from quickbooks_mcp.utils.formatting import days_between
        overdue_count = 0
        overdue_amount = Money(0)
        for inv in invoices:
            balance = float(inv.get("Balance", 0))
            due_date = inv.get("DueDate", "")
            if balance > 0 and due_date and days_between(due_date) > 0:
                overdue_count += 1
                overdue_amount = overdue_amount + Money.from_qbo(balance)

        # Build summary
        lines: list[str] = [
            f"Customer Summary: {customer_display_name}",
            f"{'=' * 50}",
        ]

        if company and company != customer_display_name:
            lines.append(f"Company:          {company}")

        email_data = customer.get("PrimaryEmailAddr", {})
        email = email_data.get("Address", "") if isinstance(email_data, dict) else ""
        phone_data = customer.get("PrimaryPhone", {})
        phone = phone_data.get("FreeFormNumber", "") if isinstance(phone_data, dict) else ""

        if email:
            lines.append(f"Email:            {email}")
        if phone:
            lines.append(f"Phone:            {phone}")

        lines.append(f"Customer ID:      {resolved_id}")
        lines.append(f"")
        lines.append(f"Financial Summary:")
        lines.append(f"  Total Invoiced:   {format_currency(total_invoiced)}")
        lines.append(f"  Total Paid:       {format_currency(total_paid)}")
        lines.append(f"  Outstanding:      {format_currency(total_outstanding)}")
        lines.append(f"  Invoice Count:    {len(invoices)}")
        lines.append(f"  Payment Count:    {len(payments)}")

        if overdue_count > 0:
            lines.append(f"")
            lines.append(f"  Overdue Invoices: {overdue_count}")
            lines.append(f"  Overdue Amount:   {format_currency(overdue_amount)}")

        # Most recent invoice
        if invoices:
            recent_inv = invoices[0]
            lines.append(f"")
            lines.append(
                f"  Last Invoice:     #{recent_inv.get('DocNumber', 'N/A')} "
                f"on {format_date(recent_inv.get('TxnDate'))} "
                f"for {format_currency(recent_inv.get('TotalAmt'))}"
            )

        # Most recent payment
        if payments:
            recent_pay = payments[0]
            method_ref = recent_pay.get("PaymentMethodRef", {})
            method = method_ref.get("name", "Unknown") if isinstance(method_ref, dict) else "Unknown"
            lines.append(
                f"  Last Payment:     {format_date(recent_pay.get('TxnDate'))} "
                f"for {format_currency(recent_pay.get('TotalAmt'))} "
                f"via {method}"
            )

        return "\n".join(lines)
