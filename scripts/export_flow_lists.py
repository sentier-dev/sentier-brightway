"""Write the FOODTURE workbook: BAFU-2026 flows and processes as implemented in Brightway.

Usage:
    uv run python scripts/export_flow_lists.py [--data-root ~/dds] [--out ./flow-lists]
                                               [--date YYYY-MM-DD] [--overwrite]

Reads the local checkouts of sentier-inventory, sentier-vocab, sentier-methods and
sentier-mappings under --data-root (default ~/dds, or $SENTIER_DATA_ROOT) and writes
<out>/bafu-2026-v1__ef-3.1_flow-lists_<date>.xlsx, plus csv/ and README.md side artifacts.
Only the xlsx is meant to be shipped. Exit 1 with the reason on any data inconsistency.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date
from pathlib import Path

from sentier_brightway.fetch import ENV_VAR, resolve_data_root
from sentier_brightway.flow_lists import export


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--data-root",
        default=os.environ.get(ENV_VAR, "~/dds"),
        help="folder holding the four data-repo checkouts (default: $SENTIER_DATA_ROOT or ~/dds)",
    )
    parser.add_argument(
        "--out", default="flow-lists", help="output folder (default: ./flow-lists)"
    )
    parser.add_argument("--date", type=date.fromisoformat, default=None, help="YYYY-MM-DD")
    parser.add_argument("--overwrite", action="store_true", help="replace an existing xlsx")
    args = parser.parse_args(argv)
    try:
        root = resolve_data_root(args.data_root)
        result = export(root, Path(args.out), today=args.date, overwrite=args.overwrite)
    except (ValueError, FileNotFoundError, FileExistsError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(result.xlsx)
    for key, value in {**result.counts, **result.headline}.items():
        print(f"  {key}: {value}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
