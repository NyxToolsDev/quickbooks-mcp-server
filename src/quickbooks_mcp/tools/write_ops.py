"""Write operation tools (premium tier).

Provides tools to create invoices, record payments, and record expenses
in QuickBooks Online. All write operations require a premium license.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from mcp.server import Server

from quickbooks_mcp.client.qbo_client import QBOClient
from quickbooks_mcp.utils.formatting import format_currency
from quickbooks_mcp.utils.license import require_premium, validate_license
from quickbooks_mcp.utils.money import Money

logger = logging.getLogger(__name__)


def register_write_tools(server: Server, qbo: QBOClient, license_key: str) -> None:
    """Register all write operation tools with the MCP server.

    All write tools require a valid premium license and perform
    validation before submitting to the QuickBooks API.

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
    async def create_invoice(
        customer_id: str,
        line_items: list[dict[str, Any]],
        due_date: str = "",
        memo: str = "",
        email_to_customer: bool = False,
    ) -> str:
        """Create a new invoice in QuickBooks.

        Requires a premium license.

        Args:
            customer_id: The QuickBooks customer ID to invoice.
            line_items: List of line items, each with:
                - description (str): Item description
                - amount (float): Line total amount
                - quantity (float, optional): Quantity (default: 1)
                - unit_price (float, optional): Price per unit
                - service_date (str, optional): Service date YYYY-MM-DD
            due_date: Invoice due date in YYYY-MM-DD format (optional).
            memo: Private memo/note for the invoice (optional).
            email_to_customer: Whether to email the invoice to the customer (default: false).

        Returns:
            Confirmation with the new invoice number, total, and ID.
        """
        premium_error = await _check_premium()
        if premium_error:
            return premium_error

        if not customer_id:
            return "Error: customer_id is required. Use search_customers to find a customer ID."

        if not line_items:
            return "Error: At least one line item is required."

        # Build invoice line items
        qbo_lines: list[dict[str, Any]] = []
        total = Money(0)

        for i, item in enumerate(line_items):
            description = item.get("description", "")
            amount_raw = item.get("amount")
            quantity = item.get("quantity", 1)
            unit_price = item.get("unit_price")
            service_date = item.get("service_date", "")

            if amount_raw is None and unit_price is None:
                return f"Error: Line item {i + 1} must have either 'amount' or 'unit_price'."

            # Calculate amount from quantity * unit_price if amount not given
            if amount_raw is not None:
                line_amount = Money.from_qbo(amount_raw)
            else:
                line_amount = Money(Decimal(str(quantity)) * Decimal(str(unit_price)))

            total = total + line_amount

            line_detail: dict[str, Any] = {
                "DetailType": "SalesItemLineDetail",
                "Amount": line_amount.to_float(),
                "Description": description,
                "SalesItemLineDetail": {
                    "Qty": quantity,
                    "UnitPrice": float(unit_price) if unit_price else line_amount.to_float(),
                },
            }

            if service_date:
                line_detail["SalesItemLineDetail"]["ServiceDate"] = service_date

            qbo_lines.append(line_detail)

        # Build the invoice body
        invoice_body: dict[str, Any] = {
            "CustomerRef": {"value": customer_id},
            "Line": qbo_lines,
        }

        if due_date:
            invoice_body["DueDate"] = due_date

        if memo:
            invoice_body["PrivateNote"] = memo

        if email_to_customer:
            invoice_body["EmailStatus"] = "NeedToSend"
            invoice_body["BillEmail"] = {"Address": ""}  # Uses customer's email on file

        # Create the invoice
        result = await qbo.create("invoice", invoice_body)

        invoice_id = result.get("Id", "Unknown")
        doc_number = result.get("DocNumber", "N/A")
        created_total = Money.from_qbo(result.get("TotalAmt", 0))

        response_lines = [
            "Invoice created successfully!",
            f"  Invoice #:  {doc_number}",
            f"  Invoice ID: {invoice_id}",
            f"  Customer:   {result.get('CustomerRef', {}).get('name', customer_id)}",
            f"  Total:      {format_currency(created_total)}",
            f"  Line Items: {len(qbo_lines)}",
        ]

        if due_date:
            response_lines.append(f"  Due Date:   {due_date}")
        if email_to_customer:
            response_lines.append(f"  Email:      Queued to send")

        return "\n".join(response_lines)

    @server.tool()
    async def record_payment(
        invoice_id: str,
        amount: float,
        payment_date: str = "",
        payment_method: str = "",
        reference_number: str = "",
        memo: str = "",
    ) -> str:
        """Record a payment against an existing invoice.

        Requires a premium license.

        Args:
            invoice_id: The QuickBooks invoice ID to apply payment to.
            amount: Payment amount (must be positive).
            payment_date: Payment date in YYYY-MM-DD format (default: today).
            payment_method: Payment method (e.g., Cash, Check, Credit Card, ACH, Other).
            reference_number: Check number or transaction reference (optional).
            memo: Private memo for the payment (optional).

        Returns:
            Confirmation with payment details and remaining invoice balance.
        """
        premium_error = await _check_premium()
        if premium_error:
            return premium_error

        if not invoice_id:
            return "Error: invoice_id is required."

        payment_amount = Money.from_qbo(amount)
        if payment_amount <= 0:
            return "Error: Payment amount must be positive."

        # Fetch the invoice to validate and get customer reference
        invoice = await qbo.get("invoice", invoice_id)
        customer_ref = invoice.get("CustomerRef", {})
        current_balance = Money.from_qbo(invoice.get("Balance", 0))

        if current_balance <= 0:
            return (
                f"Invoice #{invoice.get('DocNumber', invoice_id)} is already fully paid. "
                f"No payment recorded."
            )

        if payment_amount > current_balance:
            return (
                f"Payment amount ({format_currency(payment_amount)}) exceeds "
                f"invoice balance ({format_currency(current_balance)}). "
                f"Please enter an amount up to {format_currency(current_balance)}."
            )

        # Build payment body
        payment_body: dict[str, Any] = {
            "TotalAmt": payment_amount.to_float(),
            "CustomerRef": customer_ref,
            "Line": [
                {
                    "Amount": payment_amount.to_float(),
                    "LinkedTxn": [
                        {
                            "TxnId": invoice_id,
                            "TxnType": "Invoice",
                        }
                    ],
                }
            ],
        }

        if payment_date:
            payment_body["TxnDate"] = payment_date

        if payment_method:
            # Payment method needs to be looked up by name; use inline ref
            payment_body["PaymentMethodRef"] = {"name": payment_method}

        if reference_number:
            payment_body["PaymentRefNum"] = reference_number

        if memo:
            payment_body["PrivateNote"] = memo

        # Create the payment
        result = await qbo.create("payment", payment_body)

        payment_id = result.get("Id", "Unknown")
        remaining = current_balance - payment_amount

        response_lines = [
            "Payment recorded successfully!",
            f"  Payment ID:    {payment_id}",
            f"  Amount:        {format_currency(payment_amount)}",
            f"  Applied To:    Invoice #{invoice.get('DocNumber', invoice_id)}",
            f"  Customer:      {customer_ref.get('name', 'Unknown')}",
        ]

        if payment_date:
            response_lines.append(f"  Date:          {payment_date}")
        if payment_method:
            response_lines.append(f"  Method:        {payment_method}")
        if reference_number:
            response_lines.append(f"  Reference:     {reference_number}")

        response_lines.append(
            f"  Remaining Bal: {format_currency(remaining)}"
            + (" (PAID IN FULL)" if remaining <= 0 else "")
        )

        return "\n".join(response_lines)

    @server.tool()
    async def create_expense(
        vendor_name: str,
        amount: float,
        category: str = "",
        account_name: str = "",
        payment_type: str = "Cash",
        expense_date: str = "",
        memo: str = "",
        reference_number: str = "",
    ) -> str:
        """Record a new expense/purchase in QuickBooks.

        Requires a premium license.

        Args:
            vendor_name: Vendor/payee name.
            amount: Expense total amount (must be positive).
            category: Expense category/account name (e.g., Office Supplies, Rent).
            account_name: Bank/credit card account used for payment.
            payment_type: Cash, Check, or CreditCard (default: Cash).
            expense_date: Expense date in YYYY-MM-DD format (default: today).
            memo: Description or memo for the expense (optional).
            reference_number: Check number or reference (optional).

        Returns:
            Confirmation with expense details and ID.
        """
        premium_error = await _check_premium()
        if premium_error:
            return premium_error

        if not vendor_name:
            return "Error: vendor_name is required."

        expense_amount = Money.from_qbo(amount)
        if expense_amount <= 0:
            return "Error: Expense amount must be positive."

        valid_payment_types = {"cash", "check", "creditcard"}
        payment_type_normalized = payment_type.lower().replace(" ", "").replace("_", "")
        if payment_type_normalized not in valid_payment_types:
            return (
                f"Invalid payment_type '{payment_type}'. "
                f"Valid options: Cash, Check, CreditCard"
            )

        # Map normalized type to QBO value
        payment_type_map = {
            "cash": "Cash",
            "check": "Check",
            "creditcard": "CreditCard",
        }
        qbo_payment_type = payment_type_map[payment_type_normalized]

        # Look up vendor by name
        from quickbooks_mcp.client.query_builder import QueryBuilder

        vendor_qb = (
            QueryBuilder("Vendor")
            .select(["Id", "DisplayName"])
            .where("DisplayName", "LIKE", f"%{vendor_name}%")
            .limit(1)
        )
        vendors = await qbo.query(vendor_qb.build())

        vendor_ref: dict[str, str] = {}
        if vendors:
            vendor_ref = {
                "value": str(vendors[0]["Id"]),
                "name": vendors[0].get("DisplayName", vendor_name),
            }
        else:
            # If vendor not found, QBO may create on write or we use name ref
            vendor_ref = {"name": vendor_name}

        # Build expense line items
        line_detail: dict[str, Any] = {
            "DetailType": "AccountBasedExpenseLineDetail",
            "Amount": expense_amount.to_float(),
            "Description": memo or f"Expense - {vendor_name}",
            "AccountBasedExpenseLineDetail": {},
        }

        # Look up category/expense account if provided
        if category:
            acct_qb = (
                QueryBuilder("Account")
                .select(["Id", "Name"])
                .where("Name", "LIKE", f"%{category}%")
                .where("AccountType", "=", "Expense")
                .limit(1)
            )
            accounts = await qbo.query(acct_qb.build())
            if accounts:
                line_detail["AccountBasedExpenseLineDetail"]["AccountRef"] = {
                    "value": str(accounts[0]["Id"]),
                    "name": accounts[0].get("Name", category),
                }

        # Build purchase body
        purchase_body: dict[str, Any] = {
            "PaymentType": qbo_payment_type,
            "TotalAmt": expense_amount.to_float(),
            "EntityRef": vendor_ref,
            "Line": [line_detail],
        }

        # Look up payment account if provided
        if account_name:
            pay_acct_qb = (
                QueryBuilder("Account")
                .select(["Id", "Name"])
                .where("Name", "LIKE", f"%{account_name}%")
                .limit(1)
            )
            pay_accounts = await qbo.query(pay_acct_qb.build())
            if pay_accounts:
                purchase_body["AccountRef"] = {
                    "value": str(pay_accounts[0]["Id"]),
                    "name": pay_accounts[0].get("Name", account_name),
                }

        if expense_date:
            purchase_body["TxnDate"] = expense_date

        if memo:
            purchase_body["PrivateNote"] = memo

        if reference_number:
            purchase_body["DocNumber"] = reference_number

        # Create the purchase/expense
        result = await qbo.create("purchase", purchase_body)

        expense_id = result.get("Id", "Unknown")
        resolved_vendor = result.get("EntityRef", {}).get("name", vendor_name)

        response_lines = [
            "Expense recorded successfully!",
            f"  Expense ID:    {expense_id}",
            f"  Vendor:        {resolved_vendor}",
            f"  Amount:        {format_currency(expense_amount)}",
            f"  Payment Type:  {qbo_payment_type}",
        ]

        if category:
            response_lines.append(f"  Category:      {category}")
        if expense_date:
            response_lines.append(f"  Date:          {expense_date}")
        if memo:
            response_lines.append(f"  Memo:          {memo}")
        if reference_number:
            response_lines.append(f"  Reference:     {reference_number}")

        return "\n".join(response_lines)
