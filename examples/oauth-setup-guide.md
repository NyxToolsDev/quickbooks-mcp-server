# OAuth Setup Guide for QuickBooks MCP Server

Step-by-step guide to connect QuickBooks Online to the MCP server.

---

## Prerequisites

1. A QuickBooks Online account (even a trial works)
2. Python 3.10 or newer
3. The quickbooks-mcp package installed

---

## Step 1: Create a QuickBooks Developer App

1. Go to [developer.intuit.com](https://developer.intuit.com/)
2. Sign in with your Intuit account
3. Click **Dashboard** then **Create an app**
4. Select **QuickBooks Online and Payments**
5. Give your app a name (e.g., "Claude MCP Integration")
6. Click **Create**

---

## Step 2: Configure Your App

1. In your app dashboard, go to **Keys & OAuth**
2. Note your **Client ID** and **Client Secret**
3. Under **Redirect URIs**, add:
   ```
   http://localhost:8080/callback
   ```
4. Save changes

### Production vs Sandbox

- **Development/Sandbox keys** work with QuickBooks sandbox data (safe for testing)
- **Production keys** connect to your real QuickBooks data

For testing, start with Development keys and set `QBO_SANDBOX=true`.

---

## Step 3: Set Environment Variables

### Linux/macOS
```bash
export QBO_CLIENT_ID='ABxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'
export QBO_CLIENT_SECRET='xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'
```

### Windows (PowerShell)
```powershell
$env:QBO_CLIENT_ID = 'ABxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'
$env:QBO_CLIENT_SECRET = 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'
```

### Windows (Command Prompt)
```cmd
set QBO_CLIENT_ID=ABxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
set QBO_CLIENT_SECRET=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

### Using a .env file
Create a `.env` file (never commit this!):
```
QBO_CLIENT_ID=ABxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
QBO_CLIENT_SECRET=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
QBO_SANDBOX=true
```

Then source it:
```bash
source .env  # or use dotenv in your workflow
```

---

## Step 4: Run the OAuth Setup

```bash
python scripts/setup_oauth.py
```

What happens:
1. A local web server starts on port 8080
2. Your browser opens the QuickBooks authorization page
3. You sign in and authorize the app
4. QuickBooks redirects back to localhost with an authorization code
5. The script exchanges the code for access tokens
6. Tokens are encrypted and stored locally

The script will display your **Realm ID** (company ID). Note this down.

---

## Step 5: Set the Realm ID

```bash
export QBO_REALM_ID='123456789012345'
```

---

## Step 6: Configure Claude Desktop

Edit your Claude Desktop config file:

**macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
**Windows:** `%APPDATA%\Claude\claude_desktop_config.json`
**Linux:** `~/.config/Claude/claude_desktop_config.json`

Add the QuickBooks server:

```json
{
  "mcpServers": {
    "quickbooks": {
      "command": "quickbooks-mcp",
      "env": {
        "QBO_CLIENT_ID": "your_client_id",
        "QBO_CLIENT_SECRET": "your_client_secret",
        "QBO_REALM_ID": "your_realm_id",
        "QBO_SANDBOX": "false"
      }
    }
  }
}
```

---

## Step 7: Test the Connection

Restart Claude Desktop and try:
> "Show me my QuickBooks bank account balances"

If everything is configured correctly, Claude will connect to your QuickBooks and return your account data.

---

## Token Lifecycle

- **Access tokens** expire after 60 minutes and are auto-refreshed
- **Refresh tokens** expire after 100 days if not used
- Tokens are encrypted at rest using machine-specific keys
- If tokens expire completely, re-run `python scripts/setup_oauth.py`

---

## Troubleshooting

### "No QuickBooks tokens found"
Run the OAuth setup script again:
```bash
python scripts/setup_oauth.py
```

### "Token refresh failed"
Your refresh token may have expired (100-day limit). Re-authorize:
```bash
python scripts/setup_oauth.py
```

### "QuickBooks API error (HTTP 403)"
Check that your app has the correct scopes. The app needs the `com.intuit.quickbooks.accounting` scope.

### "Rate limited by QuickBooks"
The server includes built-in rate limiting, but if you hit limits, wait a minute and try again.

### Browser Doesn't Open
Copy the authorization URL from the terminal and paste it into your browser manually.

### Port 8080 Already in Use
Set a different redirect URI:
```bash
export QBO_REDIRECT_URI='http://localhost:9090/callback'
```
Make sure this matches the redirect URI in your QuickBooks app settings.
