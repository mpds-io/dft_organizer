import subprocess
from pathlib import Path

import click


def extract_7z(archive_path, target_dir):
    """Unpack 7z archive to target dir"""
    try:
        cmd = [
            "7z",
            "x",
            f"-o{target_dir}",  # dir for unpacking
            "-y",
            str(archive_path),
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
    if start_path.suffix == ".7z":
        extract_and_process(start_path)
        return

    # if path to dir - search for archives
    for archive in start_path.glob("**/*.7z"):
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


@click.command()
@click.option(
    "--path",
    required=True,
    type=click.Path(exists=True),
    help="Path to the 7z archive or directory containing archives",
)
def cli(path):
    """Unpack 7z archive or restore archives in a directory."""
    restore_archives_recursive(Path(path))


if __name__ == "__main__":
    # cli()
    restore_archives_recursive(Path('/root/projects/dft_organizer/playground_data.7z'))
    
