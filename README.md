# dft-organizer

[Alina Zhidkovskaya](https://orcid.org/0009-0003-9305-0030) and [Evgeny Blokhin](https://orcid.org/0000-0002-5333-3947)
<br />
Tilde Materials Informatics and Materials Platform for Data Science LLC

---

## About

`dft-organizer` is a command-line tool designed to manage data from DFT (Density Functional Theory) calculations performed with the Crystal engine (also implies FLEUR support).  
It automates archiving of calculation directories and generates detailed error reports by parsing Crystal output files.  
The original calculation files are archived after report generation to keep your workspace clean and organized.

The tool also supports unpacking 7z archives and restoring archived calculation directories recursively.

---

## Installation

Requires Python >= 3.11  
Dependencies: 
`click>=8.1`

Install via pip:

```bash
pip install .
```

## Command-line Interface

### Archive a directory and make report

```bash
dft-pack --path <directory_path> [--engine <engine_name>] [--report / --no-report]
```

### Unpack an archive 
```bash
dft-unpack --path <archive_or_directory_path>
```

## Python API

In addition to the command-line interface, `dft-organizer` provides a Python API for integration into custom scripts and workflows.

### Example: Archive a directory and generate an error report

```python
from pathlib import Path
from dft_organizer.archiver import archive_and_remove

archive_and_remove(Path("./my_calc_dir"), engine="crystal", make_report=True)
```

### Example: Restore archived .7z files

```python
from pathlib import Path
from dft_organizer.re_archiver import restore_archives_recursive

restore_archives_recursive(Path("./archive_dir"))
```

