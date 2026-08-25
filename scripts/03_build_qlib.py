#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

load_dotenv()


def ensure_qlib_repo(path: Path) -> None:
    if (path / "scripts" / "dump_bin.py").exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    print(f"Cloning Microsoft Qlib into {path}")
    subprocess.run(
        ["git", "clone", "--depth", "1", "https://github.com/microsoft/qlib.git", str(path)],
        check=True,
    )


def make_instrument_file(csv_dir: Path, qlib_dir: Path, instrument_name: str) -> None:
    rows = []
    for path in sorted(csv_dir.glob("*.csv")):
        if path.stem.upper() == "SPY":
            continue
        df = pd.read_csv(path, usecols=["date"])
        if df.empty:
            continue
        rows.append((path.stem.upper(), df["date"].min(), df["date"].max()))

    inst_dir = qlib_dir / "instruments"
    inst_dir.mkdir(parents=True, exist_ok=True)
    out = inst_dir / f"{instrument_name}.txt"
    pd.DataFrame(rows).to_csv(out, sep="\t", header=False, index=False)
    print(f"Wrote {len(rows)} instruments to {out}")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--csv-dir", default="data/qlib_csv")
    p.add_argument(
        "--qlib-dir",
        default=os.getenv("QLIB_DATA_DIR", "~/.qlib/qlib_data/us_sp500_alpaca"),
    )
    p.add_argument(
        "--qlib-repo", default=os.getenv("QLIB_REPO", ".cache/qlib")
    )
    p.add_argument("--rebuild", action="store_true")
    p.add_argument("--instrument-name", default="sp500")
    args = p.parse_args()

    csv_dir = Path(args.csv_dir).expanduser().resolve()
    qlib_dir = Path(args.qlib_dir).expanduser().resolve()
    qlib_repo = Path(args.qlib_repo).expanduser().resolve()

    if not csv_dir.exists() or not list(csv_dir.glob("*.csv")):
        raise SystemExit(f"No CSV files found in {csv_dir}")

    ensure_qlib_repo(qlib_repo)

    if args.rebuild and qlib_dir.exists():
        print(f"Removing existing Qlib dataset {qlib_dir}")
        shutil.rmtree(qlib_dir)

    qlib_dir.mkdir(parents=True, exist_ok=True)
    dump_bin = qlib_repo / "scripts" / "dump_bin.py"

    cmd = [
        sys.executable,
        str(dump_bin),
        "dump_all",
        "--data_path",
        str(csv_dir),
        "--qlib_dir",
        str(qlib_dir),
        "--freq",
        "day",
        "--date_field_name",
        "date",
        "--symbol_field_name",
        "symbol",
        "--include_fields",
        "open,close,high,low,volume,factor,vwap,trade_count",
        "--file_suffix",
        ".csv",
    ]
    print("Running Qlib dump_bin.py ...")
    subprocess.run(cmd, check=True)

    make_instrument_file(csv_dir, qlib_dir, args.instrument_name)

    print()
    print("Qlib dataset ready:")
    print(qlib_dir)
    print("Next: python scripts/04_verify_qlib.py")


if __name__ == "__main__":
    main()
