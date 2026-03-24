"""Entry point for the QuickBooks MCP server."""

import asyncio
import sys

from quickbooks_mcp.server import create_server


def main() -> None:
    """Run the QuickBooks MCP server."""
    server = create_server()
    try:
        asyncio.run(server.run_stdio())
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        print(f"QuickBooks MCP server error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
