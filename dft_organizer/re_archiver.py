import subprocess
from pathlib import Path
import click


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


def restore_archives_iterative(start_path: Path):
    """Iteratively restore archives level by level"""
    start_path = Path(start_path)
    
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
                
            start_path = extracted_dir
        else:
            print("Failed to extract root archive")
            return
    
    if not start_path.is_dir():
        print(f"Path {start_path} is not a directory")
        return
    
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
                print(f"  ⚠ Skipping: failed to extract {archive_path}")


@click.command()
@click.option(
    "--path",
    required=True,
    type=click.Path(exists=True),
    help="Path to the 7z archive or directory containing archives",
)
def cli(path):
    """Unpack 7z archive or restore archives in a directory."""
    restore_archives_iterative(Path(path))


if __name__ == "__main__":
    restore_archives_iterative(Path('output_crystal.7z'))
