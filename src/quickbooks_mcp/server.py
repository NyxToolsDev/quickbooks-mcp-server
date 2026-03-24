"""Main MCP server for QuickBooks Online integration.

Registers all tools with JSON Schema input definitions and manages
server lifecycle including authentication and license validation.
"""

from __future__ import annotations

import asyncio
import logging

from mcp.server import Server

from quickbooks_mcp.auth.oauth import OAuthManager
from quickbooks_mcp.auth.token_store import TokenStore
from quickbooks_mcp.client.qbo_client import QBOClient
from quickbooks_mcp.config import load_config
from quickbooks_mcp.tools import (
    register_account_tools,
    register_analytics_tools,
    register_customer_tools,
    register_expense_tools,
    register_invoice_tools,
    register_report_tools,
    register_write_tools,
)
from quickbooks_mcp.utils.license import validate_license

logger = logging.getLogger(__name__)

# Track whether the license has been pre-validated
_license_prevalidated = False


async def _prevalidate_license(license_key: str) -> None:
    """Pre-validate the license key so the result is cached for tool calls.

    This is called lazily on the first premium tool invocation or can be
    triggered early. The result is cached in the license module.

    Args:
        license_key: The Lemon Squeezy license key.
    """
    global _license_prevalidated  # noqa: PLW0603
    if _license_prevalidated or not license_key:
        return
    _license_prevalidated = True

    status = await validate_license(license_key)
    if status.is_premium:
        logger.info("Premium license active for %s", status.customer_name or "user")
    else:
        logger.info("License validation: %s", status.error)


def create_server() -> Server:
    """Create and configure the QuickBooks MCP server.

    Initializes authentication, API client, and registers all 19 tools
    organized by tier (free/premium) and category.

    Returns:
        A fully configured MCP Server instance ready for stdio transport.
    """
    config = load_config()

    # Configure logging
    logging.basicConfig(
        level=getattr(logging, config.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    # Validate configuration
    if not config.is_configured:
        logger.warning(
            "QuickBooks credentials not fully configured. "
            "Set QBO_CLIENT_ID, QBO_CLIENT_SECRET, and QBO_REALM_ID environment variables. "
            "Run 'python -m quickbooks_mcp.scripts.setup_oauth' to complete setup."
        )

    # Initialize auth and API client
    token_store = TokenStore(config.token_store_path)
    oauth = OAuthManager(config, token_store)
    qbo = QBOClient(config, oauth)

    # Create MCP server
    server = Server("quickbooks-mcp")

    # Register all tool groups
    # Free tier tools (9 tools)
    register_invoice_tools(server, qbo)       # list_invoices, get_invoice_details, get_overdue_invoices
    register_expense_tools(server, qbo)       # list_expenses, get_top_expenses
    register_account_tools(server, qbo)       # get_account_balances, get_account_transactions
    register_customer_tools(server, qbo)      # search_customers, get_customer_summary

    # Premium tier tools (10 tools) - license checked at execution time
    register_report_tools(server, qbo, config.license_key)    # 5 report tools
    register_write_tools(server, qbo, config.license_key)     # 3 write operation tools
    register_analytics_tools(server, qbo, config.license_key) # 2 analytics tools

    # Pre-validate license in the background (non-blocking)
    if config.license_key:
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(_prevalidate_license(config.license_key))
        except RuntimeError:
            # No event loop yet; validation will happen on first premium tool call
            pass

    logger.info(
        "QuickBooks MCP server initialized with 19 tools "
        "(9 free, 10 premium). Sandbox=%s",
        config.sandbox,
    )

    return server
