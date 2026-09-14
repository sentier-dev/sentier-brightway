"""``sentier-brightway db|coverage``."""

from __future__ import annotations

import argparse
import sys
import warnings

from . import coverage, import_bafu_db, render
from .fetch import FetchError


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="sentier-brightway")
    sub = p.add_subparsers(dest="command", required=True)

    db = sub.add_parser("db", help="write BAFU-2026 + EF 3.1 into a Brightway project (bw2data)")
    db.add_argument("--project", required=True, help="bw2data project name")
    db.add_argument("--overwrite", action="store_true", help="replace existing databases")
    db.add_argument("--data-root", default=None, help="local ~/dds-shaped folder (skips download)")
    db.add_argument(
        "--skip-nomenclature",
        action="store_true",
        help="do not relink BAFU flows whose EF counterpart has no factor",
    )

    cov = sub.add_parser("coverage", help="print linking coverage, no Brightway needed")
    cov.add_argument("--data-root", default=None)
    cov.add_argument("--skip-nomenclature", action="store_true")
    return p


def _run(args: argparse.Namespace):
    include = not args.skip_nomenclature
    if args.command == "coverage":
        return coverage(data_root=args.data_root, include_nomenclature=include)
    return import_bafu_db(
        args.project,
        overwrite=args.overwrite,
        data_root=args.data_root,
        include_nomenclature=include,
    )


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv if argv is not None else sys.argv[1:])
    try:
        # the rendered report already carries the unit-conflict line; the API keeps warning
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            cov = _run(args)
    except (FetchError, FileNotFoundError, ValueError, ImportError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(render(cov))
    return 0
