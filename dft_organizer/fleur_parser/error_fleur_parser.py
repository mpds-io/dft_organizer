import os
from pathlib import Path


def make_report(root: Path, files: list[str], error_dict: dict = {}) -> dict:
    """
    Make report with error description for FLEUR calculations.
    """
    if "fleur.error" in files:
        fleur_path = os.path.join(root, "fleur.error")
        with open(fleur_path, "r") as fleur_file:
            fleur_lines = fleur_file.readlines()

        errors = []
        inside_error_block = False
        current_error = []

        for line in fleur_lines:
            stripped = line.strip()

            # start block juDFT-Error
            if stripped.startswith("**************juDFT-Error"):
                inside_error_block = True
                current_error = [stripped]
                continue

            # end juDFT-Error block
            if inside_error_block and stripped.startswith("*****************************************"):
                current_error.append(stripped)
                errors.append("\n".join(current_error))
                inside_error_block = False
                current_error = []
                continue

            if inside_error_block:
                current_error.append(line.rstrip())
                continue

            if "Schemas validity error" in stripped:
                errors.append(stripped)

        # ifjuDFT-Error is not closed properly
        if inside_error_block and current_error:
            errors.append("\n".join(current_error))

        # structure_name = Path(root).name

        if errors:
            for err in errors:
                if err not in error_dict:
                    error_dict[err] = []
                error_dict[err].append(root)
        else:
            if "No errors found" not in error_dict:
                error_dict["No errors found"] = []
            error_dict["No errors found"].append(root)

    return error_dict


def print_report(error_dict: dict) -> None:
    """
    Print report with error description for FLEUR calculations.
    """
    print("\n")
    print("---------REPORT FLEUR ERROR---------")
    for error, structures in error_dict.items():
        print("Error:")
        print(error)
        print("Structure (system folder name):")
        for structure in structures:
            print(f" - {structure}")
        print("\n")


def save_report(error_dict: dict, report_path: Path) -> None:
    """
    Save report with error description for FLEUR calculations.
    """
    with open(report_path, "w") as report_file:
        report_file.write("---------REPORT FLEUR ERROR---------\n")
        for error, structures in error_dict.items():
            report_file.write("Error:\n")
            report_file.write(error + "\n")
            report_file.write("Structure (system folder name):\n")
            for structure in structures:
                report_file.write(f" - {structure}\n")
            report_file.write("\n")


    