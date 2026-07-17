# DFT organizer

This is a command-line tool to manage the data from DFT (density functional theory) calculations using [CRYSTAL](https://www.crystal.unito.it) and [FLEUR](https://www.flapw.de) engines.

It automates:
- archiving calculation directories with 7z compression
- parsing output files to generate detailed error reports and CSV summaries
- cleaning up original calculation directories after archiving

It also supports unpacking 7z archives and restoring archived calculation directories recursively, with optional AiiDA UUID tracking.


## Installation

Requires Python ≥ 3.9 and `7z` command-line tool.

Install via pip: `pip install .`


## Command-line Interface

### Archive a directory and generate a report

dft-pack --path <directory_path> [--report|--no-report] [--aiida|--no-aiida] [--skip-errors|--no-skip-errors]

- `--path`         Path to the calculation directory
- `--report`       Generate error report and summary (default)
- `--no-report`    Skip report generation
- `--aiida`        Extract UUID from AiiDA directory structure
- `--no-aiida`     Do not extract UUID
- `--skip-errors`  Skip calculations with errors to create summary table

Creates:

- `<directory_name>.7z`
- `report_crystal_<timestamp>.txt` and/or `report_fleur_<timestamp>.txt`
- `summary_<timestamp>.csv`


### Unpack an archive and generate reports

dft-unpack --path <archive_or_directory_path> [--report|--no-report] [--aiida|--no-aiida] [--skip-errors|--no-skip-errors]

- `--path`         Path to a .7z archive or directory with archives
- `--report`       Generate summary and error reports after extraction (default)
- `--no-report`    Skip report generation
- `--aiida`        Extract UUID from AiiDA directory structure
- `--no-aiida`     Do not extract UUID
- `--skip-errors`  Skip calculations with errors to create summary table

Creates under parent directory:
- `summary_<timestamp>.csv`
- `report_crystal_<timestamp>.txt`
- `report_fleur_<timestamp>.txt`

Example:
`dft-report --path /data/aiida_data --aiida --skip-errors`


### Generate reports without archiving

dft-report --path <directory_path> [--aiida|--no-aiida] [--skip-errors|--no-skip-errors] [--calc-type TYPE]

- `--path`         Root directory containing calculations
- `--aiida`        Extract UUID from AiiDA directory structure
- `--no-aiida`     Do not extract UUID
- `--skip-errors`  Skip calculations with errors to create summary table
- `--calc-type`    Filter by calculation type: `scf`, `optimise`, `phonon`, `transport`, `elastic`, `electron`, `properties`, or `all` (default). For CRYSTAL, `phonon`/`transport`/`elastic`/`electron` are detected from sibling files (`SEEBECK.DAT`, `PHONON.DAT`/`FREQ.DAT`, `ELASTIC.DAT`, `BAND.DAT`/`DOSS.DAT`) or keywords in the OUTPUT file.

Creates under parent directory:
- `summary_<timestamp>.csv`
- `report_crystal_<timestamp>.txt`
- `report_fleur_<timestamp>.txt`


### Generate reports from AiiDA database (no archiving)

dft-report-aiida [--label LABEL] [--from-date YYYY-MM-DD] [--to-date YYYY-MM-DD] [--calc-type TYPE] [--skip-errors] [--output-dir DIR]

- `--label`        Filter by calculation label (exact match)
- `--from-date`    Only include calculations created on or after this date
- `--to-date`      Only include calculations created on or before this date
- `--calc-type`    Only include calculations of this type, e.g. `phonon`, `transport`, `elastic`, `electron`, `optimise`, `scf`, `struct`, `hform`. Filtering is applied after enrichment (so `scf` rows reclassified to `transport` via `SEEBECK.DAT` are kept by `--calc-type transport`).
- `--skip-errors`  Skip calculations with exit_status != 0
- `--output-dir`   Directory to save reports (default `/tmp`)

Creates:
- `summary_<timestamp>.csv`
- `summary_<timestamp>.json`
- `report_crystal_<timestamp>.txt` / `report_fleur_<timestamp>.txt` (only if errors found)


## Python API

### Archive a directory and generate an error report, skip errors

```
from pathlib import Path
from dft_organizer.core import archive_and_save

archive_and_save(
	Path("./my_calc_dir"),
	engine="crystal",
	make_report=True,
	aiida=True,
	skip_errors=True
)
```

### Restore archived .7z files and generate reports, without errors omission

```
from pathlib import Path
from dft_organizer.core import restore_archives_iterative

restore_archives_iterative(
	Path("./archive_dir.7z"),
	engine="crystal",
	generate_reports=True,
	aiida=True,
	skip_errors=False
)
```

### Generate summary for all calculations, skip errors

```
from dft_organizer.core import generate_reports_only
from pathlib import Path

generate_reports_only(Path("/data/aiida"), aiida=True, skip_errors=True)

```


## Example Report Command by AIIDA UUID

Generate report for a specific calculation UUID:

```
dft-pack report \
--path aiida_playground_data \
--uuid 0ea8a6be-7199-4c3e-9263-fae76e8d081e \
--engine crystal
```

Output files:
- `summary_uuid_<uuid>_<timestamp>.csv`
- `errors_uuid_<uuid>_<timestamp>.txt`


## CSV Summary Fields

- `total_energy`        Total energy in eV (from CRYSTAL `energy`).
- `energy_hartree`      Total energy converted to Hartree (`total_energy / 27.2114`).
- `bandgap`             Band gap value from the last conduction entry (if available).
- `duration`            Calculation wall-clock time (if reported by CRYSTAL).
- `a`, `b`, `c`         Lattice parameters in Å for the final structure.
- `alpha`, `beta`, `gamma`  Lattice angles in degrees for the final structure.
- `chemical_formula`    Reduced chemical formula of the final structure (from ASE).
- `sum_sq_disp`         Sum of squared atomic displacements between first and last structure.
- `rmsd_disp`           Root-mean-square displacement between first and last structure.
- `output_path`         Full path to the main OUTPUT file for this calculation.
- `uuid`                Calculation UUID (only in AiiDA mode, extracted from directory layout).
- `calc_type`           Calculation type: `scf`, `optimise`, `phonon`, `transport`, `electron`, `elastic`, `struct`, `hform`. In AiiDA-DB mode, `scf` rows whose retrieved repository contains `SEEBECK.DAT` are reclassified as `transport`.
- `has_phonons`         True when CRYSTAL phonon frequencies were parsed (AiiDA-DB mode, `calc_type == 'phonon'`).
- `phonon_freq_min`     Minimum phonon frequency in THz across all q-points.
- `phonon_freq_max`     Maximum phonon frequency in THz across all q-points.
- `phonon_n_imag`       Number of imaginary (unstable) phonon modes (THz < -1e-3).
- `phonon_modes_count`  Number of modes at the first q-point.
- `seebeck_coefficient_uvk`  Average Seebeck coefficient in µV/K. For CRYSTAL, parsed from `SEEBECK.DAT` (transport calcs); for FLEUR, from `FleurDOSLocalWorkChain` outputs.
- `mu_ev`               Chemical potential. For CRYSTAL, in Hartree (from `SEEBECK.DAT`); for FLEUR, in eV. Note: units differ between engines.
- `temperature_k`       Temperature in Kelvin at which Seebeck was computed.


## License

MIT

&copy; [Alina Zhidkovskaya](https://orcid.org/0009-0003-9305-0030) and [Evgeny Blokhin](https://orcid.org/0000-0002-5333-3947), Materials Platform for Data Science OÜ
