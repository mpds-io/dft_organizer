import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

import click
from dft_organizer.crystal_parser.summary import parse_content, get_crystal_table_string
import pandas as pd


def compress_with_7z(source_dir: Path, archive_path: Path) -> bool:
    """Compress directory using 7z without storing parent paths"""
    try:
        cmd = [
            "7z",
            "a",
            "-t7z",
            "-mx=9",
            "-m0=LZMA2",
            "-mmt=on",
            "-spf",
            str(archive_path),
            source_dir.name,
        ]

        print(f"Archiving {source_dir} to {archive_path}...")
        result = subprocess.run(
            cmd, 
            check=True, 
            capture_output=True, 
            text=True,
            cwd=str(source_dir.parent)
        )
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error archiving {source_dir}: {e}")
        print(f"Output: {e.stderr if hasattr(e, 'stderr') else ''}")
        return False


def archive_and_remove(
    root_dir: Path, engine: str = "crystal", make_report: bool = True, aiida: bool = False
) -> None:
    """Archive directories recursively and remove original files"""
    summary_store = []
    
    if make_report:
        error_dict = {}
        if engine == "crystal":
            from dft_organizer.crystal_parser.error_crystal_parser import (
                make_report,
                print_report,
                save_report,
            )
        elif engine == "fleur":
            from dft_organizer.fleur_parser.error_fleur_parser import (
                make_report,
                print_report,
                save_report,
            )
        else:
            raise NotImplementedError(
                f"Engine {engine} is not implemented for reporting errors."
            )

    root_path = Path(root_dir).resolve()

    if not root_path.exists():
        print(f"Directory does not exist: {root_path}")
        return

    dirs_to_process = []
    
    for dirpath, dirnames, filenames in os.walk(root_path, topdown=False):
        current_dir = Path(dirpath)
        
        if current_dir == root_path:
            continue
            
        dirs_to_process.append((current_dir, dirnames, filenames))

    for current_dir, dirnames, filenames in dirs_to_process:
        if make_report:
            error_dict = make_report(str(current_dir), filenames, error_dict)
            
            if 'OUTPUT' in filenames:
                summary = parse_content(current_dir / 'OUTPUT')
                summary_store.append(summary)
                print(get_crystal_table_string(summary))

        if not any(current_dir.iterdir()):
            print(f"Skipping empty directory: {current_dir}")
            continue

        archive_name = f"{current_dir.name}.7z"
        archive_path = current_dir.parent / archive_name

        if compress_with_7z(current_dir, archive_path):
            print(f"Removing original directory: {current_dir}")
            shutil.rmtree(current_dir)
        else:
            print(f"Failed to archive: {current_dir}")

    if make_report:
        print_report(error_dict)
        print("Error report is ready.")
        save_report(
            error_dict,
            str(root_path.parent / f"report_{engine}_{datetime.now().strftime('%Y_%m_%d_%H_%M_%S')}.txt"),
        )
    
    if summary_store:
        df = pd.DataFrame(summary_store)
        df.to_csv(
            root_path.parent / f"summary_{engine}_{datetime.now().strftime('%Y_%m_%d_%H_%M_%S')}.csv",
            index=False
        )

    print(f"\n=== Archiving root directory {root_path.name} ===")
    root_archive_name = f"{root_path.name}.7z"
    root_archive_path = root_path.parent / root_archive_name
    
    if compress_with_7z(root_path, root_archive_path):
        print(f"Removing root directory: {root_path}")
        shutil.rmtree(root_path)
        print(f"Done! Archive created: {root_archive_path}")
    else:
        print(f"Failed to archive root directory: {root_path}")
    
    return df if summary_store else None


@click.command()
@click.option(
    "--path",
    required=True,
    type=click.Path(exists=True, file_okay=False),
    help="Path to the directory to be archived",
)
@click.option(
    "--engine",
    default="crystal",
    help="Engine name for error parsing. Default is 'crystal'.",
)
@click.option("--report/--no-report", default=True, help="Create error report")
@click.option("--aiida/--no-aiida", default=False, help="AiiDA mode")
def cli(path, engine, report, aiida):
    """Archive directory, create report and remove original files."""
    archive_and_remove(Path(path), engine, make_report=report, aiida=aiida)


if __name__ == "__main__":
    archive_and_remove('aiida_playground_data', engine='crystal', make_report=True, aiida=True)
