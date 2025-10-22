from pathlib import Path


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