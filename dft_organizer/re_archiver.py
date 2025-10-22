import os
import subprocess
from datetime import datetime
from pathlib import Path

import click
import pandas as pd

from dft_organizer.crystal_parser.error_crystal_parser import \
    make_report as make_report_crystal
from dft_organizer.crystal_parser.error_crystal_parser import \
    print_report as print_report_crystal
from dft_organizer.crystal_parser.error_crystal_parser import \
    save_report as save_report_crystal
from dft_organizer.crystal_parser.summary import parse_crystal_output
from dft_organizer.fleur_parser.error_fleur_parser import \
    make_report as make_report_fleur
from dft_organizer.fleur_parser.error_fleur_parser import \
    print_report as print_report_fleur
from dft_organizer.fleur_parser.error_fleur_parser import \
    save_report as save_report_fleur
from dft_organizer.fleur_parser.summary import parse_fleur_output
from dft_organizer.utils import detect_engine, get_table_string


def extract_7z(archive_path, target_dir):
    """Unpack 7z archive to target dir"""
    try:
        cmd = [
            "7z",
            "x",
            f"-o{target_dir}",
            "-y",
            str(archive_path),
        ]
        print(f"Extracting {archive_path}...")
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error extracting {archive_path}: {e}")
        return False


def extract_uuid_from_path(output_path: Path, root_path: Path) -> str:
    """Extract UUID from AiiDA path structure"""
    try:
        relative_path = output_path.relative_to(root_path)
        parts = relative_path.parts
        
        if len(parts) >= 3:
            first_part = parts[0]
            second_part = parts[1]
            third_part = parts[2]
            
            uuid = f"{first_part}{second_part}{third_part}"
            return uuid
        
        return ""
    except (ValueError, IndexError):
        return ""


def generate_reports_after_extraction(root_dir: Path, aiida: bool = False):
    """Generate summary and error reports after extraction"""
    root_path = Path(root_dir).resolve()
    
    if not root_path.exists():
        print(f"Directory does not exist: {root_path}")
        return
    
    print(f"\n{'='*60}")
    print("GENERATING REPORTS AFTER EXTRACTION")
    print(f"{'='*60}\n")
    
    summary_store = []
    error_dict_crystal = {}
    error_dict_fleur = {}
    
    # walk through all directories
    for dirpath, dirnames, filenames in os.walk(root_path):
        current_dir = Path(dirpath)
        
        # detect engine for current directory
        engine = detect_engine(filenames)
        
        # check for errors based on detected engine
        if engine == "crystal":
            error_dict_crystal = make_report_crystal(str(current_dir), filenames, error_dict_crystal)
        elif engine == "fleur":
            error_dict_fleur = make_report_fleur(str(current_dir), filenames, error_dict_fleur)
        
        # parse output files based on detected engine
        if engine == "crystal" and 'OUTPUT' in filenames:
            output_path = current_dir / 'OUTPUT'
            
            try:
                summary = parse_crystal_output(output_path)
                summary['output_path'] = str(output_path)
                summary['engine'] = 'crystal'
                
                if aiida:
                    uuid = extract_uuid_from_path(output_path, root_path)
                    summary['uuid'] = uuid
                
                summary_store.append(summary)
                print(f"Processed CRYSTAL: {output_path.relative_to(root_path)}")
                print(get_table_string(summary))
                
            except Exception as e:
                print(f"Error processing {output_path}: {e}")
        
        elif engine == "fleur" and 'out' in filenames:
            output_path = current_dir / 'out'
            
            try:
                summary = parse_fleur_output(output_path)
                summary['output_path'] = str(output_path)
                summary['engine'] = 'fleur'
                
                if aiida:
                    uuid = extract_uuid_from_path(output_path, root_path)
                    summary['uuid'] = uuid
                
                summary_store.append(summary)
                print(f"Processed FLEUR: {output_path.relative_to(root_path)}")
                print(get_table_string(summary))
                
            except Exception as e:
                print(f"Error processing {output_path}: {e}")
    
    # save error reports for both engines
    time_now = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    if error_dict_crystal:
        print(f"\n{'='*60}")
        print("ERROR REPORT - CRYSTAL")
        print(f"{'='*60}")
        print_report_crystal(error_dict_crystal)
        
        error_report_file = root_path.parent / f"report_crystal_extracted_{time_now}.txt"
        save_report_crystal(error_dict_crystal, str(error_report_file))
        print(f"\nCRYSTAL error report saved to: {error_report_file}")
    
    if error_dict_fleur:
        print(f"\n{'='*60}")
        print("ERROR REPORT - FLEUR")
        print(f"{'='*60}")
        print_report_fleur(error_dict_fleur)
        
        error_report_file = root_path.parent / f"report_fleur_extracted_{time_now}.txt"
        save_report_fleur(error_dict_fleur, str(error_report_file))
        print(f"\nFLEUR error report saved to: {error_report_file}")
    
    # save summary
    if summary_store:
        df = pd.DataFrame(summary_store)
        summary_file = root_path.parent / f"summary_{time_now}.csv"
        df.to_csv(summary_file, index=False)
        print(f"\nSummary saved to: {summary_file}")
        print(f"Total calculations processed: {len(summary_store)}")
        
        # print statistics by engine
        crystal_count = sum(1 for s in summary_store if s.get('engine') == 'crystal')
        fleur_count = sum(1 for s in summary_store if s.get('engine') == 'fleur')
        print(f"  - CRYSTAL calculations: {crystal_count}")
        print(f"  - FLEUR calculations: {fleur_count}")
    else:
        print("No output files found in extracted directory")
    
    print(f"\n{'='*60}")
    print("REPORTS GENERATION COMPLETE")
    print(f"{'='*60}\n")


def restore_archives_iterative(start_path: Path, generate_reports: bool = True, aiida: bool = False):
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
        generate_reports_after_extraction(extracted_root, aiida)


@click.command()
@click.option(
    "--path",
    required=True,
    type=click.Path(exists=True),
    help="Path to the 7z archive or directory containing archives",
)
@click.option(
    "--report/--no-report",
    default=True,
    help="Generate summary and error reports after extraction",
)
@click.option(
    "--aiida/--no-aiida",
    default=False,
    help="AiiDA mode - extract UUID from path",
)
def cli(path, report, aiida):
    """Unpack 7z archive or restore archives in a directory."""
    restore_archives_iterative(Path(path), generate_reports=report, aiida=aiida)


if __name__ == "__main__":
    cli()
    # restore_archives_iterative(Path('/root/projects/dft_organizer/output_fleur_crystal.7z'), generate_reports=True, aiida=False)
