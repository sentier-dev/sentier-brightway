# sentier-brightway

One call installs the BAFU-2026 v1 life cycle inventory, an EF 3.1 biosphere and the 25 EF 3.1
LCIA methods into your Brightway project, linked through the Sentier flow mappings. Open it in
Activity Browser, build your foreground on top, compute with stock bw2calc.

## Install

Run in the Python environment where Brightway or Activity Browser is installed:

    pip install sentier-brightway
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
| `--data-root DIR` | `data_root=DIR` | Read the four data repos from local clones under `DIR` instead of downloading. |
| `--skip-nomenclature` | `include_nomenclature=False` | Keep BAFU flows whose EF counterpart carries no factor in the residual database instead of relinking them (see coverage). |

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
    from sentier_brightway.writer import get_node, score
    bd.projects.set_current("my-project")
    act = next(a for a in bd.Database("bafu-2026")
               if a["name"] == "Electricity, low voltage, production CH, at grid")
    score(act, ("sentier", "EF v3.1", "Climate change"))   # kg CO2 eq per kWh

## Current coverage

Output of `sentier-brightway coverage` on 2026-09-14, data pinned in `sources.toml` to
sentier-inventory `2334dfc`, sentier-mappings `07f0e25`, sentier-vocab `396c7be`,
sentier-methods `a181071`:

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
writing the methods.

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
| Ecotoxicity, freshwater_organics | 3.7e5 % | 1.4e8 % | 200 |

Sixteen categories agree to well under 1 % for practically every process. The rest deviate
for identifiable reasons in the mapping and factor data, not in the Brightway install: BAFU
*Sodium* (to water) is bridged onto the EF flow labelled "sodium" that is really sodium
hexadecyl sulphate (CAS 1120-01-0, 93,308 CTUe/kg), which dominates both ecotoxicity
methods; BAFU chromium emissions carry EF's Cr(VI) cancer factors; *Water to turbine* and its
release are characterized with +42.95 and -42.955 m3 world eq and nearly cancel, so water use
comes out small or negative wherever hydropower is upstream; land transformation flows
(*To/From ...*) carry large opposite-sign factors that flip the sign of a few land use scores;
resource use, fossils is a uniform +5 %, most likely one calorific-value conversion. The
remaining outliers trace to the 99 unlinked flows.


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

Parity check against BAFU's published results (needs the LCIA results spreadsheet from
`BAFU-2026 v1_LCIA Results_corrected.zip` and an installed project):

    uv run --extra testing --with openpyxl python scripts/parity_bafu_lcia.py \
        --xlsx "BAFU-2026 v1 LCIA Results_corrected.xlsx" --project my-project \
        --sample 200 --seed 0          # --all for every process
