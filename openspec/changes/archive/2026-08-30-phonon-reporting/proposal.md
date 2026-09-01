## Why

dft_organizer lacked phonon calculation support: `calc_type` was always `scf`/`optimise`/`properties`, and no thermodynamic properties (ZPE, free energy, entropy, heat capacity) were computed. PR #18 added CRYSTAL phonon parsing but FLEUR phonon support was a no-op stub, and no thermodynamic integration existed.

## What Changes

- Added CRYSTAL phonon frequency parsing from OUTPUT MODES blocks (`crystal_parser/properties/phonon.py`), with columns `has_phonons`, `phonon_freq_min/max/mean/std`, `phonon_n_imag`, `phonon_modes_count`.
- Added `determine_calc_type_summary()` in `aiida/export.py` classifying calc types: `phonon`, `transport`, `elastic`, `electron`, `struct`, `hform`, `optimise`, `scf`.
- Added FLEUR phonon WorkChain enrichment via `phonon_utils.py`: extracts frequencies from `PhonopyFleurWorkChain` force constants using phonopy, integrates thermodynamic properties (ZPE, F, S, Cv) via `ab_initio_calculations.phonon_thermo` (custom/phonopy/ase methods).
- Added standalone `dft-report-phonons` CLI producing CSV/JSON with pk, formula, space group, Pearson symbol, cell parameters, cost, n_imaginary, ZPE, F/S/Cv at t_eval.
- Added Pearson symbol filling via `_pearson_from_attrs()` alongside space group.
- Added `--calc-type`, `--max-duration`, `--skip-displacement`, `--phonon-t-eval`, `--phonon-method`, `--provider`, `--machine-type` CLI flags.
- Added `ab_initio_calculations` as dependency for phonon thermodynamic integration.
- Added `structures.py` with `get_space_group_robust()` and `nullify_right_angles()`.

## Capabilities

### New Capabilities
- `phonon-reporting`: Detect phonon calculations (CRYSTAL + FLEUR), parse/extract frequencies, enrich summary with phonon columns and thermodynamic properties, generate standalone phonon reports.

### Modified Capabilities
<!-- No existing specs modified. -->

## Impact

- **Code**: New files `phonon_utils.py`, `crystal_parser/properties/phonon.py`, `fleur_parser/phonon.py`, `structures.py`, `cli/report_phonons_cli.py`. Modified `aiida/reporting.py`, `aiida/export.py`, `cli/report_aiida_cli.py`, `cli/report_cli.py`, `reporting.py`, `pyproject.toml`.
- **API**: New public callables `scan_phonon_workchains()`, `get_phonon_workchain_summary()`, `generate_aiida_phonon_reports()`, `save_aiida_phonon_reports()`, `determine_calc_type_summary()`.
- **Dependencies**: `ab_initio_calculations` (local editable install) for `phonon_thermo` integration.
- **Systems**: AiiDA database read-only; phonopy required for FLEUR frequency extraction.