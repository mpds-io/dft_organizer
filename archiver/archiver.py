import os
import subprocess
from pathlib import Path
from datetime import datetime


def compress_with_7z(source_dir: Path, archive_path: Path) -> bool:
    """Compress dir using 7z and remove orig files"""
    try:
        cmd = [
            "7z", "a",
            "-t7z",  # format 7z
            "-mx=9",  # max compression
            "-m0=LZMA2",  
            "-mmt=on", 
            str(archive_path),
            str(source_dir) + "/*"
        ]
        
        print(f"Archive {source_dir} in {archive_path}...")
        subprocess.run(cmd, check=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error {source_dir}: {e}")
        return False

def archive_and_remove(root_dir: Path, engine: str = "crystal") -> None:
    """Archive dir and remove orig files"""
    root_path = Path(root_dir)
    
    if not root_path.exists():
        print(f"No such dir: {root_path}")
        return
    
    # from bottom to top
    for dirpath, dirnames, filenames in os.walk(root_path, topdown=False):
        current_dir = Path(dirpath)
        
        if not os.listdir(current_dir):
            continue
        
        if root_path == current_dir:
            archive_name = f"{current_dir.name}_{engine}_{datetime.now().strftime('%Y_%m_%d_%H_%M_%S')}.7z"
        else:
            archive_name = f"{current_dir.name}.7z"
            
        archive_path = current_dir.parent / archive_name
        
        if compress_with_7z(current_dir, archive_path):
            shutil.rmtree(current_dir)

if __name__ == "__main__":
    import shutil
    
    target_dir = "/root/projects/science_archiver/dir_for_test"   
    archive_and_remove(target_dir, 'crystal')
