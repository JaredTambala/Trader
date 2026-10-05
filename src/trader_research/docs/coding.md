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

The human Console receives only the resulting typed admission projection. Its authoring request includes the exact
implementation/version, source digest, validation report, specification identity, and reuse/adaptation/authorship
decision; it never accepts a module import path or opaque callable. The Console may use an application-composed
resolver to revalidate that the research-owned report and source digest are still current before persisting a
definition, while research remains the authority for registration and admission.

## Verification ownership

The package-owned contract at
`tests/trader_research/coding/test_workspace_lifecycle_and_isolation.py` follows the complete workspace lifecycle:
idempotent creation and writes, bounded read-only repository access, dependency policy, runner availability, digest
pinning, container-command isolation controls, output and deadline termination, inert packaging, and exact cleanup.
It uses temporary directories, an injected runner, and a fake Docker-compatible executable; it does not require or
claim real container-runtime qualification. Catalogue search, comparison, maintained templates, and admission are
verified under `tests/trader_research/experiments/`.
