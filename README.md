# sentier-brightway

```mermaid
flowchart TB
    AB["User's Activity Browser"] -- GET --> DB
    XLSX[("BAFU openLCA results<br/>LCIA Results_corrected.xlsx")] -- COMPARE --> BT
    DASH(["backtest dashboard<br/>emissions.csv, vs_bafu.csv<br/>backtest_dashboard.html"]) -- VIEW --> BROWSER["User's web browser"]

    subgraph GH["GitHub"]
        subgraph SB["sentier-brightway"]
            IDB{"import_bafu_db()"} --> DB(["BAFU Brightway database<br/>+ mappings + EF"])
            IFILES{"import_bafu_files()"} --> FILES(["randonneur files BAFU -> EF<br/>BAFU registry files<br/>EF registry files"])
            FILES -- SCORE --> BT{"run_backtest()"}
            BT --> DASH
        end
        METHODS["sentier-methods<br/>EF methods files"]
        INVENTORY["sentier-inventory<br/>BAFU files"]
        MAPPINGS["sentier-mappings<br/>BAFU -> EF mappings files"]
    end

    IDB -- PULL --> METHODS
    IDB -- PULL --> INVENTORY
    IDB -- PULL --> MAPPINGS
    IFILES -- PULL --> METHODS
    IFILES -- PULL --> INVENTORY
    IFILES -- PULL --> MAPPINGS
```

One call installs the BAFU-2026 v1 life cycle inventory, an EF 3.1 biosphere and the 25 EF 3.1
LCIA methods into your Brightway project, linked through the Sentier flow mappings. Open it in
Activity Browser, build your foreground on top, compute with stock bw2calc.

## Install

Run in the Python environment where Brightway or Activity Browser is installed:

    pip install git+https://github.com/sentier-dev/sentier-brightway   # PyPI release pending
    sentier-brightway db --project my-project

or from Python:

    from sentier_brightway import import_bafu_db
    import_bafu_db("my-project")

The first run downloads about 37 MB of parquet/JSON from the public Sentier data repositories
(pinned commits, sha256-verified) into your user cache. No data ships inside the package.
The install itself takes a few minutes (most of it is bw2data writing the 25 methods).

Options:

| Flag | Python | Effect |
|---|---|---|
| `--overwrite` | `overwrite=True` | Replace a previous install in the same project. Also the recovery step after a partial failure. Other databases in the project that link to ours are reprocessed automatically. |
| `--data-root DIR` | `data_root=DIR` | Read the four data repos from local clones under `DIR` instead of downloading. Resolution order: argument > `$SENTIER_DATA_ROOT` > verified download cache. |
| `--skip-nomenclature` | `include_nomenclature=False` | Keep BAFU flows whose EF counterpart carries no factor in the residual database instead of relinking them (see coverage). |
| `files --out DIR` | `import_bafu_files(DIR)` | Write plain files to `DIR` instead of a bw2data project (see below). `--overwrite` replaces a non-empty `DIR`; `--data-root` and `--skip-nomenclature` work as above. |
| `files --no-datapackages` | `datapackages=False` | Skip the `bw_package/` bw_processing output; registry, mappings and manifest are still written. |

`sentier-brightway coverage [--data-root DIR]` prints the linking report below without
touching Brightway.

## What you get

| Brightway object | Content |
|---|---|
| database `bafu-2026` | 11,947 BAFU-2026 v1 processes with technosphere links resolved |
| database `ef-3.1-biosphere` | EF 3.1 elementary flows; BAFU emissions are relinked onto these |
| database `bafu-2026-residual` | BAFU flows with no EF 3.1 counterpart at all (kept for transparency; empty when the mapping is complete) |
| methods `("sentier", "EF v3.1", <category>)` | 25 EF 3.1 impact categories, global factors |

Model your own activities by linking product inputs to `bafu-2026` processes and direct
emissions to `ef-3.1-biosphere` flows. Nothing else needs mapping.

In Activity Browser: run the install from the AB environment, then start (or restart) AB and
select the project. The three databases appear in the database list and the methods under
`sentier` > `EF v3.1` in the impact categories tab. AB reads the project on start-up, so
reload the project after an install into a project it already has open.

From Python, one score:

    import bw2data as bd
    from sentier_brightway.writer import score
    bd.projects.set_current("my-project")
    act = next(a for a in bd.Database("bafu-2026")
               if a["name"] == "Electricity, low voltage, production CH, at grid")
    score(act, ("sentier", "EF v3.1", "Climate change"))   # kg CO2 eq per kWh

## Files instead of a database

If you prefer plain files (pandas, your own tooling, or bw2calc without bw2data), the same
build can be written to a folder instead of a project. No Brightway project is created and
bw2data is not imported:

    pip install git+https://github.com/sentier-dev/sentier-brightway   # PyPI release pending
    sentier-brightway files --out ./bafu-2026-ef31
    # or: from sentier_brightway import import_bafu_files; import_bafu_files("./bafu-2026-ef31")

The folder contains:

    registry/       processes, biosphere, exchanges, methods, characterization-factors (parquet)
    mappings/       every JSON of the sentier-mappings bridge folder, copied verbatim (see manifest)
    bw_package/     bw_processing datapackages: bafu-2026/ (inventory) and methods/<slug>/ (one per method)
    manifest.json   layout version, data pins, citation, coverage, row counts

`manifest.json` also carries `bridge_packages`, the packages that were actually applied in
order, and `include_nomenclature`, which says whether the order-4 nomenclature package was
among them (`--skip-nomenclature` sets it to false). `--overwrite` only ever replaces a
folder that holds a previous export's `manifest.json`; any other non-empty folder, a file or
a symlink as `--out` is refused and left untouched.

Every table in `registry/` is joined by an integer `bw_id`: a contiguous id starting at 1,
processes first (sorted), then the EF biosphere flows, then the residual BAFU flows. The same
ids are the row/column indices of the datapackages, so `registry/processes.parquet` is the
lookup from a process `code` or `name` to the id you put into a demand vector.

`bw_package/` is stock bw_processing, so stock bw2calc reads it with no bw2data project and
without importing sentier_brightway at all:

    from pathlib import Path
    import bw2calc as bc
    import bw_processing as bwp
    import pandas as pd

    out = Path("./bafu-2026-ef31")
    procs = pd.read_parquet(out / "registry/processes.parquet")
    code = procs.loc[procs.name.str.startswith("Electricity, low voltage, production CH"), "code"].iloc[0]
    bw_id = int(procs.loc[procs.code == code, "bw_id"].iloc[0])

    fs = bwp.generic_directory_filesystem   # dirpath must be a pathlib.Path
    inventory = bwp.load_datapackage(fs(dirpath=out / "bw_package/bafu-2026"))
    method = bwp.load_datapackage(fs(dirpath=out / "bw_package/methods/ef-3.1__climate-change"))
    lca = bc.LCA({bw_id: 1.0}, data_objs=[inventory, method])
    lca.lci(); lca.lcia(); lca.score

Method folders are named by slug (`ef-3.1__<category>`); `registry/methods.parquet` lists
them. `sentier_brightway.datapackage.load_inventory_datapackage(out)` and
`load_method_datapackage(out, method_id)` wrap exactly those two `load_datapackage` calls.
Technosphere inputs are stored as positive amounts with `flip_array` set, the usual
bw_processing convention. The parquet side reads back with
`sentier_brightway.registry.load_registry(folder)`; the shortest path to one score is:

    from sentier_brightway.registry import load_registry
    from sentier_brightway.datapackage import score
    reg = load_registry("./bafu-2026-ef31/registry")
    code = reg.processes[reg.processes.name.str.startswith("Electricity, low voltage, production CH")].code.iloc[0]
    score("./bafu-2026-ef31", code, "ef-3.1:climate-change")   # 0.0320835 kg CO2 eq per kWh

Both modes come from the same in-memory build (`sentier_brightway.assemble`), so scores are
identical: the CH low-voltage electricity mix gives 0.0320835 kg CO2 eq/kWh in the bw2data
project and 0.0320835 from the datapackages. The datapackages are static vectors only for
now; uncertainty distributions are not exported yet.

## Backtest and dashboard

`sentier-brightway backtest` scores all 11,947 processes for the 25 EF 3.1 categories from
the file-mode datapackages with one adjoint solve per category (25 transposed solves of the
technosphere matrix instead of 11,947 x 25 forward solves), cross-checks the result against
the plain bw2calc loop, and compares every score with BAFU's own openLCA results from
`BAFU-2026 v1 LCIA Results_corrected.xlsx`, per the table's unit (electricity per MJ, transport
per km, and so on). The comparison uses the same guards as the Agribalyse dashboards: a zero
reference gives no percentage, a near-zero floor (both values below 1 % of the category's
median reference count as 0 %) and a fold cap (gaps above 10x are blanked and counted).

    pip install "sentier-brightway[fast]"    # adds pypardiso; scipy's SuperLU is the fallback
    sentier-brightway backtest --out dashboard --data-root ~/dds
    sentier-brightway backtest --out dashboard --files ./bafu-2026-ef31   # reuse an export

`--xlsx` defaults to `~/dds/sources/bafu-2026/BAFU-2026 v1_LCIA Results_corrected.zip` (the
zip or the extracted xlsx both work). Without `--files` the command first writes a file-mode
export into `<out>/files/`. About 5 s with an existing export, about 10 s including the
export from local clones (the first run without `--data-root` adds the download).

Written into `--out`:

    emissions.csv        one row per process, the 25 scores in the table's unit
    vs_bafu.csv          the same rows as signed percent difference vs BAFU (blank = guarded)
    vs_bafu_meta.json    baseline, thresholds, suppressed cells, unmatched rows on both sides
    run_report.json      timings, solver, counts and the export's data pins
    backtest/*.parquet   scores, reference, diff_pct, summary (the full-precision record)
    files/               the file-mode export (only when --files was not given)

View it locally:

    python -m http.server 8000 --directory dashboard
    # open http://localhost:8000/backtest_dashboard.html

The page has two tabs (percent difference vs BAFU, absolute scores) plus a Distributions
view with one sorted chart per category; a blank cell means no or zero reference, or a gap
above the fold cap. There is no flow drill-down in this version. `dashboard/` in the
repository holds only the page and its vendored assets; everything the command writes there
is gitignored. A hosted copy at dashboard.d-d-s.ch/bafu/ is access-restricted.

Anchor: *Electricity, low voltage, production CH, at grid* scores 0.0320835 kg CO2 eq/kWh
here, i.e. 0.008912093/MJ, against 0.008912093/MJ in BAFU's table (ratio 1.0000). On the
2026-09-16 run every one of the 11,947 processes matched a table row; human toxicity cancer
differs by a documented chromium convention (BAFU counts unspecified chromium as zero, EF's
own flow carries the Cr(VI) factor), and the other categories agree with BAFU within a
fraction of a percent at the median.

## Current coverage

Output of `sentier-brightway coverage` on 2026-09-14, data pinned in `sources.toml` to
sentier-inventory `2334dfc`, sentier-mappings `07f0e25`, sentier-vocab `396c7be`,
sentier-methods `a181071` (the sentier-inventory pin is a pre-merge commit of PR #3 and will
move to main after the merge):

    Installed bafu-2026: 11947 processes
    Installed ef-3.1-biosphere and 25 EF 3.1 methods
    Linked 2580/2679 BAFU flows to EF 3.1 (96.3%); 286797/293747 biosphere exchanges (97.6%)
      513 of the linked flows point at EF flows with no factor (nomenclature only, impact zero)
    Unlinked flows kept in bafu-2026-residual (no EF 3.1 counterpart in the bridge):
      economic issues: 5
      emissions to air: 18
      emissions to soil: 10
      emissions to water: 18
      non material emissions: 8
      resources: 40

    Source: Life Cycle Inventory database of the Swiss Federal Administration, BAFU:2026.

A full install (`db --data-root`, local clones) took 2 min 56 s; most of that is bw2data
writing the methods. The file mode (`files --data-root`) writes the same content in about
8 s to a 40 MB folder: `registry/` 21 MB, `bw_package/` 17 MB, `mappings/` 2.6 MB.

## Limitations (v0.1)

- Regionalized EF factors are not installed; global factors only. BAFU applies country
  water-use factors, which is where the water-use tail of the backtest comes from.
- EF flow units are taken from the mapping where known and default to kilogram otherwise
  (labels only; they do not affect results).
- Only BAFU-2026 v1 and EF 3.1 are supported.
- 99 of the 2,679 BAFU flows used in exchanges have no EF 3.1 counterpart yet. They are kept in
  `bafu-2026-residual` with their exchanges intact, so no inventory is lost, but they carry no
  characterization factor.
- BAFU flows whose EF counterpart carries no factor are relinked by default (impact zero,
  reported in the coverage block); `--skip-nomenclature` keeps them in the residual database.
- The backtest dashboard has no flow drill-down (v1).
- Activity Browser: the package must be installed and run in the AB environment (it needs
  that environment's bw2data), and AB has to reload the project after an install.

## Licence and citation

Code: MIT. Data is read from the Sentier repositories under their own licences. BAFU data:
*Source: Life Cycle Inventory database of the Swiss Federal Administration, BAFU:2026.*
Keep this citation in any work derived from the installed data.

## Development

    uv run --extra testing pytest
    uv run --extra dev pre-commit run --all-files
    uv run python scripts/pin_sources.py   # re-pin after the data repos change
    uv run sentier-brightway coverage --data-root ~/dds   # read local clones
    uv run sentier-brightway files --out /tmp/bafu-files --data-root ~/dds --overwrite   # file mode, no bw2data
    SENTIER_DATA_ROOT=~/dds uv run sentier-brightway coverage   # env var alternative to --data-root, honoured by db, files and the import_bafu_* functions too

Backtest against BAFU's published results (needs the LCIA results zip or xlsx, see
"Backtest and dashboard"):

    uv run --extra fast sentier-brightway backtest --out dashboard --data-root ~/dds   # ~10 s, pypardiso
    uv run sentier-brightway backtest --out /tmp/bt --files /tmp/bafu-files              # reuse an export, scipy
