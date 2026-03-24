# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-03-23

### Added
- Initial release of QuickBooks MCP Server
- Free tier tools:
  - `list_invoices` - List and filter invoices
  - `get_invoice_details` - Full invoice details with line items
  - `get_overdue_invoices` - Overdue invoices sorted by days past due
  - `list_expenses` - List and filter expenses/purchases
  - `get_top_expenses` - Top expenses by category or vendor
  - `get_account_balances` - Current account balances
  - `get_account_transactions` - Recent account transactions
  - `search_customers` - Customer search by name or email
  - `get_customer_summary` - Customer financial summary
- Premium tier tools ($29/mo):
  - `get_profit_and_loss` - Profit & Loss report
  - `get_balance_sheet` - Balance Sheet report
  - `get_cash_flow` - Cash Flow Statement
  - `get_accounts_receivable_aging` - AR Aging report
  - `get_accounts_payable_aging` - AP Aging report
  - `create_invoice` - Create new invoices
  - `record_payment` - Record payments against invoices
  - `create_expense` - Record expenses
  - `get_financial_health` - Financial health metrics
  - `compare_periods` - Period-over-period comparison
- OAuth2 authentication with automatic token refresh
- Encrypted local token storage
- Interactive OAuth setup script
- Claude Desktop and Claude Code configuration support
- Lemon Squeezy license key validation for premium features
