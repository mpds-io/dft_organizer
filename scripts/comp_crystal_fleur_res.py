import os
from collections import defaultdict
from dft_organizer.utils import create_summary_table
from pycrystal import CRYSTOUT
from ase.io import read
import re


def find_output_files(root_dir, target_filename):
    """
    Recursively search for files with a specific filename in a directory tree.
    
    Args:
        root_dir (str): The root directory to start the search from
        target_filename (str): The filename to search for
        
    Returns:
        list: List of full paths to files matching the target filename
    """
    output_files = []
    for dirpath, _, filenames in os.walk(root_dir):
        if target_filename in filenames:
            output_files.append(os.path.join(dirpath, target_filename))
    return output_files

def parse_crystal_formula(filename):
    """
    Parse chemical formula from CRYSTAL output file.
    
    Args:
        filename (str): Path to CRYSTAL OUTPUT file
        
    Returns:
        str: Chemical formula extracted from the file, or None if parsing fails
    """
    CRYSTOUT_file = CRYSTOUT(filename)
    return str(CRYSTOUT_file.info['structures'][0].symbols)

def parse_fleur_formula(filepath: str) -> str:
    """
    Parse chemical formula from FLEUR output files using multiple methods.
    
    First attempts to use ASE library to parse XML output files.
    If that fails, falls back to regex pattern matching in text files.
    
    Args:
        filepath (str): Path to FLEUR output file (.xml or .out)
        
    Returns:
        str: Chemical formula if successfully parsed, None otherwise
    """
    try:
        atoms = read(filepath)   
        return atoms.get_chemical_formula()
    except Exception as e:
        print(f"Error parsing by ase {filepath}: {e}")
        
    try:
        with open(filepath[:-4], 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        for pattern in [r'atom:\s*([A-Za-z]+)', r'System:\s*(\w+)']:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                return match.group(1)
        return None
    except Exception as e:
        print(f"Eror parsing by 're' {filepath}: {e}")
        return None

def normalize_formula(formula):
    """
    Normalize chemical formula by removing non-alphabetic characters 
    and converting to uppercase.
    
    Args:
        formula (str): Input chemical formula (may contain numbers/symbols)
        
    Returns:
        str: Normalized formula containing only uppercase letters, 
             or None if input is None/empty
    """
    if formula:
        return ''.join([c for c in formula if c.isalpha()]).upper()
    return None

def create_formula_path_dict(crystal_dir, fleur_dir):
    """
    Create a dictionary mapping chemical formulas to their corresponding 
    CRYSTAL and FLEUR output file paths.
    
    Args:
        crystal_dir (str): Directory containing CRYSTAL output files
        fleur_dir (str): Directory containing FLEUR output files
        
    Returns:
        dict: Dictionary with normalized formulas as keys and dictionaries 
              containing 'crystal' and/or 'fleur' file paths as values
    """
    crystal_files = find_output_files(crystal_dir, 'OUTPUT')
    fleur_files = find_output_files(fleur_dir, 'out')
    formula_dict = defaultdict(dict)
    
    for crystal_file in crystal_files:
        formula = parse_crystal_formula(crystal_file)
        if formula:
            normalized = normalize_formula(formula)
            if normalized:
                formula_dict[normalized]["crystal"] = crystal_file
    
    for fleur_file in fleur_files:
        formula = parse_fleur_formula(fleur_file[:-3] + 'out.xml')
        if formula:
            normalized = normalize_formula(formula)
            if normalized:
                formula_dict[normalized]["fleur"] = fleur_file
    
    return dict(formula_dict)


def main():
    """
    Main function to compare CRYSTAL and FLEUR calculation results.
    
    Searches for output files in specified directories, extracts chemical formulas,
    creates a comparison summary table, and saves it to CSV.
    """
    crystal_dir = "output_crystal"
    fleur_dir = "output_fleur"

    formula_paths = create_formula_path_dict(crystal_dir, fleur_dir)

    summary_data = create_summary_table(formula_paths)
    summary_data.to_csv("comparison_summary.csv", index=False)
    
    print(summary_data)

if __name__ == "__main__":
    main()