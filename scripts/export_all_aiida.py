"""Export ALL AiiDA calculations as MPDS-format 7z archives with report.

Usage:
    python scripts/export_all_aiida.py

Input:
    AiiDA PostgreSQL database (via active AiiDA profile).

Output:
    - <formula>_<spg>_<pearson>.7z archives in export_aiida/
    - Each archive contains ELECTRON/, STRUCT/, TRANSPORT/ subfolders and README.txt
    - Also generates AiiDA summary report (CSV/JSON) alongside archives

Parameters:
    export_all -- export all calculations (no label filter)
    output_dir -- directory for archives and report
    generate_report -- also generate summary CSV/JSON from AiiDA database
"""
from dft_organizer.aiida.export import launch_aiida_export

launch_aiida_export(
    export_all=True,
    output_dir="export_aiida",
    generate_report=True,
)
