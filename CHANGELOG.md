# Changelog

## 0.1.0 (unreleased)

- bw2data mode: `import_bafu_db()` / `sentier-brightway db` installs BAFU-2026 v1, an EF 3.1
  biosphere and the 25 EF 3.1 methods into a Brightway project, relinked through the
  sentier-mappings bridge.
- File mode: `import_bafu_files()` / `sentier-brightway files` writes the same build as a
  parquet registry, the applied randonneur packages and bw_processing datapackages for
  bw2calc without bw2data. `--overwrite` only ever replaces a previous export.
- Pinned, sha256-verified data manifest (`sources.toml`), downloaded on first use; no data in
  the wheel.
- Coverage report (`sentier-brightway coverage`) with the BAFU citation.
- Parity script against BAFU's published EF 3.1 LCIA results (`scripts/parity_bafu_lcia.py`).
