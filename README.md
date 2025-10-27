# DFT organizer

[Alina Zhidkovskaya](https://orcid.org/0009-0003-9305-0030) and [Evgeny Blokhin](https://orcid.org/0000-0002-5333-3947)
Tilde Materials Informatics and Materials Platform for Data Science LLC


## About

`dft-organizer` is a command-line tool to manage data from density functional theory calculations using CRYSTAL and FLEUR engines.

It automates:
- Archiving calculation directories with 7z compression
- Parsing output files to generate detailed error reports and CSV summaries
- Cleaning up original calculation directories after archiving

It also supports unpacking 7z archives and restoring archived calculation directories recursively, with optional AiiDA UUID tracking.


## Installation

Requires Python ≥ 3.11

Dependencies:
- click ≥ 8.1
- pandas
- 7z (command-line tool)

Install via pip:

`pip install .`


## Command-line Interface

### Archive a directory and generate report

```

dft-pack --path <directory_path> [--engine <crystal|fleur>] [--report|--no-report] [--aiida|--no-aiida]

```

- `--path`         Path to the calculation directory
- `--engine`       DFT engine (default: crystal)
- `--report`       Generate error report and summary (default)
- `--no-report`    Skip report generation
- `--aiida`        Extract UUID from AiiDA directory structure
- `--no-aiida`     Do not extract UUID

Creates:

- `<directory_name>.7z`
- `report_<engine>_<timestamp>.txt`
- `summary_<engine>_<timestamp>.csv`

### Unpack an archive and generate reports

```
dft-unpack --path <archive_or_directory_path> [--engine <crystal|fleur>] [--report|--no-report] [--aiida|--no-aiida]
```

- `--path`         Path to a .7z archive or directory with archives
- `--engine`       DFT engine (default: crystal)
- `--report`       Generate summary and error reports after extraction (default)
- `--no-report`    Skip report generation
- `--aiida`        Extract UUID from AiiDA directory structure
- `--no-aiida`     Do not extract UUID

Creates under parent directory:
- `summary_<engine>_extracted_<timestamp>.csv`
- `report_<engine>_extracted_<timestamp>.txt`


## Python API

### Archive a directory and generate an error report

```
from pathlib import Path
from dft_organizer.archiver import archive_and_remove

archive_and_remove(
	Path("./my_calc_dir"),
	engine="crystal",
	make_report=True,
	aiida=True
)
```

### Restore archived .7z files and generate reports

```
from pathlib import Path
from dft_organizer.re_archiver import restore_archives_iterative

restore_archives_iterative(
	Path("./archive_dir.7z"),
	engine="crystal",
	generate_reports=True,
	aiida=True
)
```


## Example Report Command

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

- `bandgap`         Band gap value
- `cpu_time`        CPU time
- `total_energy`    Total energy
- `s_pop`, `p_pop`, `d_pop`  Mulliken populations
- `total_pop`       Total population
- `output_path`     Full path to OUTPUT file
- `uuid`            Calculation UUID (AiiDA mode only)


## Authors

- [Alina Zhidkovskaya](https://orcid.org/0009-0003-9305-0030)
- [Evgeny Blokhin](https://orcid.org/0000-0002-5333-3947)
