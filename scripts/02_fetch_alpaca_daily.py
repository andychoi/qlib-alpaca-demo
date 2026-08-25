#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from dotenv import load_dotenv
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.data.enums import Adjustment, DataFeed

load_dotenv()


def parse_date(s: str | None, default) -> datetime:
    if s:
        return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)
    return datetime.combine(default, datetime.min.time(), tzinfo=timezone.utc)


def get_feed(name: str) -> DataFeed:
    name = name.strip().lower()
    mapping = {"iex": DataFeed.IEX, "sip": DataFeed.SIP}
    if name not in mapping:
        raise ValueError("ALPACA_DATA_FEED must be iex or sip")
    return mapping[name]


def fetch_bars(
    client: StockHistoricalDataClient,
    symbols: list[str],
    start: datetime,
    end: datetime,
    feed: DataFeed,
    adjustment: Adjustment,
    retries: int = 4,
) -> pd.DataFrame:
    req = StockBarsRequest(
        symbol_or_symbols=symbols,
        timeframe=TimeFrame.Day,
        start=start,
        end=end,
        adjustment=adjustment,
        feed=feed,
        asof=end.date().isoformat(),
    )

    for attempt in range(retries):
        try:
            bars = client.get_stock_bars(req)
            df = bars.df
            if df is None or len(df) == 0:
                return pd.DataFrame()
            return df.reset_index()
        except Exception as exc:
            if attempt == retries - 1:
                raise
            delay = min(2 ** attempt * 3, 30)
            print(f"  request failed ({exc}); retrying in {delay}s")
            time.sleep(delay)
    return pd.DataFrame()


def normalize_timestamp(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    df = df.copy()
    ts = pd.to_datetime(df["timestamp"], utc=True)
    # Alpaca daily bars are keyed to the US trading date.
    df["date"] = ts.dt.tz_convert("America/New_York").dt.date.astype(str)
    return df


def make_qlib_ready(raw: pd.DataFrame, adj: pd.DataFrame) -> dict[str, pd.DataFrame]:
    raw = normalize_timestamp(raw)
    adj = normalize_timestamp(adj)
    if raw.empty or adj.empty:
        return {}

    keep = [
        "symbol", "date", "open", "high", "low", "close",
        "volume", "trade_count", "vwap"
    ]
    raw = raw[[c for c in keep if c in raw.columns]].copy()
    adj = adj[[c for c in keep if c in adj.columns]].copy()

    merged = raw.merge(
        adj,
        on=["symbol", "date"],
        how="inner",
        suffixes=("_raw", "_adj"),
        validate="one_to_one",
    )

    merged["factor"] = merged["close_adj"] / merged["close_raw"]
    bad = ~np.isfinite(merged["factor"]) | (merged["factor"] <= 0)
    merged.loc[bad, "factor"] = 1.0

    out = {}
    for symbol, g in merged.groupby("symbol", sort=True):
        q = pd.DataFrame(
            {
                "symbol": symbol,
                "date": g["date"],
                "open": g["open_raw"] * g["factor"],
                "high": g["high_raw"] * g["factor"],
                "low": g["low_raw"] * g["factor"],
                "close": g["close_raw"] * g["factor"],
                "volume": g["volume_raw"] / g["factor"],
                "factor": g["factor"],
            }
        )
        if "vwap_raw" in g:
            q["vwap"] = g["vwap_raw"] * g["factor"]
        if "trade_count_raw" in g:
            q["trade_count"] = g["trade_count_raw"]

        q = q.sort_values("date").drop_duplicates("date")
        q = q.replace([np.inf, -np.inf], np.nan)
        out[symbol] = q
    return out


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--universe", default="data/universe/sp500_current.csv")
    p.add_argument("--output-dir", default="data/qlib_csv")
    p.add_argument("--start", default=os.getenv("START_DATE", "2020-01-01"))
    p.add_argument("--end", default=os.getenv("END_DATE") or None)
    p.add_argument("--batch-size", type=int, default=int(os.getenv("ALPACA_BATCH_SIZE", "25")))
    p.add_argument("--limit-symbols", type=int, default=None)
    args = p.parse_args()

    key = os.getenv("APCA_API_KEY_ID")
    secret = os.getenv("APCA_API_SECRET_KEY")
    if not key or not secret:
        raise SystemExit(
            "Set APCA_API_KEY_ID and APCA_API_SECRET_KEY in .env or environment."
        )

    universe = pd.read_csv(args.universe)
    required = {"alpaca_symbol", "qlib_symbol"}
    if not required.issubset(universe.columns):
        raise RuntimeError(f"Universe must contain {required}")

    if args.limit_symbols:
        universe = universe.head(args.limit_symbols).copy()

    # SPY is not part of the research universe but is needed by the workflow benchmark.
    mapping = dict(zip(universe["alpaca_symbol"], universe["qlib_symbol"]))
    mapping["SPY"] = "SPY"
    symbols = list(mapping)

    start = parse_date(args.start, datetime(2020, 1, 1).date())
    default_end = datetime.now(timezone.utc).date() - timedelta(days=1)
    # Add one day because date endpoints and midnight boundaries can otherwise omit the last bar.
    end_inclusive = parse_date(args.end, default_end)
    request_end = end_inclusive + timedelta(days=1)

    feed = get_feed(os.getenv("ALPACA_DATA_FEED", "iex"))
    client = StockHistoricalDataClient(key, secret)

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    status_rows = []
    print(
        f"Downloading {len(symbols)} symbols, {start.date()}..{end_inclusive.date()}, "
        f"feed={feed.value}, batch={args.batch_size}"
    )

    for i in range(0, len(symbols), args.batch_size):
        batch = symbols[i : i + args.batch_size]
        print(f"[{i+1:>3}-{i+len(batch):>3}/{len(symbols)}] {batch[0]} ... {batch[-1]}")

        raw = fetch_bars(
            client, batch, start, request_end, feed, Adjustment.RAW
        )
        adj = fetch_bars(
            client, batch, start, request_end, feed, Adjustment.ALL
        )
        prepared = make_qlib_ready(raw, adj)

        for alpaca_symbol in batch:
            qlib_sym = mapping[alpaca_symbol]
            q = prepared.get(alpaca_symbol)
            if q is None or q.empty:
                print(f"  WARNING no usable bars: {alpaca_symbol}")
                status_rows.append(
                    {"alpaca_symbol": alpaca_symbol, "qlib_symbol": qlib_sym, "rows": 0}
                )
                continue

            q = q.copy()
            q["symbol"] = qlib_sym
            out_file = out_dir / f"{qlib_sym}.csv"

            # Incremental/backfill downloads should preserve rows already on
            # disk. Newly fetched rows win if the requested range overlaps.
            if out_file.exists():
                existing = pd.read_csv(out_file)
                q = pd.concat([existing, q], ignore_index=True)
                q = q.sort_values("date").drop_duplicates("date", keep="last")

            q.to_csv(out_file, index=False)

            status_rows.append(
                {
                    "alpaca_symbol": alpaca_symbol,
                    "qlib_symbol": qlib_sym,
                    "rows": len(q),
                    "first_date": q["date"].min(),
                    "last_date": q["date"].max(),
                }
            )

        # Gentle pacing. Batching keeps this far below normal API request limits.
        time.sleep(0.25)

    status = pd.DataFrame(status_rows)
    status.to_csv("reports/alpaca_download_status.csv", index=False)

    ok = status[status["rows"] > 0]
    print()
    print(f"Downloaded: {len(ok)}/{len(status)} symbols")
    if len(ok):
        print(f"Date coverage: {ok['first_date'].min()} .. {ok['last_date'].max()}")
        print(f"Rows: {int(ok['rows'].sum()):,}")
    print("Status: reports/alpaca_download_status.csv")


if __name__ == "__main__":
    main()
