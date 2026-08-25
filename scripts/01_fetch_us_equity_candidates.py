#!/usr/bin/env python3
from __future__ import annotations

import argparse
from io import StringIO
from pathlib import Path

import pandas as pd
import requests

NASDAQ_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
OTHER_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"


def read_symbol_directory(url: str) -> pd.DataFrame:
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    frame = pd.read_csv(StringIO(response.text), sep="|")
    return frame[~frame.iloc[:, 0].astype(str).str.startswith("File Creation Time")].copy()


def qlib_symbol(symbol: str) -> str:
    return symbol.strip().upper().replace(".", "_").replace("/", "_").replace("-", "_")


def common_stock_candidates() -> pd.DataFrame:
    nasdaq = read_symbol_directory(NASDAQ_LISTED_URL)
    nasdaq = nasdaq.rename(columns={"Symbol": "alpaca_symbol", "Security Name": "security_name"})
    nasdaq["exchange"] = "NASDAQ"

    other = read_symbol_directory(OTHER_LISTED_URL)
    other = other.rename(columns={"ACT Symbol": "alpaca_symbol", "Security Name": "security_name"})
    exchange_names = {"A": "NYSE American", "N": "NYSE", "P": "NYSE Arca", "Z": "Cboe"}
    other["exchange"] = other["Exchange"].map(exchange_names).fillna(other["Exchange"])

    keep_columns = ["alpaca_symbol", "security_name", "exchange", "ETF", "Test Issue"]
    frame = pd.concat([nasdaq[keep_columns], other[keep_columns]], ignore_index=True)
    frame = frame[(frame["ETF"] == "N") & (frame["Test Issue"] == "N")].copy()

    # The exchange directories identify ETFs explicitly. These name filters
    # remove other non-common-share structures that should not enter a stock
    # cross-section. ADRs are deliberately excluded from the initial universe.
    excluded = r"(?i:depositary|\bADR\b|preferred|preference|warrant|\brights?\b|\bunits?\b|acquisition corp|blank check)"
    frame = frame[~frame["security_name"].fillna("").str.contains(excluded, regex=True)]
    frame = frame.dropna(subset=["alpaca_symbol"])
    frame["alpaca_symbol"] = frame["alpaca_symbol"].astype(str).str.strip().str.upper()
    frame = frame[frame["alpaca_symbol"].ne("")]
    frame = frame[~frame["alpaca_symbol"].str.contains(r"[$^/]", regex=True)]
    frame["qlib_symbol"] = frame["alpaca_symbol"].map(qlib_symbol)
    collisions = frame[frame.duplicated("qlib_symbol", keep=False)]
    if not collisions.empty:
        raise RuntimeError(f"Qlib symbol collision:\n{collisions[['alpaca_symbol', 'qlib_symbol']]}")
    frame["universe_snapshot_source"] = "Nasdaq Trader Symbol Directory"
    return frame.drop_duplicates("alpaca_symbol").sort_values("alpaca_symbol")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="data/universe/us_equity_candidates.csv")
    args = parser.parse_args()

    frame = common_stock_candidates()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output, index=False)
    print(f"Wrote {len(frame):,} US common-stock candidates to {output}")
    print("ETFs, test issues, ADRs, preferred shares, warrants, rights, and units were excluded.")


if __name__ == "__main__":
    main()
