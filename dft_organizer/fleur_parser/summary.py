import re
import math
from pathlib import Path

import numpy as np
from masci_tools.io.parsers.fleur import outxml_parser
from ase.io import read
from ase.geometry import cell_to_cellpar

from dft_organizer.ase_utils import get_formula 


def round_floats(obj, ndigits: int = 2):
    """Recursively round all numeric values in dict/list/tuple to ndigits; keep NaN/Inf."""
    if isinstance(obj, dict):
        return {k: round_floats(v, ndigits) for k, v in obj.items()}

    if isinstance(obj, (list, tuple)):
        t = [round_floats(v, ndigits) for v in obj]
        return t if isinstance(obj, list) else tuple(t)

    if isinstance(obj, np.generic):
        obj = obj.item()

    if isinstance(obj, bool):
        return obj

    if isinstance(obj, (int, float)):
        if isinstance(obj, float) and not math.isfinite(obj):
            return obj
        return round(float(obj), ndigits)

    return obj


def _nan_cellpar_results() -> dict:
    return {
        "a": float("nan"),
        "b": float("nan"),
        "c": float("nan"),
        "alpha": float("nan"),
        "beta": float("nan"),
        "gamma": float("nan"),
        "chemical_formula": "",
    }


def parse_fleur_out_xml(filename: Path) -> dict:
    """
    Parse FLEUR out.xml file using masci_tools and return results dictionary
    """
    try:
        parsed_data = outxml_parser(filename)
    except Exception as e:
        print(f"Error parsing file {filename}: {e}")
        return {}

    results = {}

    # CPU time: walltime in sec -> in hours
    walltime_sec = parsed_data.get("walltime", float("nan"))
    results["duration"] = walltime_sec / 3600 if walltime_sec else float("nan")

    results["bandgap"] = parsed_data.get("bandgap", float("nan"))

    # structure -> cellpar columns
    try:
        ase_obj = read(filename, format="fleur-outxml")
        a, b, c, alpha, beta, gamma = cell_to_cellpar(ase_obj.get_cell())  
        results.update(
            {
                "a": float(a),
                "b": float(b),
                "c": float(c),
                "alpha": float(alpha),
                "beta": float(beta),
                "gamma": float(gamma),
                "chemical_formula": get_formula(ase_obj, find_gcd=True)
            }
        )
    except Exception as e:
        print(f"Error reading structure from file {filename}: {e}")
        results.update(_nan_cellpar_results())
        results["sum_sq_disp"] = float("nan")
        results["rmsd_disp"] = float("nan")
        results["chemical_formula"] = ""
        return round_floats(results, 2)

    # displacement metrics
    inp_path = filename.parent / "inp.xml"
    if inp_path.is_file():
        disp = {"sum_sq_disp": 0.0, "rmsd_disp": 0.0}
        results.update(disp)
    else:
        results["sum_sq_disp"] = float("nan")
        results["rmsd_disp"] = float("nan")

    return round_floats(results, 2)


def parse_fleur_output(filename: Path) -> dict:
    """
    Parse FLEUR output file and return results dictionary
    """
    if filename.suffix == ".xml":
        return parse_fleur_out_xml(filename)

    try:
        with open(filename, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
    except Exception as e:
        print(f"Error reading file {filename}: {e}")
        return {}

    results = {}
    results.update(_nan_cellpar_results())

    time_match = re.search(r"Total execution time:\s*(\d+)sec", content)
    results["duration"] = float(time_match.group(1)) / 3600 if time_match else float("nan")

    bandgap_match = re.search(r"bandgap\s*:\s*([\d\.E+-]+)\s*htr", content, re.IGNORECASE)
    if not bandgap_match:
        bandgap_match = re.search(
            r"FERHIS:\s*Fermi-Energy by histogram:\s*bandgap\s*:\s*([\d\.E+-]+)\s*htr",
            content,
            re.IGNORECASE,
        )
    results["bandgap"] = float(bandgap_match.group(1)) * 27.2114 if bandgap_match else float("nan")

    results["sum_sq_disp"] = float("nan")
    results["rmsd_disp"] = float("nan")

    return round_floats(results, 2)
