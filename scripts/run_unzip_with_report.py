"""Recursively extract .7z archives and generate reports for found calculations.

Usage:
    python scripts/run_unzip_with_report.py

Input:
    Path to a .7z archive or directory. Nested .7z files are extracted iteratively.

Output:
    - Extracted calculation directories
    - Summary CSV and error reports for each level with calculations

Parameters:
    start_path -- path to .7z archive or directory to restore
    generate_reports -- create summary reports after each extraction level
    aiida -- extract UUID from path structure and enrich with AiiDA data
"""
from pathlib import Path
from dft_organizer.core.archive_core import restore_archives_iterative

restore_archives_iterative(
    Path("examples/fleur_data/inputfiles.7z"),
    generate_reports=True,
    aiida=False,
)