"""``sentier-brightway db|files|coverage|backtest``."""

from __future__ import annotations

import argparse
import logging
import sys
import warnings
from pathlib import Path

from . import coverage, import_bafu_db, import_bafu_files, render
from .constants import CITATION
from .fetch import FetchError

# files.ExistingOutputError is a RuntimeError and FileNotFoundError/NotADirectoryError are
# OSErrors, so the except tuple in main() covers them


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

    fil = sub.add_parser(
        "files", help="write registry parquet + mappings + datapackages to a folder (no bw2data)"
    )
    fil.add_argument("--out", required=True, help="output folder")
    fil.add_argument("--overwrite", action="store_true", help="replace a non-empty output folder")
    fil.add_argument(
        "--no-datapackages",
        action="store_true",
        help="skip the bw_processing output (bw_package/)",
    )
    fil.add_argument(
        "--data-root", default=None, help="local ~/dds-shaped folder (skips download)"
    )
    fil.add_argument(
        "--skip-nomenclature",
        action="store_true",
        help="do not relink BAFU flows whose EF counterpart has no factor",
    )

    cov = sub.add_parser("coverage", help="print linking coverage, no Brightway needed")
    cov.add_argument("--data-root", default=None)
    cov.add_argument("--skip-nomenclature", action="store_true")

    bt = sub.add_parser(
        "backtest", help="score all processes and compare with BAFU's published EF 3.1 results"
    )
    bt.add_argument(
        "--out", required=True, help="dashboard data folder (CSV, meta, parquet, run_report)"
    )
    bt.add_argument(
        "--xlsx",
        default=None,
        help="BAFU 'LCIA Results' .xlsx or .zip (default: ~/dds/sources/bafu-2026/...)",
    )
    bt.add_argument(
        "--files",
        default=None,
        help="existing file-mode export; omitted = export into <out>/files first",
    )
    bt.add_argument("--data-root", default=None, help="local ~/dds-shaped folder (skips download)")
    bt.add_argument("--skip-nomenclature", action="store_true")
    bt.add_argument("--fixture-categories", action="store_true", help=argparse.SUPPRESS)
    return p


def _run_backtest(args: argparse.Namespace, include: bool) -> str:
    """Export first when no ``--files`` is given, then score, compare and write."""
    from . import backtest as bt  # bw2calc is imported inside run_backtest

    files_dir = Path(args.files) if args.files else Path(args.out) / "files"
    if not args.files:
        # <out>/files is ours: overwrite only ever replaces a previous export there
        import_bafu_files(
            files_dir, data_root=args.data_root, include_nomenclature=include, overwrite=True
        )
    cats = bt.FIXTURE_CATEGORIES if args.fixture_categories else bt.CATEGORIES
    xlsx = Path(args.xlsx) if args.xlsx else bt.DEFAULT_XLSX.expanduser()
    result = bt.run_backtest(files_dir, xlsx, args.out, categories=cats)
    return f"{bt.render_summary(result)}\n{CITATION}"


def _run(args: argparse.Namespace) -> str:
    """Run one subcommand and return the text to print on success."""
    include = not args.skip_nomenclature
    if args.command == "backtest":
        return _run_backtest(args, include)
    if args.command == "coverage":
        cov = coverage(data_root=args.data_root, include_nomenclature=include)
    elif args.command == "files":
        cov = import_bafu_files(
            args.out,
            data_root=args.data_root,
            include_nomenclature=include,
            datapackages=not args.no_datapackages,
            overwrite=args.overwrite,
        )
    else:
        cov = import_bafu_db(
            args.project,
            overwrite=args.overwrite,
            data_root=args.data_root,
            include_nomenclature=include,
        )
    text = render(cov)
    if args.command == "files":
        text += f"\nFiles written to {Path(args.out).resolve()}"
    return text


def _progress_handler() -> logging.Handler:
    """Progress lines (project creation, one per method) on stderr while a command runs."""
    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(logging.INFO)
    handler.setFormatter(logging.Formatter("%(message)s"))
    return handler


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv if argv is not None else sys.argv[1:])
    logger = logging.getLogger("sentier_brightway")
    handler = _progress_handler()
    previous_level = logger.level
    logger.addHandler(handler)
    logger.setLevel(min(logger.level or logging.INFO, logging.INFO))
    try:
        # the rendered report already carries the unit-conflict line; the API keeps warning,
        # and any other warning (bw2data's included) still reaches the user
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message=r".*conflicting units", category=UserWarning)
            text = _run(args)
    except (FetchError, OSError, ValueError, ImportError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous_level)
    print(text)
    return 0
