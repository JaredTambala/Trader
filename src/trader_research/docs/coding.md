# Isolated Coding Workspaces

The Coding context provides an ephemeral, policy-bounded workspace for comparing, adapting, or authoring strategy
candidates. It exposes a pinned repository read-only and a separate candidate write area. Search, reads, writes,
dependency resolution, allowed checks, packaging, and destruction are explicit operations.

Checks execute in a digest-pinned container with network, privilege, filesystem, process, memory, CPU, deadline,
output, and cleanup limits. There is no host-execution fallback. The workspace receives no broker, Postgres, provider,
or model-service credentials.

Packaging creates source evidence; it does not admit the implementation. Strategy/risk validation and immutable
registration belong to the Experiments context. A failed admission may be repaired within an allowed revision budget,
but changing the research semantics requires a new brief or coordinator decision rather than a hidden patch.
