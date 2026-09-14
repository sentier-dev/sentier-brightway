"""Compare our EF 3.1 scores for installed BAFU-2026 processes with BAFU's published results.

Usage (needs an installed project, see README):

    uv run --extra testing --with openpyxl python scripts/parity_bafu_lcia.py \
        --xlsx "BAFU-2026 v1 LCIA Results_corrected.xlsx" --project my-project \
        --sample 200 --seed 0 [--all] [--out parity.csv]

Writes ``parity.csv`` (process, method, ours, ref, rel_dev) and prints a per-method summary.
The table reports scores per its own unit (electricity in MJ, we install kWh), so scores are
compared per the table's unit; processes whose units cannot be reconciled are skipped and
counted. One factorized technosphere solve is reused for every process and the 25
characterization matrices are cached, so ``--all`` (11,947 processes) takes minutes.
"""

from __future__ import annotations

import argparse
import csv
import math
import random
import statistics
import sys
import warnings
from pathlib import Path
from types import MappingProxyType

SHEET = "BAFU_2026 v1"
METHOD_PREFIX = ("sentier", "EF v3.1")
OUTLIER_THRESHOLD = 0.01
WORST_ROWS = 10
PROGRESS_EVERY = 500

# our sentier-methods impact category -> column name in the BAFU table (EF 3.1 family)
COLUMN_FOR_CATEGORY = MappingProxyType(
    {
        "Acidification": "Acidification [mol H+ eq]",
        "Climate change": "Climate change [kg CO2 eq]",
        "Climate change-Biogenic": "Climate change (biogenic) [kg CO2 eq]",
        "Climate change-Fossil": "Climate change (fossil) [kg CO2 eq]",
        "Climate change-Land use and land use change": "Climate change (land use) [kg CO2 eq]",
        "EF-particulate Matter": "Particulate matter [disease incidence]",
        "Eutrophication marine": "Eutrophication marine [kg N eq]",
        "Eutrophication, freshwater": "Eutrophication freshwater [kg P eq]",
        "Eutrophication, terrestrial": "Eutrophication terrestrial [mol N eq]",
        "Human toxicity, cancer": "Human toxicity cancer [CTUh]",
        "Human toxicity, cancer_inorganics": "Human toxicity cancer (inorganics) [ CTUh ]",
        "Human toxicity, cancer_organics": "Human toxicity cancer (organics) [CTUh]",
        "Human toxicity, non-cancer": "Human toxicity non-cancer [CTUh]",
        "Human toxicity, non-cancer_inorganics": "Human toxicity non-cancer (inorganics) - [CTUh]",
        "Human toxicity, non-cancer_organics": "Human toxicity non-cancer (organics) [CTUh]",
        "Ionising radiation, human health": "Ionising radiation (human health) [kBq U235 eq]",
        "Land use": "Land use [dimensionless (pt)]",
        "Ozone depletion": "Ozone depletion [kg CFC11 eq]",
        "Photochemical ozone formation - human health": (
            "Photochemical ozone formation (human health) [kg NMVOC eq]"
        ),
        "Resource use, fossils": "Resource use fossils [MJ (net calorific)]",
        "Resource use, minerals and metals": "Resource use minerals and metals [kg Sb eq]",
        "Water use": "Water use [m3 world eq]",
        "Ecotoxicity, freshwater": "Ecotoxicity freshwater [CTUe]",
        "Ecotoxicity, freshwater_inorganics": "Ecotoxicity freshwater (inorganics) [CTUe]",
        "Ecotoxicity, freshwater_organics": "Ecotoxicity freshwater (organics) [CTUe]",
    }
)

# table unit spelling -> Brightway spelling (as written by sentier_brightway.units)
TABLE_UNITS = MappingProxyType(
    {
        "kg": "kilogram",
        "MJ": "megajoule",
        "Item(s)": "unit",
        "m3": "cubic meter",
        "m2": "square meter",
        "m": "meter",
        "t*km": "ton kilometer",
        "p*km": "person kilometer",
        "h": "hour",
        "km*a": "kilometer-year",
        "m2*a": "square meter-year",
    }
)

# (our unit, table unit after normalisation) -> multiply our per-unit score by this. The two
# non-trivial entries were verified on climate change (ratios exactly 1.0000 and 1000.0):
# the table writes Nm3 as m3, and its "m" rows for passenger transport are really per metre.
UNIT_FACTORS = MappingProxyType(
    {
        ("kilowatt hour", "megajoule"): 1 / 3.6,
        ("normal cubic meter", "cubic meter"): 1.0,
        ("kilometer", "meter"): 1 / 1000,
    }
)


def demojibake(text: str) -> str:
    """The table double-encodes non-ASCII names ('ä' arrives as 'ÃƒÂ¤'); undo that."""
    for _ in range(2):
        try:
            fixed = text.encode("cp1252").decode("utf-8")
        except UnicodeError:
            return text
        if fixed == text:
            return text
        text = fixed
    return text


def load_table(path: Path) -> dict[str, tuple[str, dict[str, float]]]:
    """``product -> (unit, {column name: score})`` for the EF 3.1 columns of the sheet."""
    import openpyxl

    ws = openpyxl.load_workbook(path, read_only=True)[SHEET]
    rows = ws.iter_rows(values_only=True)
    families, header = next(rows), next(rows)
    family = None
    ef_columns: dict[int, str] = {}
    for i, (fam, name) in enumerate(zip(families, header)):
        family = fam or family
        if family == "EF 3.1" and name:
            ef_columns[i] = " ".join(str(name).split())
    table = {}
    for row in rows:
        if not row[0]:
            continue
        scores = {name: float(row[i] or 0.0) for i, name in ef_columns.items()}
        table[demojibake(str(row[0]).strip())] = (str(row[3]).strip(), scores)
    return table


def unit_factor(ours: str, table: str) -> float | None:
    """Multiply our per-unit score by this to express it per the table's unit; None = skip."""
    table_norm = TABLE_UNITS.get(table, table)
    if ours == table_norm:
        return 1.0
    return UNIT_FACTORS.get((ours, table_norm))


def rel_dev(ours: float, ref: float) -> float:
    if ref == 0.0:
        return 0.0 if abs(ours) < 1e-15 else math.inf
    return (ours - ref) / abs(ref)


def installed_methods(bd) -> list[tuple[str, tuple[str, ...]]]:
    """``(impact category, method key)`` for every installed method under our prefix."""
    return sorted(
        (key[len(METHOD_PREFIX)], tuple(key))
        for key in bd.methods
        if tuple(key[: len(METHOD_PREFIX)]) == METHOD_PREFIX
    )


def pick_processes(db, sample: int | None, seed: int) -> list:
    nodes = sorted(db, key=lambda a: a["code"])
    if sample is None or sample >= len(nodes):
        return nodes
    return random.Random(seed).sample(nodes, sample)


class Scorer:
    """One LCA object: factorized technosphere, cached characterization matrix per method."""

    def __init__(self, bd, bc, seed_activity, keys: list[tuple[str, ...]]):
        fu, data_objs, _ = bd.prepare_lca_inputs({seed_activity: 1.0}, method=keys[0])
        self.lca = bc.LCA(fu, data_objs=data_objs)
        self.lca.lci(factorize=True)
        self.lca.lcia()
        self.matrices = {}
        for key in keys:
            self.lca.switch_method(key)
            self.lca.lcia()
            self.matrices[key] = self.lca.characterization_matrix.copy()

    def scores(self, activity) -> dict[tuple[str, ...], float]:
        self.lca.lci(demand={activity.id: 1.0})
        inventory = self.lca.inventory
        return {key: float((matrix * inventory).sum()) for key, matrix in self.matrices.items()}


def compare(scorer, table, methods, processes) -> tuple[list[dict], dict[str, int]]:
    counts = {"matched": 0, "unmatched": 0, "unit_skipped": 0}
    rows = []
    for i, act in enumerate(processes, start=1):
        product = f"{act['name']} - {act['location']}"
        if product not in table:
            counts["unmatched"] += 1
            print(f"unmatched: {product}", file=sys.stderr)
            continue
        table_unit, ref_scores = table[product]
        factor = unit_factor(act["unit"], table_unit)
        if factor is None:
            counts["unit_skipped"] += 1
            print(
                f"unit skipped: {product} ours={act['unit']} table={table_unit}", file=sys.stderr
            )
            continue
        counts["matched"] += 1
        ours = scorer.scores(act)
        for category, key in methods:
            ref = ref_scores[COLUMN_FOR_CATEGORY[category]]
            value = ours[key] * factor
            rows.append(
                {
                    "process": product,
                    "method": category,
                    "ours": value,
                    "ref": ref,
                    "rel_dev": rel_dev(value, ref),
                }
            )
        if i % PROGRESS_EVERY == 0:
            print(f"{i}/{len(processes)} processes scored", file=sys.stderr)
    return rows, counts


def summarise(rows: list[dict]) -> str:
    by_method: dict[str, list[float]] = {}
    for r in rows:
        by_method.setdefault(r["method"], []).append(abs(r["rel_dev"]))
    lines = [f"{'method':<46} {'median':>8} {'max':>10} {'>1%':>5} {'n':>5}"]
    for method, devs in sorted(by_method.items()):
        finite = [d for d in devs if math.isfinite(d)]
        med = statistics.median(devs) if devs else math.nan
        mx = max(finite) if finite else math.nan
        inf = len(devs) - len(finite)
        over = sum(1 for d in devs if d > OUTLIER_THRESHOLD)
        mx_txt = f"{mx:9.2%}" + ("*" if inf else " ")
        lines.append(f"{method:<46} {med:8.2%} {mx_txt:>10} {over:>5} {len(devs):>5}")
    total_over = sum(1 for r in rows if abs(r["rel_dev"]) > OUTLIER_THRESHOLD)
    lines.append(f"rows with |rel_dev| > 1%: {total_over}/{len(rows)}")
    lines.append("* = at least one row where the table gives 0 and we do not (inf, excluded)")
    lines.append("")
    lines.append(f"{WORST_ROWS} worst rows:")
    worst = sorted(rows, key=lambda r: abs(r["rel_dev"]), reverse=True)[:WORST_ROWS]
    for r in worst:
        lines.append(
            f"  {r['rel_dev']:+9.2%}  {r['method']:<40} ours={r['ours']:.4g} "
            f"ref={r['ref']:.4g}  {r['process']}"
        )
    return "\n".join(lines)


def write_csv(rows: list[dict], path: Path) -> None:
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["process", "method", "ours", "ref", "rel_dev"])
        writer.writeheader()
        writer.writerows(rows)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--xlsx", required=True, type=Path)
    p.add_argument("--project", required=True)
    p.add_argument("--sample", type=int, default=200)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--all", action="store_true", help="every process, ignores --sample")
    p.add_argument("--out", type=Path, default=Path("parity.csv"))
    return p.parse_args(argv)


def check_mapping(methods, table) -> list[str]:
    """Categories without a table column, or mapped to a column the sheet does not have."""
    columns = next(iter(table.values()))[1] if table else {}
    problems = [f"unmapped method {c!r}" for c, _ in methods if c not in COLUMN_FOR_CATEGORY]
    for category, _ in methods:
        column = COLUMN_FOR_CATEGORY.get(category)
        if column is not None and column not in columns:
            problems.append(f"missing table column {column!r} (for {category!r})")
    return problems


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    warnings.filterwarnings("ignore", message=".*pypardiso.*")
    import bw2calc as bc
    import bw2data as bd

    from sentier_brightway.constants import INVENTORY_DB

    if args.project not in bd.projects:
        print(f"ERROR: project {args.project!r} does not exist", file=sys.stderr)
        return 2
    bd.projects.set_current(args.project)
    table = load_table(args.xlsx)
    methods = installed_methods(bd)
    problems = check_mapping(methods, table)
    if problems:
        print("ERROR: " + "; ".join(problems), file=sys.stderr)
        return 2
    db = bd.Database(INVENTORY_DB)
    processes = pick_processes(db, None if args.all else args.sample, args.seed)
    print(f"{len(methods)} methods, {len(processes)} processes, {len(table)} table rows")
    scorer = Scorer(bd, bc, processes[0], [key for _, key in methods])
    rows, counts = compare(scorer, table, methods, processes)
    write_csv(rows, args.out)
    print(
        f"matched {counts['matched']}, unmatched {counts['unmatched']}, "
        f"unit skipped {counts['unit_skipped']}; wrote {args.out}"
    )
    print(summarise(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
