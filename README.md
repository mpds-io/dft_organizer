# dft-organizer

[Alina Zhidkovskaya](https://orcid.org/0009-0003-9305-0030) and [Evgeny Blokhin](https://orcid.org/0000-0002-5333-3947)
<br />
Tilde Materials Informatics and Materials Platform for Data Science LLC

---

## Project Description

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
