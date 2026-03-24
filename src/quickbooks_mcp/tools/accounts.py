"""Account balance and transaction tools (free tier).

Provides access to QuickBooks chart of accounts data including
current balances and recent transaction history.
"""

from __future__ import annotations

import logging
from typing import Any

from mcp.server import Server

from quickbooks_mcp.client.qbo_client import QBOClient
from quickbooks_mcp.client.query_builder import QueryBuilder
from quickbooks_mcp.utils.formatting import format_currency, format_date
from quickbooks_mcp.utils.money import Money

logger = logging.getLogger(__name__)


def register_account_tools(server: Server, qbo: QBOClient) -> None:
    """Register all account-related tools with the MCP server.

    Args:
        server: The MCP server instance.
        qbo: The QuickBooks API client.
    """

    @server.tool()
    async def get_account_balances(
        account_type: str = "All",
    ) -> str:
        """Get current balances for your accounts by type.

        Args:
            account_type: Filter by account type - Bank, CreditCard, or All (default: All).

        Returns:
            Formatted list of accounts with names, types, and current balances.
        """
        valid_types = {"bank", "creditcard", "all"}
        account_type_lower = account_type.lower().replace(" ", "").replace("_", "")

        if account_type_lower not in valid_types:
            return (
                f"Invalid account type '{account_type}'. "
                f"Valid options: Bank, CreditCard, All"
            )

        qb = QueryBuilder("Account").select(
            ["Id", "Name", "AccountType", "AccountSubType",
             "CurrentBalance", "Active"]
        )

        if account_type_lower == "bank":
            qb.where("AccountType", "=", "Bank")
        elif account_type_lower == "creditcard":
            qb.where("AccountType", "=", "Credit Card")

        qb.where("Active", "=", "true").order_by("Name", "ASC").limit(200)

        accounts = await qbo.query(qb.build())

        if not accounts:
            return f"No {account_type} accounts found."

        # Group accounts by type
        grouped: dict[str, list[dict[str, Any]]] = {}
        for acct in accounts:
            acct_type = acct.get("AccountType", "Other")
            if acct_type not in grouped:
                grouped[acct_type] = []
            grouped[acct_type].append(acct)

        lines: list[str] = [f"Account Balances ({account_type}):\n"]

        total_assets = Money(0)
        total_liabilities = Money(0)

        for acct_type, accts in sorted(grouped.items()):
            lines.append(f"  {acct_type}:")
            type_total = Money(0)

            for acct in sorted(accts, key=lambda a: a.get("Name", "")):
                balance = Money.from_qbo(acct.get("CurrentBalance", 0))
                name = acct.get("Name", "Unknown")
                sub_type = acct.get("AccountSubType", "")
                sub_label = f" ({sub_type})" if sub_type else ""

                lines.append(
                    f"    {name}{sub_label}: {format_currency(balance)}"
                )
                type_total = type_total + balance

            lines.append(f"    {'─' * 40}")
            lines.append(f"    {acct_type} Total: {format_currency(type_total)}\n")

            if acct_type in ("Bank", "Other Current Asset", "Fixed Asset"):
                total_assets = total_assets + type_total
            elif acct_type in ("Credit Card", "Other Current Liability", "Long Term Liability"):
                total_liabilities = total_liabilities + type_total

        if account_type_lower == "all":
            lines.append(f"Summary:")
            lines.append(f"  Total Bank/Asset Balances: {format_currency(total_assets)}")
            lines.append(
                f"  Total Credit Card/Liability Balances: {format_currency(total_liabilities)}"
            )

        return "\n".join(lines)

    @server.tool()
    async def get_account_transactions(
        account_id: str = "",
        account_name: str = "",
        date_from: str = "",
        date_to: str = "",
        limit: int = 25,
    ) -> str:
        """Get recent transactions for a specific account.

        You must provide either account_id or account_name.

        Args:
            account_id: The QuickBooks account ID.
            account_name: Search by account name (will find the first match).
            date_from: Start date filter in YYYY-MM-DD format.
            date_to: End date filter in YYYY-MM-DD format.
            limit: Maximum number of transactions to return (default: 25, max: 100).

        Returns:
            Recent transactions with dates, descriptions, amounts, and running context.
        """
        limit = min(max(1, limit), 100)

        # Resolve account name to ID if needed
        resolved_account_id = account_id
        resolved_account_name = account_name

        if not resolved_account_id and account_name:
            acct_query = (
                QueryBuilder("Account")
                .select(["Id", "Name"])
                .where("Name", "LIKE", f"%{account_name}%")
                .limit(1)
            )
            accounts = await qbo.query(acct_query.build())
            if not accounts:
                return f"No account found matching '{account_name}'."
            resolved_account_id = str(accounts[0]["Id"])
            resolved_account_name = accounts[0].get("Name", account_name)

        if not resolved_account_id:
            return (
                "Please provide either an account_id or account_name. "
                "Use get_account_balances to see available accounts."
            )

        # Build report parameters for the TransactionList detail report
        params: dict[str, str] = {
            "account": resolved_account_id,
            "columns": "tx_date,txn_type,name,memo,subt_nat_amount,rbal_nat_amount",
        }

        if date_from:
            params["start_date"] = date_from
        if date_to:
            params["end_date"] = date_to

        try:
            report = await qbo.get_report("TransactionList", params=params)
        except Exception as exc:
            # Fallback: query purchases and journal entries directly
            logger.warning("TransactionList report failed, using query fallback: %s", exc)
            return await _query_transactions_fallback(
                qbo, resolved_account_id, resolved_account_name, date_from, date_to, limit
            )

        # Parse the report response
        lines: list[str] = [
            f"Transactions for {resolved_account_name or f'Account #{resolved_account_id}'}:\n"
        ]

        columns = report.get("Columns", {}).get("Column", [])
        col_names = [col.get("ColTitle", "") for col in columns]

        rows = report.get("Rows", {}).get("Row", [])
        if not rows:
            return f"No transactions found for this account in the specified period."

        count = 0
        for row in rows:
            if count >= limit:
                break
            col_data = row.get("ColData", [])
            if not col_data:
                # Check for section rows
                section_rows = row.get("Rows", {}).get("Row", [])
                for sub_row in section_rows:
                    if count >= limit:
                        break
                    sub_data = sub_row.get("ColData", [])
                    if sub_data:
                        line = _format_transaction_row(col_names, sub_data)
                        if line:
                            lines.append(f"  {line}")
                            count += 1
            else:
                line = _format_transaction_row(col_names, col_data)
                if line:
                    lines.append(f"  {line}")
                    count += 1

        lines.append(f"\nShowing {count} transaction(s)")
        return "\n".join(lines)


def _format_transaction_row(
    col_names: list[str], col_data: list[dict[str, Any]]
) -> str:
    """Format a single transaction row from a report response.

    Args:
        col_names: Column header names.
        col_data: Column data values.

    Returns:
        Formatted transaction string, or empty string if not a data row.
    """
    values: dict[str, str] = {}
    for i, col in enumerate(col_data):
        if i < len(col_names):
            values[col_names[i]] = col.get("value", "")

    date_val = values.get("Date", values.get("tx_date", ""))
    txn_type = values.get("Transaction Type", values.get("txn_type", ""))
    name = values.get("Name", values.get("name", ""))
    memo = values.get("Memo", values.get("memo", ""))
    amount = values.get("Amount", values.get("subt_nat_amount", ""))
    balance = values.get("Balance", values.get("rbal_nat_amount", ""))

    if not date_val and not amount:
        return ""

    parts = [format_date(date_val) if date_val else ""]
    if txn_type:
        parts.append(txn_type)
    if name:
        parts.append(name)
    if memo:
        parts.append(memo[:30])
    if amount:
        parts.append(f"Amount: {format_currency(amount)}")
    if balance:
        parts.append(f"Bal: {format_currency(balance)}")

    return " | ".join(p for p in parts if p)


async def _query_transactions_fallback(
    qbo: QBOClient,
    account_id: str,
    account_name: str,
    date_from: str,
    date_to: str,
    limit: int,
) -> str:
    """Fallback method to get transactions when the report API is unavailable.

    Queries purchases directly instead of using the TransactionList report.

    Args:
        qbo: The QuickBooks API client.
        account_id: The account ID to query.
        account_name: The account name for display.
        date_from: Start date filter.
        date_to: End date filter.
        limit: Maximum results.

    Returns:
        Formatted transaction list.
    """
    qb = (
        QueryBuilder("Purchase")
        .select(["Id", "TxnDate", "TotalAmt", "EntityRef", "AccountRef", "PaymentType"])
        .where("AccountRef", "=", account_id)
    )

    if date_from:
        qb.where("TxnDate", ">=", date_from)
    if date_to:
        qb.where("TxnDate", "<=", date_to)

    qb.order_by("TxnDate", "DESC").limit(limit)

    transactions = await qbo.query(qb.build())

    if not transactions:
        return f"No transactions found for {account_name or f'Account #{account_id}'}."

    lines: list[str] = [
        f"Transactions for {account_name or f'Account #{account_id}'}:\n"
    ]

    for txn in transactions:
        vendor = txn.get("EntityRef", {}).get("name", "")
        payment_type = txn.get("PaymentType", "")
        lines.append(
            f"  {format_date(txn.get('TxnDate'))} | "
            f"{vendor or 'N/A'} | "
            f"{format_currency(txn.get('TotalAmt'))} | "
            f"{payment_type}"
        )

    lines.append(f"\nShowing {len(transactions)} transaction(s)")
    return "\n".join(lines)
