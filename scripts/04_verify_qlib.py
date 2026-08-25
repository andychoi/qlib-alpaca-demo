#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
from pathlib import Path

import pandas as pd
import qlib
from qlib.config import REG_US
from qlib.data import D
from dotenv import load_dotenv

load_dotenv()


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--qlib-dir",
        default=os.getenv("QLIB_DATA_DIR", "~/.qlib/qlib_data/us_sp500_alpaca"),
    )
    p.add_argument("--start", default="2024-01-01")
    p.add_argument("--end", default="2026-08-24")
    p.add_argument("--alpha158", action="store_true")
    p.add_argument("--instrument", default="sp500")
    args = p.parse_args()

    provider = str(Path(args.qlib_dir).expanduser().resolve())
    qlib.init(provider_uri=provider, region=REG_US)

    calendar = D.calendar(start_time=args.start, end_time=args.end, freq="day")
    print(f"Calendar rows: {len(calendar)}")
    if len(calendar):
        print(f"Calendar: {calendar[0]} .. {calendar[-1]}")

    features = D.features(
        D.instruments(args.instrument),
        ["$open", "$high", "$low", "$close", "$volume", "$vwap", "$factor"],
        start_time=args.start,
        end_time=args.end,
        freq="day",
    )
    print(f"Feature rows: {len(features):,}")
    if len(features):
        n_inst = features.index.get_level_values("instrument").nunique()
        print(f"Instruments returned: {n_inst}")
        print(features.head())

    spy = D.features(
        ["SPY"],
        ["$close", "$volume"],
        start_time=args.start,
        end_time=args.end,
        freq="day",
    )
    print(f"SPY rows: {len(spy)}")

    if args.alpha158:
        print("\nInstantiating Alpha158 (this is intentionally heavier)...")
        from qlib.contrib.data.handler import Alpha158

        # Small interval for construction/function verification.
        h = Alpha158(
            instruments=args.instrument,
            start_time="2022-01-01",
            end_time=args.end,
            fit_start_time="2022-01-01",
            fit_end_time="2023-12-31",
        )
        sample = h.fetch(
            slice("2024-01-01", "2024-03-31"),
            col_set=["feature", "label"],
        )
        print(f"Alpha158 sample shape: {sample.shape}")
        print(sample.head())

    print("\nPASS: Qlib can read the Alpaca-built US dataset.")


if __name__ == "__main__":
    main()
