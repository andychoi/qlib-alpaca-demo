# Frozen Qlib baseline metrics

Run date: 2026-08-25

Pipeline: Alpaca S&P 500 → Alpha158 → LightGBM → prediction → TopK portfolio → backtest

Universe: `sp500` (503 instrument records)

Strategy: `topk: 50`, `n_drop: 5`

Test/backtest period: 2025-01-02 through 2026-08-21 (410 sessions)

## Signal analysis

| Metric | Value |
|---|---:|
| IC | 0.0038008352 |
| Rank IC | -0.0029116752 |
| ICIR | 0.0351447841 |
| Rank ICIR | -0.0333105626 |

## Portfolio analysis

| Return series | annualized_return | information_ratio | max_drawdown |
|---|---:|---:|---:|
| Benchmark return (SPY) | 0.178252 | 1.094018 | -0.202204 |
| Excess return without cost | 0.111818 | 1.085498 | -0.065950 |
| Excess return with cost | 0.088025 | 0.854431 | -0.070301 |

Primary excess-return figures:

- `excess_return_without_cost`: 0.111818 annualized return
- `excess_return_with_cost`: 0.088025 annualized return

Source log: `reports/qlib_baseline.log`

Frozen config: `reports/baseline_qlib_config.yaml`
