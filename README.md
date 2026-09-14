# sentier-brightway

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
    mappings/       the randonneur packages that were applied, copied verbatim from sentier-mappings
    bw_package/     bw_processing datapackages: bafu-2026/ (inventory) and methods/<slug>/ (one per method)
    manifest.json   layout version, data pins, citation, coverage, row counts

Every table in `registry/` is joined by an integer `bw_id`: a contiguous id starting at 1,
processes first (sorted), then the EF biosphere flows, then the residual BAFU flows. The same
ids are the row/column indices of the datapackages, so `registry/processes.parquet` is the
lookup from a process `code` or `name` to the id you put into a demand vector.

`bw_package/` is stock bw_processing, so stock bw2calc reads it with no bw2data project:

    import bw2calc as bc
    from sentier_brightway.datapackage import load_inventory_datapackage, load_method_datapackage
    inventory = load_inventory_datapackage("./bafu-2026-ef31")
    method = load_method_datapackage("./bafu-2026-ef31", "ef-3.1:climate-change")
    lca = bc.LCA({bw_id: 1.0}, data_objs=[inventory, method])
    lca.lci(); lca.lcia(); lca.score

The two loaders are conveniences; `bw_processing.load_datapackage(bw_processing.FS(...))` on
the folders works just as well. Technosphere inputs are stored as positive amounts with
`flip_array` set, the usual bw_processing convention. The parquet side reads back with
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

## Parity with BAFU's published LCIA results

`scripts/parity_bafu_lcia.py` scores installed processes with stock bw2calc and compares them
with the EF 3.1 columns of BAFU's own `BAFU-2026 v1 LCIA Results_corrected.xlsx`, per the
table's unit. Anchor: *Electricity, low voltage, production CH, at grid* gives 0.0320835 kg
CO2 eq/kWh here, i.e. 0.008912093/MJ, against 0.008912093/MJ in the table (ratio 1.0000).

Random sample of 200 processes (`--sample 200 --seed 0`, 2026-09-14), relative deviation
|ours - ref| / |ref| per method:

| Method | Median | Max | Rows > 1 % (of 200) |
|---|---|---|---|
| Acidification | 0.00 % | 0.02 % | 0 |
| Climate change | 0.00 % | 0.03 % | 0 |
| Climate change-Biogenic | 0.00 % | 0.02 % | 0 |
| Climate change-Fossil | 0.00 % | 0.03 % | 0 |
| Climate change-Land use and land use change | 0.00 % | 0.00 % | 0 |
| EF-particulate Matter | 0.00 % | 0.26 % | 0 |
| Eutrophication, freshwater | 0.00 % | 0.03 % | 0 |
| Eutrophication, terrestrial | 0.00 % | 0.03 % | 0 |
| Eutrophication marine | 0.12 % | 17.5 % | 19 |
| Human toxicity, cancer_organics | 0.00 % | 0.34 % | 0 |
| Human toxicity, non-cancer | 0.12 % | 14.1 % | 12 |
| Human toxicity, non-cancer_inorganics | 0.15 % | 14.2 % | 12 |
| Human toxicity, non-cancer_organics | 0.02 % | 74.8 % | 4 |
| Ionising radiation, human health | 0.00 % | 99.9 % | 2 |
| Ozone depletion | 0.00 % | 0.04 % | 0 |
| Photochemical ozone formation - human health | 0.00 % | 0.04 % | 0 |
| Resource use, minerals and metals | 0.00 % | 42.6 % | 1 |
| Ecotoxicity, freshwater_inorganics | 1.05 % | 245 % | 102 |
| Land use | 2.17 % | 583 % | 135 |
| Resource use, fossils | 4.97 % | 6.37 % | 195 |
| Human toxicity, cancer | 90.8 % | 1711 % | 199 |
| Water use | 95.0 % | 6484 % | 199 |
| Human toxicity, cancer_inorganics | 210 % | 12218 % | 200 |
| Ecotoxicity, freshwater | 14517 % | 1.1e6 % | 200 |
| Ecotoxicity, freshwater_organics | 3.7e5 % | 1.4e8 % * | 200 |

\* one sampled process has 0 in the sheet and a non-zero score here; that row (inf) is
excluded from the max, which is over the 199 finite rows.

Eleven categories match to within 0.35 % on every sampled process: acidification, the four
climate change methods, particulate matter, freshwater and terrestrial eutrophication,
human toxicity cancer (organics), ozone depletion and photochemical ozone formation.
Ionising radiation, minerals and metals, and human toxicity non-cancer (organics) have 1 to 4
outliers each. Marine eutrophication (19 rows > 1 %, max 17.5 %) and the two other human
toxicity non-cancer methods (12 rows, max 14 %) have not yet been traced.

The large deviations have identified causes (verified with the sentier-mappings maintainers):

- **Ecotoxicity (both methods)**: a sentier-vocab label defect. The EF flow with CAS
  1120-01-0 (sodium hexadecyl sulphate, 93,308 CTUe/kg) carries the pref_label "sodium";
  BAFU's *Sodium* has no CAS, so the name matcher picked it. Fix in progress upstream
  (sentier-importers branch `fix/vocab-label-defects`); after it BAFU *Sodium* maps to EF
  *Sodium* (CAS 7440-23-5, no factor) and ecotoxicity moves to parity.
- **Human toxicity cancer (inorganics), and the cancer total**: not a mapping error. EF 3.1's
  own flow *Chromium* (CAS 7440-47-3) carries the Cr(VI) factors (identical to
  *Chromium(6+)*), and BAFU *Chromium* (same CAS) onto it is the faithful mapping. BAFU's
  published results treat unspecified chromium as Cr(III); this is a method-implementation
  choice that DdS will decide on. Until then human toxicity cancer (inorganics) is 2 to 3
  times BAFU's figure by construction.
- **Water use**: the EF table nets turbined water to zero through the *Water to turbine*
  +42.95 / *Water from turbine* -42.95 pair. The mapping follows the table; both terms are
  about 560 m3/kWh on the Swiss mix and cancel, so the large relative deviations sit on very
  small net values. The category is numerically sensitive, not wrong by construction.
- **Land use**: *To/From* transformation flows carry opposite-sign EF factors; deviations are
  concentrated on agricultural processes and are under investigation (two example rows are
  with the mappings maintainers).
- **Resource use, fossils**: uniform +3 to +6 %, not yet traced (suspected energy-content
  conversion on the resource side).

These are data issues in sentier-mappings / sentier-vocab / sentier-methods, not in the
Brightway install; the numbers will move with the next manifest pin.


## Limitations (v0.1)

- Regionalized EF factors are not installed; global factors only.
- EF flow units are taken from the mapping where known and default to kilogram otherwise
  (labels only; they do not affect results).
- Only BAFU-2026 v1 and EF 3.1 are supported.
- 99 of the 2,679 BAFU flows used in exchanges have no EF 3.1 counterpart yet. They are kept in
  `bafu-2026-residual` with their exchanges intact, so no inventory is lost, but they carry no
  characterization factor.
- BAFU flows whose EF counterpart carries no factor are relinked by default (impact zero,
  reported in the coverage block); `--skip-nomenclature` keeps them in the residual database.
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

Parity check against BAFU's published results (needs the LCIA results spreadsheet from
`BAFU-2026 v1_LCIA Results_corrected.zip` and an installed project):

    uv run --extra testing --with openpyxl python scripts/parity_bafu_lcia.py \
        --xlsx "BAFU-2026 v1 LCIA Results_corrected.xlsx" --project my-project \
        --sample 200 --seed 0          # --all for every process
