import os
import shutil
import pandas as pd

from pathlib import Path
import os
import shutil

from dft_organizer.core.reporting import scan_calculations, save_reports
from dft_organizer.core.sevenzip import compress_with_7z, extract_7z
from dft_organizer.core.reporting import generate_reports_only


def archive_and_remove(
    root_dir: Path,
    make_report: bool = True,
    aiida: bool = False,
):
    """
    Archive directory, create report and remove original files.
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
        )
        save_reports(root_path, summary_store, error_dict_crystal, error_dict_fleur)

    dirs_to_process: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root_path, topdown=False):
        current_dir = Path(dirpath)
        if current_dir == root_path:
            continue
        dirs_to_process.append(current_dir)

    for current_dir in dirs_to_process:
        if not any(current_dir.iterdir()):
            print(f"Skipping empty directory: {current_dir}")
            continue

        archive_path = current_dir.parent / f"{current_dir.name}.7z"
        if compress_with_7z(current_dir, archive_path):
            print(f"Removing original directory: {current_dir}")
            shutil.rmtree(current_dir)
        else:
            print(f"Failed to archive: {current_dir}")

    root_archive_path = root_path.parent / f"{root_path.name}.7z"
    if compress_with_7z(root_path, root_archive_path):
        print(f"Removing root directory: {root_path}")
        shutil.rmtree(root_path)
        print(f"Done! Archive created: {root_archive_path}")
    else:
        print(f"Failed to archive root directory: {root_path}")

    return pd.DataFrame(summary_store) if summary_store else None


def restore_archives_iterative(
    start_path: Path, generate_reports: bool = True, aiida: bool = False
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
        generate_reports_only(extracted_root, aiida)
