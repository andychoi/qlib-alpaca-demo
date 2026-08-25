#!/usr/bin/env bash
set -euo pipefail

python scripts/01_fetch_constituents.py
python scripts/02_fetch_alpaca_daily.py --limit-symbols 30 --start 2020-01-01
python scripts/03_build_qlib.py --rebuild
python scripts/04_verify_qlib.py --alpha158

echo
echo "Smoke test complete."
