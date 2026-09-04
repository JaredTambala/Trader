# Computational Methodology

The Methodology context translates typed method contracts into validated computational evidence. Maintained contracts
describe parameters, input/output semantics, warm-up behavior, invariants, and fixtures. Callers may submit maintained
or externally authored Python implementations for static safety, provenance, registration, and deterministic fixture
validation. The context does not call an LLM or author Python. Template-restricted C++ kernel generation remains a
deterministic optimization operation over an already validated Python reference.

Research-backed authoring crosses two explicit handoffs: Quantitative Methods produces a source-backed implementation
brief, then Strategy Engineering uses the isolated Coding Workspace tools to author and check a candidate. Packaging
does not admit code; the Experiments context independently registers and validates strategy or risk implementations.

Signal diagnostics and multiple-testing reports preserve the distinction between implementing a method correctly and
finding a convincing trading result. Optional compiled kernels require parity evidence against the trusted reference.

Knowledge evidence may inform a method contract, but source provenance does not bypass implementation validation.
Likewise, a passed computational contract does not bypass independent strategy admission, prospective experiment
design, robustness, or evaluation.

## Verification ownership

Package-owned contracts live under `tests/trader_research/methodology/` and follow the computational pipeline rather
than execution environment. The method catalogue and validation suite protects typed contracts; implementation tests
protect registration, runtime conformance, and deterministic fixtures; package tests protect immutable validated
artifacts; signal diagnostics and multiple-testing suites protect statistical reports. The C++ kernel suite is the
only compiler-backed module and runs real local generation, successful compilation, missing-compiler, tamper, and
compiler-error cases. Knowledge candidate interpretation and method-card lifecycle remain under
`tests/trader_research/knowledge/`.
