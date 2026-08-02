## Why

DFT phonon calculations (CRYSTAL `PHONON.DAT` / `FREQ.DAT`, FLEUR analogues) are currently only archived (`aiida/export.py` recognises `PHONON` calculations and copies files) but never parsed. The summary table (`summary_<ts>.csv`) and reports contain no phonon information — frequencies, mode types, thermodynamic properties. This hampers materials analysis: phonon data is a key materials-informatics descriptor (heat capacity, lattice stability, modes), and users must manually open files. Adding parsing and a dedicated phonon summary table closes this gap and makes the report self-contained.

## What Changes

- Added a new parser for CRYSTAL phonon output files (`PHONON.DAT`, `FREQ.DAT`), extracting key summary metrics: number of branches/modes, frequency range, max/min frequency, presence of imaginary (unstable) modes, heat capacity/entropy at a given T (if available).
- Added a parser for FLEUR phonon outputs (where applicable, e.g. `phonon.*`/`phono*` files), or an explicit graceful marker that the engine does not support phonons — without crashing.
- Added compact phonon summary fields to the main `summary` (`has_phonons`, `phonon_freq_min`, `phonon_freq_max`, `phonon_n_imag`, `phonon_modes_count`) — extending the existing report without breaking current columns.
- Added a **separate** `phonon_summary_<ts>.csv` table with detailed phonon data: Gamma-point frequencies, branches, thermodynamics, source file path, UUID, formula, engine.
- Integrated phonon summary aggregation and separate CSV writing into the existing `dft-report` pipeline via `reporting.scan_calculations` / `save_reports` (no new CLI commands required by default).
- Updated README documentation: new summary columns and the new `phonon_summary_<ts>.csv` file.
- **BREAKING**: none — changes are additive; when phonon files are absent, behaviour is fully preserved.

## Capabilities

### New Capabilities
- `phonon-parsing`: Parse CRYSTAL/FLEUR phonon output files into structured dictionaries (summary + detailed modes/frequencies) and aggregate them across the calculation tree.

### Modified Capabilities
<!-- No existing specs in openspec/specs/, so no modifications. -->

## Impact

- **Code**:
  - New module `dft_organizer/crystal_parser/properties/phonon.py` (parser for `PHONON.DAT`/`FREQ.DAT`).
  - New module `dft_organizer/fleur_parser/phonon.py` (FLEUR phonon parser or stub).
  - Changes in `dft_organizer/reporting.py`: phonon file detection in `scan_calculations`, `phonon_store` collection, `phonon_summary_<ts>.csv` writing in `save_reports`, adding compact fields to the main summary.
  - Changes in `dft_organizer/crystal_parser/__init__.py` and `fleur_parser/__init__.py`: export new parsers.
  - `README.md` update (new CSV fields).
- **API**: New public callable `parse_phonon_output(path, engine)`; extension of `scan_calculations` return (optionally — a third `phonon_store` value) or a separate `scan_phonons(root_dir)` function.
- **Dependencies**: no new external packages required; uses `numpy`/`polars` (already in the project) and the standard library. `phonopy` is NOT added — parsing reads raw CRYSTAL/FLEUR files directly.
- **Systems**: no impact on AiiDA/DB; AiiDA enrichment remains as-is.