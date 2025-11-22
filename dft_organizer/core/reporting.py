import os
from datetime import datetime

from dft_organizer.aiida_utils import extract_uuid_from_path
from dft_organizer.crystal_parser import make_report as make_report_crystal
from dft_organizer.crystal_parser import print_report as print_report_crystal
from dft_organizer.crystal_parser import save_report as save_report_crystal
from dft_organizer.crystal_parser import parse_crystal_output
from dft_organizer.fleur_parser import make_report as make_report_fleur
from dft_organizer.fleur_parser import print_report as print_report_fleur
from dft_organizer.fleur_parser import save_report as save_report_fleur
from dft_organizer.fleur_parser import parse_fleur_output
from dft_organizer.utils import detect_engine, get_table_string

from pathlib import Path
from typing import Any

import pandas as pd

from dft_organizer.aiida_utils import extract_uuid_from_path
from dft_organizer.utils import detect_engine, get_table_string
from dft_organizer.crystal_parser import (
    parse_crystal_output,
    make_report as make_report_crystal,
)
from dft_organizer.fleur_parser import (
    parse_fleur_output,
    make_report as make_report_fleur,
)


def scan_calculations(
    root_dir: Path,
    aiida: bool = False,
    verbose: bool = True,
) -> tuple[list[dict[str, Any]], dict, dict]:
    """
    Go through directory tree, parse outputs and generate error reports.
    """
    root_path = Path(root_dir).resolve()

    summary_store: list[dict[str, Any]] = []
    error_dict_crystal: dict = {}
    error_dict_fleur: dict = {}

    for dirpath, dirnames, filenames in os.walk(root_path, topdown=False):
        current_dir = Path(dirpath)
        if current_dir == root_path:
            continue

        engine = detect_engine(filenames, current_dir)

        if engine == "crystal" and "OUTPUT" in filenames:
            output_path = current_dir / "OUTPUT"
            summary = parse_crystal_output(output_path)
            summary["output_path"] = str(output_path)
            summary["engine"] = "crystal"
            if aiida:
                uuid = extract_uuid_from_path(output_path, root_path)
                summary["uuid"] = uuid
            summary_store.append(summary)
            if verbose:
                print("CRYSTAL OUTPUT FOUND:")
                print(get_table_string(summary))

        elif engine == "fleur" and ("out" in filenames or "out.xml" in filenames):
            output_path = current_dir / ("out.xml" if "out.xml" in filenames else "out")
            summary = parse_fleur_output(output_path)
            summary["output_path"] = str(output_path)
            summary["engine"] = "fleur"
            if aiida:
                uuid = extract_uuid_from_path(output_path, root_path)
                summary["uuid"] = uuid
            summary_store.append(summary)
            if verbose:
                print("FLEUR OUTPUT FOUND:")
                print(get_table_string(summary))

        if engine == "crystal":
            error_dict_crystal = make_report_crystal(
                current_dir, filenames, error_dict_crystal
            )
        elif engine == "fleur":
            error_dict_fleur = make_report_fleur(
                current_dir, filenames, error_dict_fleur
            )

    return summary_store, error_dict_crystal, error_dict_fleur


def find_calculation_by_uuid(root_dir: Path, uuid: str) -> Path:
    """Find calculation directory by UUID in AiiDA structure"""
    root_path = Path(root_dir).resolve()

    if not root_path.exists():
        raise FileNotFoundError(f"Directory does not exist: {root_path}")

    # extract parts from UUID: first 2 chars, next 2 chars, rest
    if len(uuid) < 4:
        raise ValueError(f"UUID too short: {uuid}")

    first_dir = uuid[:2]
    second_dir = uuid[2:4]
    calc_dir = uuid[4:]

    expected_path = root_path / first_dir / second_dir / calc_dir

    if expected_path.exists():
        return expected_path

    for dirpath, dirnames, filenames in os.walk(root_path):
        current_dir = Path(dirpath)
        extracted_uuid = extract_uuid_from_path(current_dir, root_path)

        if extracted_uuid == uuid:
            return current_dir

    raise FileNotFoundError(f"Calculation with UUID {uuid} not found in {root_path}")

def save_reports(
    root_path: Path,
    summary_store: list[dict],
    error_dict_crystal: dict,
    error_dict_fleur: dict,
) -> None:
    time_now = datetime.now().strftime("%Y_%m_%d_%H_%M_%S")

    if summary_store:
        df = pd.DataFrame(summary_store)
        df.to_csv(
            root_path.parent / f"summary_{time_now}.csv",
            index=False,
        )

    if error_dict_fleur:
        print_report_fleur(error_dict_fleur)
        save_report_fleur(
            error_dict_fleur,
            root_path.parent / f"report_fleur_{time_now}.txt",
        )

    if error_dict_crystal:
        print_report_crystal(error_dict_crystal)
        save_report_crystal(
            error_dict_crystal,
            root_path.parent / f"report_crystal_{time_now}.txt",
        )


def generate_report_for_uuid(root_dir: Path, uuid: str) -> dict:
    """Generate report for a specific calculation by UUID"""
    try:
        calc_dir = find_calculation_by_uuid(root_dir, uuid)
        print(f"Found calculation at: {calc_dir}")

        filenames = [f.name for f in calc_dir.iterdir() if f.is_file()]

        error_dict = {}

        engine = detect_engine(filenames, calc_dir)

        if engine == "crystal":
            error_dict = make_report_crystal(str(calc_dir), filenames, {})
            output_file = calc_dir / "OUTPUT"
            parse_output = parse_crystal_output
            print_report = print_report_crystal
            save_report = save_report_crystal
        elif engine == "fleur":
            error_dict = make_report_fleur(str(calc_dir), filenames, {})
            output_file = calc_dir / "out"
            parse_output = parse_fleur_output
            print_report = print_report_fleur
            save_report = save_report_fleur
        else:
            print(f"Unknown engine detected for {calc_dir}")
            return None

        summary = None

        # parse result file if exists
        if output_file.exists():
            summary = parse_output(output_file)
            summary["output_path"] = str(output_file)
            summary["uuid"] = uuid
            summary["engine"] = engine
        else:
            print(f"Output file not found in {calc_dir}")
            summary = {
                "output_path": str(calc_dir),
                "uuid": uuid,
                "engine": engine,
                "error": "Output file not found",
            }

        print("\n" + "=" * 60)
        print(f"CALCULATION REPORT FOR UUID: {uuid}")
        print("=" * 60)

        if "error" not in summary:
            print(get_table_string(summary))

        print("\n--- ERROR REPORT ---")
        print_report(error_dict)
        print("=" * 60)

        root_path = Path(root_dir).resolve()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        if summary:
            summary_file = root_path.parent / f"summary_uuid_{uuid}_{timestamp}.csv"
            df = pd.DataFrame([summary])
            df.to_csv(summary_file, index=False)
            print(f"\nSummary saved to: {summary_file}")

        # save error report
        error_report_file = root_path.parent / f"report_uuid_{uuid}_{timestamp}.txt"
        save_report(error_dict, str(error_report_file))
        print(f"Error report saved to: {error_report_file}")

        return summary

    except FileNotFoundError as e:
        print(f"Error: {e}")
        return None
    except Exception as e:
        print(f"Unexpected error: {e}")
        import traceback

        traceback.print_exc()
        return None


def generate_reports_after_extraction(root_dir: Path, aiida: bool = False) -> None:
    root_path = Path(root_dir).resolve()
    if not root_path.exists():
        print(f"Directory does not exist: {root_path}")
        return

    print("\n" + "=" * 60)
    print("GENERATING REPORTS AFTER EXTRACTION")
    print("=" * 60 + "\n")

    summary_store, err_cr, err_fl = scan_calculations(
        root_path,
        aiida=aiida,
        verbose=True,
    )

    save_reports(
        root_path,
        summary_store,
        err_cr,
        err_fl
    )

    print("\n" + "=" * 60)
    print("REPORTS GENERATION COMPLETE")
    print("=" * 60 + "\n")