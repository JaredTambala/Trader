"""MCP adapter package for research tools.

The MCP server is introduced in later chunks. This package is intentionally
importable without MCP SDK dependencies for now.
"""

from .adapters import envelope_to_mcp_result, mcp_result_json

__all__ = ["envelope_to_mcp_result", "mcp_result_json"]
