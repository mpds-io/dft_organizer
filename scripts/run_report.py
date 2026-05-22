"""Scan local calculation directories and generate summary CSV with error reports.

Usage:
    python scripts/run_report.py

Input:
    Directory tree with CRYSTAL OUTPUT / FLEUR out.xml files.
    AiiDA UUIDs are extracted from path structure if aiida=True.

Output:
    - summary_<timestamp>.csv in /root/projects/dft_organizer/
    - summary_<timestamp>.json in /root/projects/dft_organizer/
    - error reports for CRYSTAL/FLEUR

Parameters:
    root_dir -- root directory containing calculation subdirectories
    aiida -- extract UUID from path structure and enrich with AiiDA data
    skip_errors -- skip entries with parsing errors in the report
    calculation_type -- filter: "all", "optimise", "scf", "properties"
    engine_type -- filter: None (all), "crystal", or "fleur"
    output_dir -- directory for output files
"""
from pathlib import Path
from dft_organizer.reporting import generate_reports_only

generate_reports_only(
    Path("/data/aiida"),
    aiida=True,
    skip_errors=True,
    calculation_type="all",
    engine_type=None,
    output_dir=Path("reports/local"),
) 