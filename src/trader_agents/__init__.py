"""LangGraph agent identity metadata.

Graph implementations are introduced after the MCP tool surface exists. This
package currently exposes only dependency-free identity metadata.
"""

from .identities import AgentIdentity, build_agent_identity

__all__ = ["AgentIdentity", "build_agent_identity"]
