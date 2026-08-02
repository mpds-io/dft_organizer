## Why

The AiiDA-DB summary CSV (`dft-report-aiida`) contained no usable FLEUR calculation results: `bandgap` was never populated (column dropped as all-null), `seebeck_coefficient_uvk` / `mu_ev` / `temperature_k` were always null for FLEUR due to a `.get_dict()` bug on a custom node type, and `fleur.inpgen` input-generator calculations (2204 nodes with no results) cluttered the report with null rows. Meanwhile, the local-filesystem scan (`dft-report`) already parsed `bandgap` from `out.xml` via `parse_fleur_output` — the AiiDA-DB path simply never read the equivalent `output_parameters` output port.

## What Changes

- Fixed the Seebeck bug in `_fetch_fleur_seebeck` (`dft_organizer/aiida/reporting.py` and `dft_organizer/reporting.py`): replaced `.get_dict()` (which raises `AttributeError` on the custom `data.pythonjob.builtins.dict.Dict` node type) with `.base.attributes.all`. Seebeck data is now correctly populated for FLEUR DOS calculations.
- Added reading of `output_parameters` attributes in `_enrich_fleur_extras` for each `fleur.fleur` CalcJobNode, populating: `bandgap` (eV), `total_energy` (eV), `fermi_energy` (eV, converted from Hartree), `magnetic_moment` (μB, from `spin_dependent_charge_total`), `n_iterations` (from `number_of_iterations_total`).
- Added filtering of `fleur.inpgen` CalcJobNodes (input generator with no calculation results) from the AiiDA-DB scan.
- Added four new columns to the summary CSV: `total_energy`, `fermi_energy`, `magnetic_moment`, `n_iterations` (also initialized to `None` for CRYSTAL and other engines via `_null_summary_keys`).
- Updated README documentation with the new FLEUR-specific fields and their units.
- **BREAKING**: none — changes are additive; FLEUR rows that previously had null result fields now have values, and `inpgen` rows are removed (they had no useful data anyway).

## Capabilities

### New Capabilities
- `fleur-result-parsing`: Extract FLEUR calculation results (bandgap, total energy, Fermi energy, magnetic moment, iteration count, Seebeck coefficient) from the AiiDA `output_parameters` output port and `FleurDOSLocalWorkChain` outputs into the summary CSV.

### Modified Capabilities
- `phonon-parsing` (archived): the `_null_summary_keys` and `_SUMMARY_CSV_COLUMNS` lists are extended with the four new FLEUR fields; the column order in the CSV changes (new columns inserted after `bandgap`).

## Impact

- **Code**:
  - `dft_organizer/aiida/reporting.py`: fixed `_fetch_fleur_seebeck` (lines 37–53); added `output_parameters` reading block in `_enrich_fleur_extras` (lines 704–742); added `inpgen` post-query skip (line ~365); added `total_energy`, `fermi_energy`, `magnetic_moment`, `n_iterations` to `_null_summary_keys` and `_SUMMARY_CSV_COLUMNS`.
  - `dft_organizer/reporting.py`: fixed duplicate `_fetch_fleur_seebeck` (line 134–135).
  - `README.md`: documented new fields.
- **API**: No new public callables; `generate_aiida_reports` / `scan_aiida_calculations` signatures unchanged. The CSV schema gains 4 columns (additive).
- **Dependencies**: no new packages.
- **Systems**: AiiDA database read-only; `output_parameters` accessed via `.base.attributes.all` (no plugin-specific API).