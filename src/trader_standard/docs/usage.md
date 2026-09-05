# Maintained Implementation Usage Reference

Import commonly composed implementations from `trader_standard`. Import narrower prediction components from their
subpackage when needed.

<!-- verified: doctest -->
```pycon
>>> from trader_standard import SmaIndicator, SmaCrossoverSignal, NoOpRiskManager
>>> indicator = SmaIndicator(period=5)
>>> indicator.window
5
>>> NoOpRiskManager().__class__.__name__
'NoOpRiskManager'
```

## Selection guidance

| Need | Start with |
| --- | --- |
| Infrastructure or dry-run behavior | `NoOpStrategy`, `NoOpRiskManager` |
| Deterministic smoke-test orders | `ToggleUnitStrategy` |
| Simple scalar signal-to-order mapping | `SimpleStrategy` |
| Long/flat technical strategy | a `build_*_strategy` helper or `LongFlatSignalStrategy` |
| Layered runtime risk | `RiskPipeline` from core with standard risk managers |
| Model-backed decisions | prediction helpers plus `PredictionDrivenStrategy`; loading remains in `trader_mlflow` |

## Runtime expectations

Bar-backed maintained strategies expect the event store to contain normalized bars for their asset class, symbols,
timeframe, and decision window. They emit plain candidate-order mappings and may record signal evidence. The core
runtime owns risk evaluation, submission/simulation, portfolio accounting, and lifecycle evidence.

## Metadata and reproducibility

Use `strategy_info` to inspect the stable identity, source, and parameters recorded with runs. Changing behaviorally
material defaults or parameter interpretation is a versioned strategy change; do not silently reuse an identity.

## Custom work

Application-owned custom implementations may depend on `trader` interfaces directly. Agent-authored candidates use the
isolated coding and admission boundary documented by `trader_research` and exposed by `trader_mcp`. Code retrieved from
the implementation catalogue remains untrusted until its exact version is admitted.
