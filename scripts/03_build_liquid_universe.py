#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd


def symbol_statistics(path: Path, calendar: pd.DatetimeIndex, window: int) -> pd.DataFrame:
    frame = pd.read_csv(path, usecols=["date", "close", "volume"])
    frame["date"] = pd.to_datetime(frame["date"])
    frame = frame.drop_duplicates("date", keep="last").set_index("date").reindex(calendar)
    valid = frame["close"].gt(0) & frame["volume"].ge(0)
    dollar_volume = (frame["close"] * frame["volume"]).where(valid)

    stats = pd.DataFrame(index=calendar)
    stats["price"] = frame["close"]
    stats["median_dollar_volume"] = dollar_volume.rolling(window, min_periods=1).median()
    stats["coverage"] = valid.rolling(window, min_periods=1).sum() / np.minimum(
        np.arange(1, len(calendar) + 1), window
    )
    stats["history"] = valid.cumsum()
    return stats.groupby(stats.index.to_period("M")).tail(1)


def merge_intervals(rows: list[tuple[pd.Timestamp, pd.Timestamp]], calendar: pd.DatetimeIndex):
    if not rows:
        return []
    positions = {date: position for position, date in enumerate(calendar)}
    merged = [list(rows[0])]
    for start, end in rows[1:]:
        previous_end = merged[-1][1]
        if positions[start] == positions[previous_end] + 1:
            merged[-1][1] = end
        else:
            merged.append([start, end])
    return merged


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv-dir", default="data/us_equity_csv")
    parser.add_argument("--qlib-dir", default="~/.qlib/qlib_data/us_liquid_alpaca")
    parser.add_argument("--name", default="us_liquid_1000")
    parser.add_argument("--topk", type=int, default=1000)
    parser.add_argument("--price-floor", type=float, default=3.0)
    parser.add_argument("--min-dollar-volume", type=float, default=2_000_000)
    parser.add_argument("--window", type=int, default=60)
    parser.add_argument("--min-history", type=int, default=120)
    parser.add_argument("--min-coverage", type=float, default=0.90)
    args = parser.parse_args()

    csv_dir = Path(args.csv_dir).expanduser().resolve()
    qlib_dir = Path(args.qlib_dir).expanduser().resolve()
    spy_path = csv_dir / "SPY.csv"
    if not spy_path.exists():
        raise SystemExit(f"Benchmark calendar source not found: {spy_path}")

    calendar = pd.DatetimeIndex(pd.to_datetime(pd.read_csv(spy_path, usecols=["date"])["date"]).unique()).sort_values()
    month_ends = pd.Series(calendar, index=calendar).groupby(calendar.to_period("M")).last()
    effective_periods = []
    for index in range(len(month_ends) - 1):
        selection_date = month_ends.iloc[index]
        next_month_end = month_ends.iloc[index + 1]
        start_position = calendar.get_loc(selection_date) + 1
        if start_position < len(calendar):
            effective_periods.append((selection_date, calendar[start_position], next_month_end))

    snapshots = []
    paths = [path for path in sorted(csv_dir.glob("*.csv")) if path.stem.upper() != "SPY"]
    print(f"Calculating point-in-time liquidity for {len(paths):,} symbols...")
    for path in paths:
        stats = symbol_statistics(path, calendar, args.window)
        stats["symbol"] = path.stem.upper()
        snapshots.append(stats)
    if not snapshots:
        raise SystemExit(f"No stock CSV files found in {csv_dir}")

    panel = pd.concat(snapshots).reset_index(names="selection_date")
    memberships: dict[str, list[tuple[pd.Timestamp, pd.Timestamp]]] = {}
    for selection_date, effective_start, effective_end in effective_periods:
        eligible = panel[
            (panel["selection_date"] == selection_date)
            & (panel["price"] >= args.price_floor)
            & (panel["median_dollar_volume"] >= args.min_dollar_volume)
            & (panel["coverage"] >= args.min_coverage)
            & (panel["history"] >= args.min_history)
        ].nlargest(args.topk, "median_dollar_volume")
        for symbol in eligible["symbol"]:
            memberships.setdefault(symbol, []).append((effective_start, effective_end))

    output_rows = []
    for symbol, intervals in sorted(memberships.items()):
        for start, end in merge_intervals(intervals, calendar):
            output_rows.append((symbol, start.date().isoformat(), end.date().isoformat()))

    instrument_dir = qlib_dir / "instruments"
    instrument_dir.mkdir(parents=True, exist_ok=True)
    output = instrument_dir / f"{args.name}.txt"
    pd.DataFrame(output_rows).to_csv(output, sep="\t", header=False, index=False)
    print(f"Wrote {len(output_rows):,} membership intervals for {len(memberships):,} symbols to {output}")
    print(f"Rules: top {args.topk}, price >= ${args.price_floor:g}, median dollar volume >= ${args.min_dollar_volume:,.0f}")


if __name__ == "__main__":
    main()
