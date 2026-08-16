"""Constructs the FastMCP instance. Deliberately trivial -- this server exists
only to prove an MCP platform's Basic Auth flow works end to end, not to do
anything useful once connected.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings


def build_mcp() -> FastMCP:
    mcp = FastMCP(
        "mcp-test-basic-auth",
        instructions="A minimal test server for verifying HTTP Basic Auth against an MCP client.",
        # Default DNS-rebinding protection only allows Host headers matching
        # 127.0.0.1/localhost/[::1] -- rejects every real request to a
        # deployed service with a 421 unless the deployed hostname is
        # explicitly allow-listed. See mcp-fileserver/server.py for the same
        # gotcha, found the hard way there.
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )

    @mcp.tool()
    def ping() -> str:
        """Returns "pong" -- call this to confirm the connection and auth are working."""
        return "pong"

    return mcp
