import os
from pathlib import Path

def make_report(root: Path, files: str, error_dict: dict = {}) -> dict:
    """
    Make report with error description for CRYSTAL calculations.
    """
    if "fort.87" in files:
        with open(os.path.join(root, "fort.87"), "r") as fort_file:
            fort_content = fort_file.read().strip()

        if "INPUT" in files:
            # just first row
            with open(os.path.join(root, "INPUT"), "r") as input_file:
                first_line = input_file.readline().strip()

            if fort_content not in error_dict:
                error_dict[fort_content] = []
            error_dict[fort_content].append(first_line)

    return error_dict


def print_report(error_dict: dict) -> None:
    """
    Print report with error description.
    """
    print("\n")
    print("---------REPORT CRYSTAL ERROR---------")
    for error, structures in error_dict.items():
        print(f"Error: {error}")
        print("Structure (chemical formula):")
        for structure in structures:
            print(f"  - {structure}")
        print("\n")
        
        
def save_report(error_dict: dict, report_path: Path) -> None:
    """
    Save report with error description to a file.
    """
    with open(report_path, "w") as report_file:
        report_file.write("---------REPORT CRYSTAL ERROR---------\n")
        for error, structures in error_dict.items():
            report_file.write(f"Error: {error}\n")
            report_file.write("Structure (chemical formula):\n")
            for structure in structures:
                report_file.write(f"  - {structure}\n")
            report_file.write("\n")



