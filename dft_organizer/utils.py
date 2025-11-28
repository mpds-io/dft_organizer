import polars as pl 
from dft_organizer.crystal_parser import parse_crystal_output
from dft_organizer.fleur_parser import parse_fleur_output
from dft_organizer.fmt import detect_calculation_code


def get_table_string(res: dict) -> str:
    """Build a table string from generic FLEUR/CRYSTAL results."""

    def fmt(val, prec=6):
        if isinstance(val, (int, float)):
            if val != val:  # NaN
                return "N/A"
            return f"{val:.{prec}g}"
        if val is None:
            return "N/A"
        return str(val)

    lines = []
    lines.append(f"{'Parameter':<25} {'Value':<20}")
    lines.append("-" * 50)

    rows = [
        ("Total Energy (eV)",     fmt(res.get("total_energy"))),
        ("Total Energy (Ha)",     fmt(res.get("energy_hartree"))),
        ("Duration (h)",          fmt(res.get("duration"), prec=4)),
        ("Band Gap (eV)",         fmt(res.get("bandgap"))),
    ]

    for label, val in rows:
        lines.append(f"{label:<25} {val:<20}")

    return "\n".join(lines)

def detect_engine(filenames: list, current_dir) -> dict:
    """Detect DFT engine based on presence of specific files"""
    fmt_map = {}
    for file in filenames:
        fmt, _ = detect_calculation_code(current_dir / file)
        fmt_map[file] = fmt
    if "OUTPUT" in fmt_map and "crystal" in fmt_map.values():
        return "crystal"
    elif "out" in fmt_map or "out.xml" in fmt_map and "fleur" in fmt_map.values():
        return "fleur"
    else:
        return "unknown"


def create_summary_table(path_dict: dict) -> pl.DataFrame:
    """Create summary table comparing CRYSTAL and FLEUR results

    Args:
        path_dict (dict): {'H': {'crystal': 'path/to/OUTPUT', 'fleur': 'path/to/out'}, ...}
    Returns:
        pl.DataFrame: Summary of CPU time and bandgap from both codes.
    """
    summary_data = []

    for formula, paths in path_dict.items():
        row_data = {"Element": formula}
        crystal_file = paths.get("crystal")
        fleur_file = paths.get("fleur")

        if crystal_file:
            crystal_res = parse_crystal_output(crystal_file)
            row_data.update(
                {
                    "CRYSTAL_Time": crystal_res.get("cpu_time", "N/A"),
                    "CRYSTAL_Bandgap": crystal_res.get("bandgap", "N/A"),
                }
            )
        else:
            row_data.update({"CRYSTAL_Time": "N/A", "CRYSTAL_Bandgap": "N/A"})

        if fleur_file:
            fleur_res = parse_fleur_output(fleur_file)
            row_data.update(
                {
                    "FLEUR_Time": fleur_res.get("cpu_time", "N/A"),
                    "FLEUR_Bandgap": fleur_res.get("bandgap", "N/A"),
                }
            )
        else:
            row_data.update({"FLEUR_Time": "N/A", "FLEUR_Bandgap": "N/A"})

        summary_data.append(row_data)

    return pl.DataFrame(summary_data)

