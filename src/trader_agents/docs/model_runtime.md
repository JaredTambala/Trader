# Model Runtime

## Profiles and programs

The canonical implementation is under `trader_agents.model_runtime`: `client.py` defines provider-neutral clients,
`profiles.py` defines admitted model/program registries, `programs.py` supplies the current programs, and
`structured.py` owns schema-bound invocation.

`ModelProfile` fixes provider, model name, immutable revision, endpoint, temperature, context/output limits, timeout,
and thinking mode. `AgentProgram` fixes role, version, system instruction, output contracts, tool-policy version, and
schema-repair limit. Registries reject duplicate roles/identities and publish content-derived manifests.

The active development profile uses local Ollama `lfm2.5:8b` with an exact content digest, an 8,192-token context, a
2,048-token output ceiling, zero temperature, and provider thinking disabled. This is a selected evaluation identity,
not a claim that every model with the same display name behaves equivalently.

## Structured invocation

`StructuredModelRunner` serializes only bounded public context and the requested Pydantic JSON schema. It accounts for
every physical provider call, including errors and invalid outputs. It permits at most one structural repair carrying
bounded validation messages. It does not repair semantic decisions, strip permissive fenced JSON, rewrite agendas, or
substitute a canned answer.

## Reasoning ownership

Models decide interpretations and next actions inside their role. Code decides whether those outputs are safe and
contract-valid. Deterministic policy does not prescribe which specialist must be selected for every phrase; equally,
model reasoning cannot override authority, evidence, scheduling, or budget invariants.
