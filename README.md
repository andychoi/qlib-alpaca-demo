# Qlib + Alpaca S&P 500 Function-Test Dataset

This project builds a **current S&P 500** daily dataset from Alpaca historical stock bars and converts it to Microsoft Qlib's binary format.

The first goal is functional verification:

`S&P 500 universe -> Alpaca daily bars -> Qlib CSV -> Qlib .bin -> Alpha158 -> LightGBM -> SPY benchmark`

## Important research caveat

The default universe is the **current S&P 500 membership**, so a long historical backtest has **survivorship bias**. That is acceptable for a Qlib function test, but it is not suitable evidence of trading alpha.

Before using this with RD-Agent for serious research, replace the current-membership universe with point-in-time S&P 500 membership and use strict train/validation/holdout periods.

## What is included

- `scripts/01_fetch_constituents.py`
  - downloads a current S&P 500 constituent snapshot
  - preserves the Alpaca ticker and creates a Qlib-safe ticker
- `scripts/02_fetch_alpaca_daily.py`
  - downloads daily OHLCV + VWAP from Alpaca
  - also downloads `SPY` for the benchmark
  - requests both RAW and ALL-adjusted bars and calculates a Qlib-style adjustment factor
  - produces one Qlib-ready CSV per symbol
- `scripts/03_build_qlib.py`
  - clones Qlib if needed
  - invokes Qlib's official `scripts/dump_bin.py`
  - creates `instruments/sp500.txt`
- `scripts/04_verify_qlib.py`
  - verifies calendar/instruments/features
  - optionally instantiates Alpha158
- `configs/workflow_sp500_lightgbm_alpha158.yaml`
  - US-region Qlib / Alpha158 / LightGBM function-test workflow
  - benchmark: SPY
  - train: 2020-07-27 through 2022 (the earliest date returned by Alpaca IEX)
  - validation: 2023-2024
  - test/backtest: 2025-2026-08-21 (data handler through 2026-08-24)
  - stores MLflow experiment metadata in local SQLite (`mlflow.db`)

## 1. Create environment

Recommended: Python 3.11.

macOS Apple Silicon users may need:

```bash
brew install libomp
```

Then:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
```

Enter your Alpaca data API key and secret in `.env`.

## 2. Fetch current S&P 500 constituents

```bash
python scripts/01_fetch_constituents.py
```

Outputs:

```text
data/universe/sp500_current.csv
```

The script uses the public `datasets/s-and-p-500-companies` snapshot first and falls back to the Wikipedia S&P 500 table.

Special share-class tickers are mapped for Qlib file safety, for example:

```text
BRK.B -> BRK_B
BF.B  -> BF_B
```

The original Alpaca symbol remains in the mapping file.

## 3. Download Alpaca daily history

Basic/free Alpaca accounts can normally use the IEX feed:

```bash
python scripts/02_fetch_alpaca_daily.py --start 2020-01-01
```

If your account has SIP entitlement:

```bash
ALPACA_DATA_FEED=sip python scripts/02_fetch_alpaca_daily.py
```

For a faster smoke test first:

```bash
python scripts/02_fetch_alpaca_daily.py --limit-symbols 30 --start 2020-01-01
```

The full S&P 500 run is deliberately batched.

Existing symbol CSVs are merged by date, so bounded downloads can backfill or
update the dataset without discarding previously fetched rows. For example:

```bash
python scripts/02_fetch_alpaca_daily.py --start 2020-01-01 --end 2020-12-31
```

### Corporate-action normalization

The downloader requests both:

- `adjustment=raw`
- `adjustment=all`

For each date it computes:

```text
factor = adjusted_close / raw_close
qlib_open   = raw_open  * factor
qlib_high   = raw_high  * factor
qlib_low    = raw_low   * factor
qlib_close  = raw_close * factor
qlib_vwap   = raw_vwap  * factor
qlib_volume = raw_volume / factor
```

This follows Qlib's daily normalization convention more closely than simply setting `factor=1`.

## 4. Convert CSV to Qlib binary format

```bash
python scripts/03_build_qlib.py
```

Default output:

```text
~/.qlib/qlib_data/us_sp500_alpaca/
  calendars/day.txt
  features/...
  instruments/all.txt
  instruments/sp500.txt
```

`SPY` is in `all.txt` for benchmark retrieval, while `sp500.txt` contains the equity research universe.

## 5. Verify Qlib retrieval

```bash
python scripts/04_verify_qlib.py
```

For a heavier Alpha158 construction test:

```bash
python scripts/04_verify_qlib.py --alpha158
```

## 6. Run LightGBM + Alpha158 function test

From this project directory:

```bash
qrun configs/workflow_sp500_lightgbm_alpha158.yaml
```

This config is intentionally a **function-test baseline**, not an optimized investment strategy.

## Recommended test sequence

Start small:

```bash
python scripts/01_fetch_constituents.py
python scripts/02_fetch_alpaca_daily.py --limit-symbols 30 --start 2020-01-01
python scripts/03_build_qlib.py
python scripts/04_verify_qlib.py --alpha158
```

Then run the full current S&P 500 universe:

```bash
rm -rf data/qlib_csv
mkdir -p data/qlib_csv
python scripts/02_fetch_alpaca_daily.py --start 2020-01-01
python scripts/03_build_qlib.py --rebuild
python scripts/04_verify_qlib.py --alpha158
qrun configs/workflow_sp500_lightgbm_alpha158.yaml
```

## Alpaca IEX vs SIP

IEX is sufficient to prove that Qlib works end to end. It is **not ideal for final research** because its volume/VWAP reflects a narrower feed than consolidated SIP data.

For RD-Agent research, prefer SIP or another institutional-quality point-in-time data source if available.

## Data sources / documentation

- Alpaca historical bars API: https://docs.alpaca.markets/reference/stockbars
- Alpaca Python SDK: https://alpaca.markets/sdks/python/
- Qlib custom-data format: https://github.com/microsoft/qlib/blob/main/docs/component/data.rst
- Qlib dump utility: https://github.com/microsoft/qlib/blob/main/scripts/dump_bin.py
- S&P 500 constituent snapshot: https://github.com/datasets/s-and-p-500-companies

## Next step after this passes

Do **not** connect RD-Agent immediately.

First save the Qlib baseline metrics:

- IC
- Rank IC
- ICIR / Rank ICIR
- annualized excess return
- information ratio
- max drawdown
- turnover and costs

Then use exactly the same data splits when testing RD-Agent-generated factors.
