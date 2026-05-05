import json
import os
from pathlib import Path
from typing import Optional

import polars as pl

from dft_organizer.core import scan_calculations, save_reports
from dft_organizer.core import compress_with_7z, extract_7z
from dft_organizer.core import generate_reports_only


def _serialize_nested(v):
    if v is None:
        return ""
    return json.dumps(v)


def archive_and_save(
    root_dir: Path,
    make_report: bool = True,
    aiida: bool = False,
    skip_errors: bool = False
) -> Optional[pl.DataFrame]:
    """
    Archive directory, create report
    """
    root_path = Path(root_dir).resolve()
    if not root_path.exists():
        print(f"Directory does not exist: {root_path}")
        return None

    summary_store = []
    error_dict_crystal = {}
    error_dict_fleur = {}

    if make_report:
        summary_store, error_dict_crystal, error_dict_fleur = scan_calculations(
            root_path,
            aiida=aiida,
            verbose=True,
            skip_errors=skip_errors
        )
        save_reports(root_path, summary_store, error_dict_crystal, error_dict_fleur)

    root_archive_path = root_path.parent / f"{root_path.name}.7z"
    if compress_with_7z(root_path, root_archive_path):
        print(f"Done! Archive created: {root_archive_path}")
    else:
        print(f"Failed to archive root directory: {root_path}")

     # safe df creation
    if summary_store:
        nested_keys = ["cell", "positions", "pbc", "numbers", "symbols"]
        flat_summary = []
        for row in summary_store:
            try:
                row = dict(row)
                for k in nested_keys:
                    if k in row:
                        try:
                            row[k] = _serialize_nested(row[k])
                        except Exception:
                            row[k] = None
                flat_summary.append(row)
            except Exception:
                continue

        if flat_summary:
            try:
                return pl.DataFrame(flat_summary)
            except Exception:
                return None

    return None


def restore_archives_iterative(
    start_path: Path, generate_reports: bool = True, aiida: bool = False, skip_errors: bool = False
):
    """Iteratively restore archives level by level"""
    start_path = Path(start_path)
    extracted_root = None

    if start_path.is_file() and start_path.suffix == ".7z":
        print(f"=== Extracting root archive {start_path.name} ===")

        target_dir = start_path.parent

        if extract_7z(start_path, target_dir):
            archive_name = start_path.stem
            start_path.unlink()

            extracted_dir = target_dir / archive_name

            if not extracted_dir.exists():
                print(f"Extracted directory not found: {extracted_dir}")
                return

            extracted_root = extracted_dir
            start_path = extracted_dir
        else:
            print("Failed to extract root archive")
            return

    if not start_path.is_dir():
        print(f"Path {start_path} is not a directory")
        return

    # if no root was extracted, use provided directory as root
    if extracted_root is None:
        extracted_root = start_path

    iteration = 0
    while True:
        iteration += 1
        print(f"\n--- Iteration {iteration} ---")

        archives = list(start_path.glob("**/*.7z"))

        if not archives:
            print("✓ No more archives found. Done!")
            break

        print(f"Found archives: {len(archives)}")

        for archive_path in archives:
            target_dir = archive_path.parent

            print(f"  Extracting: {archive_path.relative_to(start_path)}")

            if extract_7z(archive_path, target_dir):
                archive_path.unlink()
            else:
                print(f"  Skipping: failed to extract {archive_path}")

    # generate reports after all extraction is complete
    if generate_reports:
        generate_reports_only(extracted_root, aiida, skip_errors)
