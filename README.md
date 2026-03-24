# QuickBooks MCP Server

Connect Claude Desktop and Claude Code to QuickBooks Online for natural-language accounting. Ask questions about invoices, expenses, reports, and more using plain English.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)

---

## What is this?

An [MCP (Model Context Protocol)](https://modelcontextprotocol.io/) server that gives Claude direct access to your QuickBooks Online data. Instead of logging into QuickBooks and clicking through reports, just ask Claude:

> "Show me all overdue invoices sorted by amount"
> "What's our P&L this quarter?"
> "Create an invoice for Acme Corp for $2,500"

The server handles OAuth authentication, API calls, rate limiting, and data formatting.

---

## Quick Start

### 1. Install

```bash
pip install quickbooks-mcp
```

Or install from source:

```bash
git clone https://github.com/nyxtools/quickbooks-mcp-server.git
cd quickbooks-mcp-server
pip install -e .
```

### 2. Create a QuickBooks Developer App

1. Go to [developer.intuit.com](https://developer.intuit.com/)
2. Create an app and select **QuickBooks Online and Payments**
3. Under **Keys & OAuth**, note your **Client ID** and **Client Secret**
4. Add `http://localhost:8080/callback` as a **Redirect URI**

### 3. Set Environment Variables

```bash
export QBO_CLIENT_ID='your_client_id'
export QBO_CLIENT_SECRET='your_client_secret'
```

### 4. Run OAuth Setup

```bash
python scripts/setup_oauth.py
```

This opens your browser, authorizes with QuickBooks, and stores tokens locally (encrypted). Note the **Realm ID** it prints at the end.

```bash
export QBO_REALM_ID='your_realm_id'
```

### 5. Configure Claude Desktop

Add to your Claude Desktop config (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "quickbooks": {
      "command": "quickbooks-mcp",
      "env": {
        "QBO_CLIENT_ID": "your_client_id",
        "QBO_CLIENT_SECRET": "your_client_secret",
        "QBO_REALM_ID": "your_realm_id"
      }
    }
  }
}
```

**Config file locations:**
- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`
- Linux: `~/.config/Claude/claude_desktop_config.json`

### 6. Start Using It

Restart Claude Desktop and try:
> "What are my current bank account balances?"

---

## All 19 Tools

### Free Tier (9 tools)

| Tool | Description |
|------|-------------|
| `list_invoices` | List and filter invoices by status, date, customer |
| `get_invoice_details` | Full invoice details with line items and payment history |
| `get_overdue_invoices` | All overdue invoices sorted by days past due |
| `list_expenses` | List expenses with date, vendor, amount, and category filters |
| `get_top_expenses` | Top expenses grouped by category or vendor for any period |
| `get_account_balances` | Current balances for Bank, Credit Card, or all accounts |
| `get_account_transactions` | Recent transactions for any account with date filters |
| `search_customers` | Search customers by name or email with contact info |
| `get_customer_summary` | Customer financial summary: invoiced, paid, outstanding |

### Premium Tier (10 tools) -- $29/month

| Tool | Description |
|------|-------------|
| `get_profit_and_loss` | P&L report for any period with income/expense breakdown |
| `get_balance_sheet` | Balance sheet as of any date (assets, liabilities, equity) |
| `get_cash_flow` | Cash flow statement (operating, investing, financing) |
| `get_accounts_receivable_aging` | AR aging by customer (current/30/60/90+ days) |
| `get_accounts_payable_aging` | AP aging by vendor (current/30/60/90+ days) |
| `create_invoice` | Create invoices with line items, due dates, and memos |
| `record_payment` | Record payments against invoices with method and reference |
| `create_expense` | Record expenses with vendor, amount, category, and date |
| `get_financial_health` | Key ratios: current ratio, DSO, burn rate, runway |
| `compare_periods` | Side-by-side period comparison with % changes |

**Get a premium license at [nyxtools.dev/quickbooks-mcp](https://nyxtools.dev/quickbooks-mcp)**

Set it in your environment:
```bash
export LICENSE_KEY='your_license_key'
```

---

## Usage Examples

### Invoices
> "Show me all invoices from January"
> "Which invoices are overdue? Show me the worst ones first"
> "Get the details for invoice #1042"
> "Show me open invoices for Acme Corp"

### Expenses
> "What did we spend this month?"
> "Show me our top 10 expense categories this quarter"
> "How much have we spent at Amazon this year?"

### Accounts
> "What are our bank balances?"
> "Show me the last 20 transactions in checking"
> "What's the balance on our company credit card?"

### Customers
> "Find the customer John Smith"
> "Give me a financial summary for customer 456"
> "Search for customers with outstanding balances"

### Reports (Premium)
> "Show me the P&L for this quarter"
> "Pull up the balance sheet"
> "How's our cash flow this month?"
> "Show me the AR aging report"
> "Who are our slowest-paying customers?"

### Write Operations (Premium)
> "Create an invoice for customer 123: Website Design $2,500, Hosting $150/month, due net-30"
> "Record a $1,000 check payment on invoice #1042"
> "Record a $250 expense to Office Depot for supplies, paid by credit card on March 15"

### Analytics (Premium)
> "How healthy are our finances? Show me key ratios"
> "Compare this month to last month"
> "How did this quarter compare to the same quarter last year?"

---

## Configuration

All configuration is via environment variables:

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `QBO_CLIENT_ID` | Yes | | QuickBooks OAuth2 Client ID |
| `QBO_CLIENT_SECRET` | Yes | | QuickBooks OAuth2 Client Secret |
| `QBO_REALM_ID` | Yes | | QuickBooks Company/Realm ID |
| `QBO_REDIRECT_URI` | No | `http://localhost:8080/callback` | OAuth redirect URI |
| `LICENSE_KEY` | No | | Premium license key |
| `QBO_SANDBOX` | No | `false` | Use sandbox environment |
| `TOKEN_STORE_PATH` | No | `~/.quickbooks-mcp/tokens.json` | Token storage location |
| `LOG_LEVEL` | No | `INFO` | Logging level |

---

## Security

- **Tokens encrypted at rest** using machine-specific keys (Fernet + PBKDF2)
- **Tokens auto-refresh** -- access tokens last 60 min, refresh tokens 100 days
- **No credentials stored in code** -- all secrets via environment variables
- **Rate limiting built in** to respect QuickBooks API throttles
- **Input sanitization** on all query parameters to prevent injection

---

## Development

```bash
# Clone and install with dev dependencies
git clone https://github.com/nyxtools/quickbooks-mcp-server.git
cd quickbooks-mcp-server
pip install -e ".[dev]"

# Run tests
pytest

# Run with coverage
pytest --cov=quickbooks_mcp

# Lint
ruff check src/ tests/

# Type check
mypy src/
```

### Project Structure

```
quickbooks-mcp-server/
  src/quickbooks_mcp/
    auth/          # OAuth2 flow and encrypted token storage
    client/        # QBO REST API client with rate limiting
    tools/         # MCP tool implementations (19 tools)
    utils/         # Money (Decimal), formatting, license validation
    server.py      # MCP server setup and tool registration
    config.py      # Environment-based configuration
  scripts/
    setup_oauth.py # Interactive OAuth setup
  examples/        # Config examples and usage guide
  tests/           # Pytest test suite
```

---

## Troubleshooting

### "No QuickBooks tokens found"
Run the OAuth setup:
```bash
python scripts/setup_oauth.py
```

### "Token refresh failed"
Your refresh token may have expired. Re-run OAuth setup.

### "QuickBooks API error (HTTP 403)"
Verify your app has `com.intuit.quickbooks.accounting` scope.

### "Rate limited by QuickBooks"
The server handles rate limiting automatically. If you see this error, wait 60 seconds.

### "This is a premium feature"
Some tools require a license key. [Get one here](https://nyxtools.dev/quickbooks-mcp) or set `LICENSE_KEY` in your environment.

### Sandbox Mode
For testing without affecting real data:
```bash
export QBO_SANDBOX=true
```
Use your Development keys (not Production) from the Intuit developer dashboard.

---

## License

MIT License. See [LICENSE](LICENSE) for details.

Copyright (c) 2026 NyxTools · LEW Enterprises LLC
