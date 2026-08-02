## ADDED Requirements

### Requirement: FLEUR Seebeck data populated via correct node attribute access
The system SHALL extract `seebeck_coefficient_uvk`, `mu_ev`, and `temperature_k` for FLEUR DOS calculations by reading `.base.attributes.all` on the `output_seebeck` and `output_dos_local_wc_para` nodes of `FleurDOSLocalWorkChain`, NOT via `.get_dict()` (which fails on the custom `data.pythonjob.builtins.dict.Dict` node type).

The Seebeck coefficient values SHALL be stored directly in μV/K without any additional multiplication (FLEUR values are already in μV/K, unlike CRYSTAL where `avg_s * 1e6` is applied).

#### Scenario: FLEUR DOS calc with Seebeck output
- **WHEN** a FLEUR CalcJobNode has a caller `FleurDOSLocalWorkChain` with `output_seebeck` and `output_dos_local_wc_para` output ports populated
- **THEN** the summary row has `seebeck_coefficient_uvk`, `mu_ev`, and `temperature_k` populated from those nodes' attributes

#### Scenario: FLEUR calc without Seebeck
- **WHEN** a FLEUR CalcJobNode has no `FleurDOSLocalWorkChain` caller or the output ports are missing
- **THEN** the summary row has `seebeck_coefficient_uvk`, `mu_ev`, `temperature_k` set to `None`

### Requirement: FLEUR output_parameters read into summary
The system SHALL read `calc.outputs.output_parameters.base.attributes.all` for each `fleur.fleur` CalcJobNode and populate the following summary fields:
- `bandgap` — band gap in eV (no conversion needed)
- `total_energy` — total energy in eV (from the `energy` attribute)
- `fermi_energy` — Fermi energy in eV, converted from Hartree via `* 27.2114`
- `magnetic_moment` — magnetic moment in μB, computed as `abs(spin_dependent_charge_total[0] - spin_dependent_charge_total[1])`
- `n_iterations` — total SCF iteration count (from `number_of_iterations_total`)

Calcs without `output_parameters` (e.g. failed calcs, `fleur.inpgen`) SHALL have these fields set to `None`.

#### Scenario: FLEUR SCF calc with output_parameters
- **WHEN** a `fleur.fleur` CalcJobNode has `exit_status == 0` and an `output_parameters` output port
- **THEN** the summary row has `bandgap`, `total_energy`, `fermi_energy`, `magnetic_moment`, and `n_iterations` populated

#### Scenario: FLEUR calc without output_parameters
- **WHEN** a FLEUR CalcJobNode has no `output_parameters` output (e.g. failed calc)
- **THEN** `bandgap`, `total_energy`, `fermi_energy`, `magnetic_moment`, `n_iterations` are `None`

### Requirement: fleur.inpgen calculations excluded from summary
The system SHALL exclude `fleur.inpgen` CalcJobNodes (input generator, no calculation results) from the summary by checking `process_type` after the database query and skipping any node whose `process_type` contains `inpgen`.

#### Scenario: inpgen excluded
- **WHEN** the AiiDA database contains 2204 `fleur.inpgen` CalcJobNodes and 2363 `fleur.fleur` CalcJobNodes
- **THEN** the summary contains only `fleur.fleur` rows; no `fleur.inpgen` rows appear in the CSV

### Requirement: New CSV columns for FLEUR results
The summary CSV SHALL include columns `total_energy`, `fermi_energy`, `magnetic_moment`, `n_iterations` (in that order, after `bandgap`). These columns SHALL be initialized to `None` for all engines via `_null_summary_keys`.

#### Scenario: CSV schema
- **WHEN** `save_aiida_reports` writes the CSV
- **THEN** the columns include `total_energy`, `fermi_energy`, `magnetic_moment`, `n_iterations` after `bandgap` and before `has_phonons`
- **AND** CRYSTAL rows have `None` in these columns (unless populated by other enrichment)
- **AND** FLEUR rows have values where `output_parameters` was available