"""Export AiiDA calculations from a given date as 7z archives with report.

Usage:
    python scripts/export_period_aiida.py

Input:
    AiiDA PostgreSQL database (via active AiiDA profile).

Output:
    - <formula>_<spg>_<pearson>.7z archives in export_aiida/
    - Also generates AiiDA summary report (CSV/JSON)

Parameters:
    export_all -- export all calculations matching date filter
    from_date -- only include calculations created on or after this date (YYYY-MM-DD)
    output_dir -- directory for archives and report
    generate_report -- also generate summary CSV/JSON
"""
from dft_organizer.aiida.export import launch_aiida_export

launch_aiida_export(
    export_all=True,
    from_date="2026-05-13",
    output_dir="export_aiida",
    generate_report=True,
)
