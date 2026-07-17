## ADDED Requirements

### Requirement: Parse CRYSTAL phonon output files
The system SHALL parse CRYSTAL phonon output files (`PHONON.DAT`, `FREQ.DAT`) into a structured dictionary containing a flat summary and detailed per-mode frequency records.

#### Scenario: PHONON.DAT present and parseable
- **WHEN** a calculation directory contains a `PHONON.DAT` file with valid CRYSTAL phonon data
- **THEN** `parse_phonon_output(path, engine="crystal")` returns a dict with `has_phonons=True`, `phonon_freq_min`, `phonon_freq_max`, `phonon_n_imag`, `phonon_modes_count`, and a `details` list of per-mode records including `frequency_thz` and `is_imaginary`

#### Scenario: FREQ.DAT present as fallback
- **WHEN** the directory contains `FREQ.DAT` but not `PHONON.DAT`
- **THEN** the system SHALL parse `FREQ.DAT` using the same output structure

#### Scenario: No phonon files present
- **WHEN** neither `PHONON.DAT` nor `FREQ.DAT` is present in the directory
- **THEN** `parse_phonon_output` returns `None` and the summary gets `has_phonons=False` with `phonon_*` fields set to `None`

### Requirement: Normalize phonon frequencies to THz
The system SHALL normalize all parsed phonon frequencies to THz and record the unit in the output. Frequencies below `-IMAG_THRESHOLD_THZ` (1e-3 THz) SHALL be classified as imaginary (unstable modes).

#### Scenario: Frequencies given in cm-1
- **WHEN** the source file stores frequencies in cm⁻¹
- **THEN** the parser converts each frequency to THz (1 cm⁻¹ ≈ 0.02998 THz) and exposes `frequency_unit="THz"`

#### Scenario: Imaginary mode detection
- **WHEN** a mode has frequency below `-1e-3` THz
- **THEN** `is_imaginary=True` for that mode and `phonon_n_imag` is incremented

### Requirement: Parse FLEUR phonon output when available
The system SHALL attempt to parse FLEUR phonon output files; when the format is unsupported or files are absent, it SHALL return `None` without raising an error (graceful no-op).

#### Scenario: FLEUR phonon file absent
- **WHEN** engine is "fleur" and no recognized phonon output file is present
- **THEN** `parse_phonon_output(path, engine="fleur")` returns `None` and `has_phonons=False` is set in the summary

#### Scenario: FLEUR phonon file recognized
- **WHEN** engine is "fleur" and a recognized phonon output file is present
- **THEN** the parser returns a dict with the same summary shape as the CRYSTAL parser

### Requirement: Detect phonon files during scan
`scan_calculations` SHALL detect phonon output files for each calculation directory and invoke `parse_phonon_output` to populate compact phonon fields in the main summary and collect detailed records in a separate `phonon_store`.

#### Scenario: Phonon files detected in a CRYSTAL calculation
- **WHEN** scanning a CRYSTAL calculation directory containing `PHONON.DAT`
- **THEN** the corresponding `summary` entry contains `has_phonons=True`, `phonon_freq_min`, `phonon_freq_max`, `phonon_n_imag`, `phonon_modes_count`, and the detailed records are appended to `phonon_store`

#### Scenario: No phonon files in directory
- **WHEN** a calculation directory has no phonon files
- **THEN** the summary entry gets `has_phonons=False` and `phonon_*` fields set to `None`, and nothing is appended to `phonon_store`

### Requirement: Return phonon store from scan_calculations
`scan_calculations` SHALL return a 4-tuple `(summary_store, error_dict_crystal, error_dict_fleur, phonon_store)` where `phonon_store` is a list of detailed phonon records.

#### Scenario: Callers unpack four values
- **WHEN** `scan_calculations` is called
- **THEN** all internal callers (`generate_reports_only`, AiiDA reporting) unpack four values

### Requirement: Write phonon_summary CSV
`save_reports` SHALL write a separate `phonon_summary_<timestamp>.csv` file when `phonon_store` is non-empty, alongside the existing `summary_<timestamp>.csv`.

#### Scenario: Phonon records exist
- **WHEN** `phonon_store` is non-empty at save time
- **THEN** `save_reports` writes `phonon_summary_<ts>.csv` (via polars) containing fields: `uuid`, `engine`, `chemical_formula`, `output_path`, `q_point`, `branch_index`, `frequency_thz`, `is_imaginary`, `temperature_k`, `modes_count`

#### Scenario: No phonon records
- **WHEN** `phonon_store` is empty
- **THEN** no `phonon_summary_<ts>.csv` file is written and behavior matches the previous pipeline

### Requirement: Preserve backward compatibility of summary CSV
The main `summary_<ts>.csv` SHALL keep all existing columns unchanged and only add the five new phonon fields (`has_phonons`, `phonon_freq_min`, `phonon_freq_max`, `phonon_n_imag`, `phonon_modes_count`) when phonon data is available; otherwise these fields are absent or `None`.

#### Scenario: Directory with no phonons
- **WHEN** no calculation in the scanned tree has phonon files
- **THEN** the main summary CSV columns are identical to the previous behavior (new phonon fields are `None`)

### Requirement: Export parse_phonon_output from parser packages
The `dft_organizer.crystal_parser` and `dft_organizer.fleur_parser` packages SHALL export `parse_phonon_output` so it can be imported directly.

#### Scenario: Import from crystal_parser
- **WHEN** a caller does `from dft_organizer.crystal_parser import parse_phonon_output`
- **THEN** the function is available and parses CRYSTAL phonon files

#### Scenario: Import from fleur_parser
- **WHEN** a caller does `from dft_organizer.fleur_parser import parse_phonon_output`
- **THEN** the function is available and parses (or no-ops) FLEUR phonon files