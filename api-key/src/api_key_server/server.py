"""Constructs the FastMCP instance. Deliberately trivial -- this server exists
only to prove an MCP platform's API Key flow works end to end.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings


def build_mcp() -> FastMCP:
    mcp = FastMCP(
        "mcp-test-api-key",
        instructions="A minimal test server for verifying API Key auth against an MCP client.",
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )

    @mcp.tool()
    def ping() -> str:
        """Returns "pong" -- call this to confirm the connection and auth are working."""
        return "pong"

    return mcp
