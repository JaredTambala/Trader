"""MCP transport and policy adapters over deterministic research services.

The package owns the stdio FastMCP server, public tool envelopes, capability
registration gates, and provider composition. Research behavior remains in
``trader_research`` and model-backed control remains in ``trader_agents``.
"""

from .adapters import result_to_mcp_result, mcp_result_json

__all__ = ["result_to_mcp_result", "mcp_result_json"]
