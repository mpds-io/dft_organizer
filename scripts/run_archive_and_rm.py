"""Archive a calculation directory tree into a .7z file with report, then remove originals.

Usage:
    python scripts/run_archive_and_rm.py

Input:
    Directory tree with CRYSTAL OUTPUT / FLEUR out.xml files.

Output:
    - <dirname>.7z archive in the parent directory
    - Summary CSV and error reports alongside the archive

Parameters:
    root_dir -- path to the calculation directory to archive
    make_report -- scan and include a summary report before archiving
    aiida -- extract UUID from path structure and enrich with AiiDA data
"""
from pathlib import Path
from dft_organizer.archive import archive_and_save

archive_and_save(
    Path("examples/fleur_data/inputfiles"),
    make_report=True,
    aiida=False,
)