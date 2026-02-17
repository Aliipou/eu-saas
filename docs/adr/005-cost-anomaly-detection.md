# ADR-005: Z-Score Based Cost Anomaly Detection

## Status

Accepted

## Context

Tenants need alerts when their cloud costs deviate unexpectedly. The detection method must be:
- Simple to implement and explain
- Effective with limited historical data (7-day window)
- Low false-positive rate

## Decision

Use **z-score analysis** with:
- **Threshold**: 2.5 standard deviations from the rolling mean
- **Window**: 7-day rolling window
- **Minimum data**: 3 data points required for meaningful analysis

Formula: `z = (current - mean) / std_dev`. Anomaly if `|z| > 2.5`.

## Consequences

### Positive
- Simple, well-understood statistical method
- Low computational cost (no ML infrastructure needed)
- Configurable threshold per deployment
- 2.5 sigma captures ~98.8% of normal variation

### Negative
- Assumes roughly normal distribution of daily costs
- May not detect slow, gradual increases (boiling frog)
- Weekday/weekend patterns not accounted for

### Future Improvements
- Seasonal decomposition for weekly patterns
- Exponential smoothing for trend detection
- Per-resource-type thresholds
