# Computational Methodology

The Methodology context translates typed method contracts into validated computational evidence. Maintained contracts
describe parameters, input/output semantics, warm-up behavior, invariants, and fixtures. Generation is quarantined;
produced Python or C++ is not runnable platform code until diagnostics, fixtures, and registration pass.

Signal diagnostics and multiple-testing reports preserve the distinction between implementing a method correctly and
finding a convincing trading result. Optional compiled kernels require parity evidence against the trusted reference.

Knowledge evidence may inform a method contract, but source provenance does not bypass implementation validation.
Likewise, a passed computational contract does not bypass prospective experiment design, robustness, or independent
evaluation.
