# Simple Moving Average

The simple moving average computes the arithmetic mean of the most recent fixed
window of ordered observations. The period is declared before evaluation, and
the output is not available until enough warmup observations exist.

## Failure Modes

The method is blocked when there are too few observations, when the period is
outside approved bounds, or when the input sequence contains unresolved
non-finite values.
