#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import pandas as pd
import requests

PRIMARY_URL = (
    "https://raw.githubusercontent.com/datasets/"
    "s-and-p-500-companies/main/data/constituents.csv"
)
WIKI_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"


def qlib_symbol(symbol: str) -> str:
    # Keep an explicit mapping so broker symbols remain untouched.
    return symbol.strip().upper().replace(".", "_").replace("/", "_").replace("-", "_")


def fetch_primary(timeout: int = 30) -> pd.DataFrame:
    r = requests.get(PRIMARY_URL, timeout=timeout)
    r.raise_for_status()
    from io import StringIO
    return pd.read_csv(StringIO(r.text))


def fetch_wikipedia() -> pd.DataFrame:
    tables = pd.read_html(WIKI_URL)
    df = tables[0].copy()
    return df


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--output", default="data/universe/sp500_current.csv")
    args = p.parse_args()

    try:
        df = fetch_primary()
        source = PRIMARY_URL
    except Exception as exc:
        print(f"Primary constituent source failed: {exc}")
        print("Falling back to Wikipedia.")
        df = fetch_wikipedia()
        source = WIKI_URL

    if "Symbol" not in df.columns:
        raise RuntimeError(f"No Symbol column found. Columns={list(df.columns)}")

    df = df.copy()
    df["alpaca_symbol"] = df["Symbol"].astype(str).str.strip().str.upper()
    df["qlib_symbol"] = df["alpaca_symbol"].map(qlib_symbol)
    df["universe_snapshot_source"] = source

    # Put mapping columns first, preserve useful metadata after them.
    leading = ["alpaca_symbol", "qlib_symbol"]
    rest = [c for c in df.columns if c not in leading]
    df = df[leading + rest].drop_duplicates("alpaca_symbol").sort_values("alpaca_symbol")

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)

    print(f"Wrote {len(df)} current S&P 500 securities to {out}")
    print("NOTE: current membership is survivorship-biased for historical backtests.")
    print(df[["alpaca_symbol", "qlib_symbol"]].head(10).to_string(index=False))


if __name__ == "__main__":
    main()
