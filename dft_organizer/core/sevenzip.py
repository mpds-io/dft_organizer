from pathlib import Path
import py7zr


def compress_with_7z(source_dir: Path, archive_path: Path) -> bool:
    """Compress directory using py7zr without storing parent paths"""
    try:
        print(f"Archiving {source_dir} to {archive_path}...")

        with py7zr.SevenZipFile(archive_path, 'w', filters=[
            {"id": py7zr.FILTER_LZMA2, "preset": 9}
        ]) as archive:
            for path in source_dir.rglob("*"):
                archive.write(
                    path,
                    arcname=path.relative_to(source_dir.parent)
                )

        return True
    except Exception as e:
        print(f"Error archiving {source_dir}: {e}")
        return False


def extract_7z(archive_path: Path, target_dir: Path) -> bool:
    """Unpack 7z archive to target dir"""
    try:
        print(f"Extracting {archive_path}...")

        with py7zr.SevenZipFile(archive_path, 'r') as archive:
            archive.extractall(path=target_dir)

        return True
    except Exception as e:
        print(f"Error extracting {archive_path}: {e}")
        return False