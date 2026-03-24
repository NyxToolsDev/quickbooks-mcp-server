#!/usr/bin/env python3
"""Interactive OAuth2 setup for QuickBooks Online.

Opens a browser for QuickBooks authorization, runs a local callback server
on port 8080, exchanges the authorization code for tokens, and stores them
securely using the encrypted token store.

Usage:
    python -m quickbooks_mcp.scripts.setup_oauth

    Or run directly:
    python scripts/setup_oauth.py

Environment variables required:
    QBO_CLIENT_ID     - QuickBooks OAuth2 Client ID
    QBO_CLIENT_SECRET - QuickBooks OAuth2 Client Secret
"""

from __future__ import annotations

import asyncio
import os
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread
from typing import Any
from urllib.parse import parse_qs, urlparse

# Add src to path for direct script execution
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


def main() -> None:
    """Run the interactive OAuth setup flow."""
    print("=" * 60)
    print("  QuickBooks MCP Server - OAuth Setup")
    print("=" * 60)
    print()

    # Check for required environment variables
    client_id = os.environ.get("QBO_CLIENT_ID", "")
    client_secret = os.environ.get("QBO_CLIENT_SECRET", "")

    if not client_id or not client_secret:
        print("ERROR: Missing required environment variables.")
        print()
        print("Please set the following environment variables:")
        print("  QBO_CLIENT_ID     - Your QuickBooks OAuth2 Client ID")
        print("  QBO_CLIENT_SECRET - Your QuickBooks OAuth2 Client Secret")
        print()
        print("You can get these from https://developer.intuit.com/")
        print("  1. Create or select an app")
        print("  2. Go to 'Keys & OAuth'")
        print("  3. Copy Client ID and Client Secret")
        print()
        print("Set them in your terminal:")
        print("  export QBO_CLIENT_ID='your_client_id'")
        print("  export QBO_CLIENT_SECRET='your_client_secret'")
        print()
        print("Or add to your .env file and source it.")
        sys.exit(1)

    redirect_uri = os.environ.get("QBO_REDIRECT_URI", "http://localhost:8080/callback")

    print("Configuration:")
    print(f"  Client ID:    {client_id[:8]}...{client_id[-4:]}")
    print(f"  Redirect URI: {redirect_uri}")
    print()

    # Import after path setup
    from quickbooks_mcp.auth.oauth import OAuthManager
    from quickbooks_mcp.auth.token_store import TokenStore
    from quickbooks_mcp.config import load_config

    config = load_config()
    token_store = TokenStore(config.token_store_path)
    oauth = OAuthManager(config, token_store)

    # Generate authorization URL
    auth_url, state = oauth.get_authorization_url()

    # Set up callback server
    callback_result: dict[str, str] = {}
    server_ready = asyncio.Event()

    class CallbackHandler(BaseHTTPRequestHandler):
        """HTTP handler for the OAuth callback."""

        def do_GET(self) -> None:
            """Handle the OAuth callback GET request."""
            parsed = urlparse(self.path)

            if parsed.path != "/callback":
                self.send_response(404)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(b"<html><body><h1>Not Found</h1></body></html>")
                return

            params = parse_qs(parsed.query)
            code = params.get("code", [None])[0]
            realm_id = params.get("realmId", [None])[0]
            returned_state = params.get("state", [None])[0]
            error = params.get("error", [None])[0]

            if error:
                callback_result["error"] = error
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(
                    f"<html><body>"
                    f"<h1>Authorization Failed</h1>"
                    f"<p>Error: {error}</p>"
                    f"<p>You can close this window.</p>"
                    f"</body></html>".encode()
                )
                return

            if not code or not realm_id:
                callback_result["error"] = "Missing code or realmId in callback"
                self.send_response(400)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(
                    b"<html><body>"
                    b"<h1>Error</h1>"
                    b"<p>Missing authorization code or realm ID.</p>"
                    b"</body></html>"
                )
                return

            if returned_state != state:
                callback_result["error"] = "State mismatch (possible CSRF attack)"
                self.send_response(400)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(
                    b"<html><body>"
                    b"<h1>Security Error</h1>"
                    b"<p>State parameter mismatch. Please try again.</p>"
                    b"</body></html>"
                )
                return

            callback_result["code"] = code
            callback_result["realm_id"] = realm_id

            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(
                b"<html><body>"
                b"<h1>Authorization Successful!</h1>"
                b"<p>QuickBooks has been connected. You can close this window "
                b"and return to the terminal.</p>"
                b"</body></html>"
            )

        def log_message(self, format: str, *args: Any) -> None:
            """Suppress default HTTP server logging."""
            pass

    # Parse port from redirect URI
    parsed_uri = urlparse(redirect_uri)
    port = parsed_uri.port or 8080

    # Start callback server in background thread
    server = HTTPServer(("localhost", port), CallbackHandler)
    server_thread = Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    print(f"Callback server started on port {port}")
    print()
    print("Opening browser for QuickBooks authorization...")
    print(f"If the browser doesn't open, visit this URL manually:")
    print()
    print(f"  {auth_url}")
    print()

    # Open browser
    webbrowser.open(auth_url)

    print("Waiting for authorization callback...")
    print("(Press Ctrl+C to cancel)")
    print()

    # Wait for callback
    try:
        while "code" not in callback_result and "error" not in callback_result:
            import time
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nSetup cancelled.")
        server.shutdown()
        sys.exit(1)

    server.shutdown()

    if "error" in callback_result:
        print(f"ERROR: {callback_result['error']}")
        sys.exit(1)

    # Exchange code for tokens
    print("Exchanging authorization code for tokens...")
    code = callback_result["code"]
    realm_id = callback_result["realm_id"]

    try:
        tokens = asyncio.run(oauth.exchange_code(code, realm_id))
    except Exception as exc:
        print(f"ERROR: Token exchange failed: {exc}")
        sys.exit(1)

    print()
    print("=" * 60)
    print("  Setup Complete!")
    print("=" * 60)
    print()
    print(f"  Realm ID (Company):  {realm_id}")
    print(f"  Tokens stored at:    {config.token_store_path}")
    print(f"  Token expires in:    ~60 minutes (auto-refreshes)")
    print()
    print("Set the QBO_REALM_ID environment variable:")
    print(f"  export QBO_REALM_ID='{realm_id}'")
    print()
    print("Add to your Claude Desktop config (claude_desktop_config.json):")
    print('  {')
    print('    "mcpServers": {')
    print('      "quickbooks": {')
    print('        "command": "quickbooks-mcp",')
    print('        "env": {')
    print(f'          "QBO_CLIENT_ID": "{client_id}",')
    print(f'          "QBO_CLIENT_SECRET": "YOUR_SECRET_HERE",')
    print(f'          "QBO_REALM_ID": "{realm_id}"')
    print('        }')
    print('      }')
    print('    }')
    print('  }')
    print()
    print("You're all set! The MCP server will auto-refresh tokens as needed.")


if __name__ == "__main__":
    main()
