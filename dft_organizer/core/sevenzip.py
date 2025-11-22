import subprocess
from pathlib import Path


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
        _ = subprocess.run(
            cmd, check=True, capture_output=True, text=True, cwd=str(source_dir.parent)
        )
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error archiving {source_dir}: {e}")
        print(f"Output: {e.stderr if hasattr(e, 'stderr') else ''}")
        return False


def extract_7z(archive_path: Path, target_dir: Path) -> bool:
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
