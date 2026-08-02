"""Generate summary CSV/JSON/error report from AiiDA database.

Usage:
    python scripts/make_report_aiida_results.py

Input:
    AiiDA PostgreSQL database (via active AiiDA profile).

Output:
    - summary_<timestamp>.csv in reports/aiida_db/
    - summary_<timestamp>.json in reports/aiida_db/
    - error report if any calculations have exit_status != 0

Parameters:
    from_date -- only include calculations created on or after this date (YYYY-MM-DD)
    skip_errors -- skip calculations with parsing errors
    output_dir -- directory for output files
"""
from dft_organizer.aiida.reporting import generate_aiida_reports

generate_aiida_reports(
    from_date=None,
    skip_errors=True,
    output_dir="reports/aiida_db",
)
