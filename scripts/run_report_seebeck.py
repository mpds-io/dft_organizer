"""Compare Seebeck coefficient values from an AiiDA summary CSV with MPDS reference data.

Usage:
    python scripts/run_report_seebeck.py

Input:
    - Summary CSV with columns: chemical_formula, engine, seebeck_coefficient_uvk,
      mu_ev, temperature_k, calc_date (from dft-report-aiida or make_report_aiida_results.py)
    - MPDS Seebeck CSV directory with columns: phase_id, formula, sg, entry,
      seebeck, temperature

Output:
    - seebeck_comparison_<timestamp>.csv and .json in reports/aiida_db/
"""
from pathlib import Path
from dft_organizer.seebeck_compare import compare_seebeck

compare_seebeck(
    csv_path=Path("/root/projects/dft_organizer/reports/aiida_db/summary_2026_05_18_17_51_44.csv"),
    mpds_dir="/root/projects/ab_initio_calculations/mpds_seebeck_data/",
)