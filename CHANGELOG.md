# Changelog

## 0.1.0 (unreleased)

- README opens with an architecture schema (Mermaid): Activity Browser, the two importers, and
  the three Sentier data repositories they pull from.
- Backtest module (`sentier_brightway.backtest`) and `sentier-brightway backtest` CLI: all
  11,947 processes x 25 EF 3.1 categories from the file-mode datapackages by adjoint solve,
  cross-checked against the plain bw2calc loop, compared with BAFU's published openLCA
  results per the table's unit.
- Dashboard (`dashboard/backtest_dashboard.html`, a copy of the sentier-agribalyse-4.0 page
  with 25 categories and no drill-down) fed by the backtest's CSV and meta files.
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
