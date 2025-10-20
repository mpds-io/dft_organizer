import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

import click
from dft_organizer.crystal_parser.summary import parse_crystal_output
from dft_organizer.fleur_parser.summary import parse_fleur_output
import pandas as pd 
from dft_organizer.utils import detect_engine, get_table_string
from dft_organizer.crystal_parser.error_crystal_parser import (
                    make_report as make_report_crystal,
                    print_report as print_report_crystal,
                    save_report as save_report_crystal,
                )
from dft_organizer.fleur_parser.error_fleur_parser import (
                    make_report as make_report_fleur,
                    print_report as print_report_fleur,
                    save_report as save_report_fleur,
)
from dft_organizer.aiida_utils import extract_uuid_from_path


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


def generate_report_for_uuid(root_dir: Path, uuid: str) -> dict:
    """Generate report for a specific calculation by UUID"""
    try:
        calc_dir = find_calculation_by_uuid(root_dir, uuid)
        print(f"Found calculation at: {calc_dir}")
        
        filenames = [f.name for f in calc_dir.iterdir() if f.is_file()]
        
        error_dict = {}
        
        engine = detect_engine(filenames)
        if engine == "crystal":
            error_dict = make_report_crystal(str(calc_dir), filenames, {})
            output_file = calc_dir / 'OUTPUT'
            parse_output = parse_crystal_output
            print_report = print_report_crystal
            save_report = save_report_crystal
        elif engine == "fleur":
            error_dict = make_report_fleur(str(calc_dir), filenames, {})
            output_file = calc_dir / 'out'
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
            summary['output_path'] = str(output_file)
            summary['uuid'] = uuid
            summary['engine'] = engine
        else:
            print(f"Output file not found in {calc_dir}")
            summary = {
                'output_path': str(calc_dir),
                'uuid': uuid,
                'engine': engine,
                'error': 'Output file not found'
            }
        
        print("\n" + "="*60)
        print(f"CALCULATION REPORT FOR UUID: {uuid}")
        print("="*60)
        
        if 'error' not in summary:
            print(get_table_string(summary))
        
        print("\n--- ERROR REPORT ---")
        print_report(error_dict)
        print("="*60)
        
        root_path = Path(root_dir).resolve()
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
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


def archive_and_remove(
    root_dir: Path, make_report: bool = True, aiida: bool = False
) -> None:
    """Archive directories recursively and remove original files"""
    error_dict_fleur = {}
    error_dict_crystal = {}
    
    summary_store = []
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
            engine = detect_engine(filenames)
            
            if engine == "crystal" and 'OUTPUT' in filenames:
                output_path = current_dir / 'OUTPUT'
                summary = parse_crystal_output(output_path)
                
                summary['output_path'] = str(output_path)
                summary['engine'] = 'crystal'
                
                if aiida:
                    uuid = extract_uuid_from_path(output_path, root_path)
                    summary['uuid'] = uuid
                    
                summary_store.append(summary)
                print('CRYSTAL OUTPUT FOUND:')
                print(get_table_string(summary))
                
            elif engine == "fleur" and 'out' in filenames:
                output_path = current_dir / 'out'
                summary = parse_fleur_output(output_path)
                
                summary['output_path'] = str(output_path)
                summary['engine'] = 'fleur'
                
                if aiida:
                    uuid = extract_uuid_from_path(output_path, root_path)
                    summary['uuid'] = uuid
                
                summary_store.append(summary)
                print('FLEUR OUTPUT FOUND:')
                print(get_table_string(summary))

            if engine == "crystal":
                error_dict_crystal = make_report_crystal(str(current_dir), filenames, error_dict_crystal)
            elif engine == "fleur":
                error_dict_fleur = make_report_fleur(str(current_dir), filenames, error_dict_fleur)
                
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
        time_now = datetime.now().strftime('%Y_%m_%d_%H_%M_%S')
        if error_dict_fleur != {}:
            print_report_fleur(error_dict_fleur)
            print("Error report for FLEUR is ready.")
            save_report_fleur(
                error_dict_fleur,
                str(root_path.parent / f"report_fleur_{time_now}.txt"),
            )
        if error_dict_crystal != {}:
            print_report_crystal(error_dict_crystal)
            print("Error report for CRYSTAL is ready.")
            save_report_crystal(
                error_dict_crystal,
                str(root_path.parent / f"report_crystal_{time_now}.txt"),
            )
        
    if summary_store:
        df = pd.DataFrame(summary_store)
        df.to_csv(
            root_path.parent / f"summary_{datetime.now().strftime('%Y_%m_%d_%H_%M_%S')}.csv",
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


@click.group()
def cli():
    """DFT Organizer - Archive and analyze DFT calculations"""
    pass


@cli.command()
@click.option(
    "--path",
    required=True,
    type=click.Path(exists=True, file_okay=False),
    help="Path to the directory to be archived",
)
@click.option("--report/--no-report", default=True, help="Create error report")
@click.option("--aiida/--no-aiida", default=False, help="AiiDA mode - extract UUID from path")
def archive(path, report, aiida):
    """Archive directory, create report and remove original files."""
    archive_and_remove(Path(path), make_report=report, aiida=aiida)


@cli.command()
@click.option(
    "--path",
    required=True,
    type=click.Path(exists=True, file_okay=False),
    help="Root directory containing calculations",
)
@click.option(
    "--uuid",
    required=True,
    type=str,
    help="UUID of the calculation (e.g., 0ea8a6be-7199-4c3e-9263-fae76e8d081e)",
)
def report(path, uuid):
    """Generate report for a specific calculation by UUID."""
    clean_uuid = uuid.replace('-', '')
    generate_report_for_uuid(Path(path), clean_uuid)


if __name__ == "__main__":
    # cli()
    archive_and_remove(Path("/root/projects/dft_organizer/output_fleur_crystal"))

