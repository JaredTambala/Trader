"""MCP transport and policy adapters over deterministic research services.

The package owns the stdio FastMCP server, public tool envelopes, capability
registration gates, and provider composition. Research behavior remains in
``trader_research`` and model-backed control remains in ``trader_agents``.
"""

from .protocol.adapters import mcp_result_json, result_to_mcp_result

__all__ = ["result_to_mcp_result", "mcp_result_json"]
