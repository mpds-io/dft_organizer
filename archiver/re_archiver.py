import subprocess
from pathlib import Path


def extract_7z(archive_path, target_dir):
    """Unpack 7z archive to target dir"""
    try:
        cmd = [
            "7z", "x",
            f"-o{target_dir}",  # dir for unpacking
            "-y",               
            str(archive_path)
        ]
        subprocess.run(cmd, check=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error during unpack {archive_path}: {e}")
        return False

def restore_archives_recursive(start_path: Path):
    """Recursively restore archives from a given path"""
    start_path = Path(start_path)
    
    # if path to file - check if it is archive
    if start_path.suffix == '.7z':
        extract_and_process(start_path)
        return
    
    # if path to dir - search for archives
    for archive in start_path.glob('**/*.7z'):
        extract_and_process(archive)

def extract_and_process(archive_path):
    """Restore archive and remove it after extraction"""
    archive_path = Path(archive_path)
    original_dir_name = archive_path.stem
    target_dir = archive_path.parent / original_dir_name
    
    if extract_7z(archive_path, target_dir):
        archive_path.unlink()         
        # restore archives in extracted dir
        restore_archives_recursive(target_dir)


if __name__ == "__main__":
    target_path = '/root/projects/science_archiver/dir_crystal_2025_06_26_16_43_46.7z'
    restore_archives_recursive(target_path)