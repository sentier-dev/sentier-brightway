# Changelog

## 0.1.0 (unreleased)

- sentier-inventory layout 0.3.0: one folder per source release (`data/<source>-<version>/`)
  with `sector` as a process column. `load_inventory(root, source, source_version=None)` picks
  the folder from its `metadata.json` (errors list the source/version pairs present; two
  releases of one source need `source_version`); `Inventory.sectors` and `source_version` come
  from the metadata, the `sector` column stays on the frame and on every process node.
  `source_version=` on `assemble` / `coverage` / `import_db` / `import_files` and their
  `import_bafu_*` wrappers, `--source-version` on every CLI command. `sources.toml` pins the
  three files of `data/bafu-2026-v1/` instead of thirty-three sector files.
- README opens with an architecture schema (Mermaid): Activity Browser, the two importers, the
  three Sentier data repositories they pull from, and the backtest against BAFU's openLCA results.
- Backtest module (`sentier_brightway.backtest`) and `sentier-brightway backtest` CLI: all
  11,947 processes x 25 EF 3.1 categories from the file-mode datapackages by adjoint solve,
  cross-checked against the plain bw2calc loop, compared with BAFU's published openLCA
  results per the table's unit.
- Dashboard (`dashboard/backtest_dashboard.html`, a copy of the sentier-agribalyse-4.0 page
  with 25 categories) fed by the backtest's CSV and meta files.
- Dashboard v2: box-plot main view (25 categories, symmetric-log axis, quartile boxes, 1.5 IQR
  whiskers, outlier dots), a sector facet, a per-category worst-200 drill-down and a lazily
  loaded per-process detail panel. `backtest` now also writes `boxes.json` and `worst/`; the
  summary gains quartile columns. The heatmap table, the Emissions view and the Distributions
  view are removed.
- bw2calc and openpyxl are now hard dependencies; the `fast` extra adds pypardiso.
- Parity script `scripts/parity_bafu_lcia.py` removed; the backtest supersedes it.
- bw2data mode: `import_bafu_db()` / `sentier-brightway db` installs BAFU-2026 v1, an EF 3.1
  biosphere and the 25 EF 3.1 methods into a Brightway project, relinked through the
  sentier-mappings bridge.
- File mode: `import_bafu_files()` / `sentier-brightway files` writes the same build as a
  parquet registry, the applied randonneur packages and bw_processing datapackages for
  bw2calc without bw2data. `--overwrite` only ever replaces a previous export.
- Pinned, sha256-verified data manifest (`sources.toml`), downloaded on first use; no data in
  the wheel.
- Coverage report (`sentier-brightway coverage`) with the BAFU citation.
