# Maintained Implementation Architecture

`trader_standard` is a leaf implementation package over `trader`. Its dependency direction is deliberate:

```text
trader contracts <- trader_standard implementations
```

Core never imports this package. User wrappers, examples, and higher-level research services decide whether to compose
these implementations.

## Layers

- Indicators transform ordered `Bar` windows into scalar or structured observations.
- Signals interpret bars and indicators as normalized decision values; they do not submit orders.
- Signal generators obtain bounded bar windows and evaluate signals for configured symbols.
- Strategies combine signal state with portfolio state and emit candidate order mappings.
- Risk managers accept or reject candidate orders using an explicit `RiskContext`.
- Prediction helpers build point-in-time features and map typed predictions into strategy-specific decisions.

The policy-driven strategy separates three decisions: entry when flat, ordinary exit when long, and protective exit.
`StrategySnapshot` is the immutable handoff to these policies. Stateful trailing stops own only their per-symbol
high-water marks and reset when the position is flat.

## Effects and state

Most indicator, signal, and policy calculations are deterministic. Bar fetching and signal-event recording cross the
event-store boundary inside signal generators or strategies because those operations need timestamp and audit context.
The caller owns long-lived strategy instances; stateful policies therefore survive between cycles within the same run.

## Extension boundary

Add a maintained implementation here when it is generally useful, has stable semantics, and can be supported by the
project. Bespoke research code belongs in an explicit candidate/workspace flow and must be admitted before execution.
New implementations must declare metadata and parameters, test mathematical behavior, test runtime composition, and
update the [catalogue](catalogue.md) plus [tutorial](tutorial.md) when they affect the normal learning path.

## Verification ownership

Package tests live under `tests/trader_standard/` by extension family: prediction mappers, risk managers, and
strategies. A test remains owned here when core contracts are used to prove the behavior or composability of a
maintained implementation. Tests whose subject is the core runtime, prediction protocol, or portfolio behavior live
under `tests/trader/` even when a standard implementation is a convenient collaborator.
