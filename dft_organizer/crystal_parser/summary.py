from pathlib import Path
import math
import re

import numpy as np
from pycrystal import CRYSTOUT, CRYSTOUT_Error
from ase.geometry import cell_to_cellpar

from dft_organizer.ase_utils import get_formula
from dft_organizer.crystal_parser.parse_properties import parse_seebeck_first_line


def count_optimization_cycles(filename):
    """
    Count the number of geometry optimization cycles in CRYSTAL output files.
    Looks for lines containing "OPTIMIZATION - POINT N".
    """
    with open(filename, 'r') as f:
        content = f.read()

    # Pattern matches "COORDINATE AND CELL OPTIMIZATION - POINT N" where N is a number
    pattern = r'OPTIMIZATION - POINT\s+(\d+)'
    matches = re.findall(pattern, content)

    if matches:
        num_cycles = len(matches)
        print(f"Number of geometry optimization cycles: {num_cycles}")
        print(f"Found points: {', '.join(matches)}")
        return num_cycles
    else:
        print("No optimization cycles found")
        return 0


def round_floats(obj, ndigits: int = 2):
    """Recursively round all numeric values in dict/list/tuple to ndigits."""
    if isinstance(obj, dict):
        return {k: round_floats(v, ndigits) for k, v in obj.items()}

    if isinstance(obj, (list, tuple)):
        t = [round_floats(v, ndigits) for v in obj]
        return t if isinstance(obj, list) else tuple(t)

    # numpy scalars -> python scalars
    if isinstance(obj, np.generic):
        obj = obj.item()

    # bool is subclass of int -> exclude it
    if isinstance(obj, bool):
        return obj

    if isinstance(obj, (int, float)):
        if isinstance(obj, float) and not math.isfinite(obj):
            return obj  # keep nan/inf as-is
        return round(obj, ndigits)

    return obj


def _structure_displacement(structures: list) -> dict:
    if not structures or len(structures) < 2:
        return {"sum_sq_disp": float("nan"), "rmsd_disp": float("nan")}

    first = structures[0]
    last = structures[-1]

    pos_init = np.array(first.positions, dtype=float)
    pos_final = np.array(last.positions, dtype=float)

    if pos_init.shape != pos_final.shape:
        return {"sum_sq_disp": float("nan"), "rmsd_disp": float("nan")}

    disp = pos_final - pos_init
    sq = np.sum(disp**2, axis=1)
    return {
        "sum_sq_disp": float(np.sum(sq)),
        "rmsd_disp": float(np.sqrt(np.mean(sq))),
    }

_PERIODIC_TABLE = {
    1: "H", 2: "He", 3: "Li", 4: "Be", 5: "B", 6: "C", 7: "N", 8: "O",
    9: "F", 10: "Ne", 11: "Na", 12: "Mg", 13: "Al", 14: "Si", 15: "P",
    16: "S", 17: "Cl", 18: "Ar", 19: "K", 20: "Ca", 21: "Sc", 22: "Ti",
    23: "V", 24: "Cr", 25: "Mn", 26: "Fe", 27: "Co", 28: "Ni", 29: "Cu",
    30: "Zn", 31: "Ga", 32: "Ge", 33: "As", 34: "Se", 35: "Br", 36: "Kr",
    37: "Rb", 38: "Sr", 39: "Y", 40: "Zr", 41: "Nb", 42: "Mo", 43: "Tc",
    44: "Ru", 45: "Rh", 46: "Pd", 47: "Ag", 48: "Cd", 49: "In", 50: "Sn",
    51: "Sb", 52: "Te", 53: "I", 54: "Xe", 55: "Cs", 56: "Ba", 57: "La",
    58: "Ce", 59: "Pr", 60: "Nd", 61: "Pm", 62: "Sm", 63: "Eu", 64: "Gd",
    65: "Tb", 66: "Dy", 67: "Ho", 68: "Er", 69: "Tm", 70: "Yb", 71: "Lu",
    72: "Hf", 73: "Ta", 74: "W", 75: "Re", 76: "Os", 77: "Ir", 78: "Pt",
    79: "Au", 80: "Hg", 81: "Tl", 82: "Pb", 83: "Bi", 84: "Po", 85: "At",
    86: "Rn", 87: "Fr", 88: "Ra", 89: "Ac", 90: "Th", 91: "Pa", 92: "U",
    93: "Np", 94: "Pu", 95: "Am", 96: "Cm", 97: "Bk", 98: "Cf", 99: "Es",
    100: "Fm", 101: "Md", 102: "No", 103: "Lr",
    238: "U",
    240: "Zr",
}


def _parse_properties_only(path: Path) -> dict:
    results: dict = {
        "bandgap": float("nan"),
        "duration": float("nan"),
        "sum_sq_disp": float("nan"),
        "rmsd_disp": float("nan"),
        "chemical_formula": "",
        "techs_1_FMIXING": "",
        "techs_2": "",
        "t1": "",
        "t5": "",
        "k": float("nan"),
        "H": "",
        "smear": float("nan"),
        "spin": float("nan"),
        "optgeom": False,
        "num_opt_cycles": 0,
        "seebeck_avg": float("nan"),
        "temperature": float("nan"),
    }

    with open(path, "r") as f:
        content = f.read()

    duration_match = re.search(r"TOTAL CPU TIME\s*=\s*([\d.]+)", content)
    if duration_match:
        try:
            results["duration"] = round(float(duration_match.group(1)) / 3600, 2)
        except ValueError:
            pass

    bandgap_match = re.findall(
        r"(DIRECT|INDIRECT) ENERGY BAND GAP:\s*([.\d]*)", content
    )
    if bandgap_match:
        try:
            results["bandgap"] = float(bandgap_match[-1][1])
        except (ValueError, IndexError):
            pass
    elif "CONDUCTING STATE" in content:
        results["bandgap"] = 0.0

    seebeck_file = path.parent / "SEEBECK.DAT"
    if seebeck_file.exists():
        try:
            avg_s, S_components, temperature = parse_seebeck_first_line(
                str(seebeck_file)
            )
            results["seebeck_avg"] = avg_s
            results["temperature"] = temperature
        except Exception:
            pass

    atom_block = re.search(
        r"ATOM\s+N\.AT\.\s+SHELL\s+X\(A\)\s+Y\(A\)\s+Z\(A\)\s+EXAD\s+N\.ELECT\.\s*\n([\s\S]*?)\n\s*\*{2,}",
        content,
    )
    if atom_block:
        atom_lines = atom_block.group(1).strip().split("\n")
        symbols = []
        for line in atom_lines:
            line = line.strip()
            if not line or line.startswith("*"):
                continue
            parts = line.split()
            if len(parts) >= 4:
                symbol = parts[2].strip()
                symbols.append(symbol)
        if symbols:
            from collections import Counter
            from math import gcd as math_gcd
            from functools import reduce
            from dft_organizer.ase_utils import FORMULA_SEQUENCE
            counts = Counter(symbols)
            g = reduce(math_gcd, counts.values()) if len(counts) > 1 else list(counts.values())[0]
            ordered = [x for x in FORMULA_SEQUENCE if x in counts] + [
                x for x in counts if x not in FORMULA_SEQUENCE
            ]
            results["chemical_formula"] = "".join(
                f"{s}{'' if (counts[s] // g) == 1 else str(counts[s] // g)}"
                for s in ordered
            )

    vec_block = re.search(
        r"DIRECT LATTICE VECTOR COMPONENTS \(ANGSTROM\)\s*\n"
        r"\s*([\d.E+-]+)\s+([\d.E+-]+)\s+([\d.E+-]+)\s*\n"
        r"\s*([\d.E+-]+)\s+([\d.E+-]+)\s+([\d.E+-]+)\s*\n"
        r"\s*([\d.E+-]+)\s+([\d.E+-]+)\s+([\d.E+-]+)",
        content,
    )
    if vec_block:
        try:
            cell = np.array([
                [float(vec_block.group(i)) for i in range(1, 4)],
                [float(vec_block.group(i)) for i in range(4, 7)],
                [float(vec_block.group(i)) for i in range(7, 10)],
            ])
            a, b, c, alpha, beta, gamma = cell_to_cellpar(cell)
            results["a"] = round(float(a), 2)
            results["b"] = round(float(b), 2)
            results["c"] = round(float(c), 2)
            results["alpha"] = round(float(alpha), 2)
            results["beta"] = round(float(beta), 2)
            results["gamma"] = round(float(gamma), 2)
        except Exception:
            pass

    lat_match = re.search(
        r"A\s*=\s*([\d.]+)\s*B\s*=\s*([\d.]+)\s*C\s*=\s*([\d.]+)\s*"
        r"ALPHA\s*=\s*([\d.]+)\s*BETA\s*=\s*([\d.]+)\s*GAMMA\s*=\s*([\d.]+)",
        content,
    )
    if lat_match and "a" not in results:
        try:
            results["a"] = round(float(lat_match.group(1)), 2)
            results["b"] = round(float(lat_match.group(2)), 2)
            results["c"] = round(float(lat_match.group(3)), 2)
            results["alpha"] = round(float(lat_match.group(4)), 2)
            results["beta"] = round(float(lat_match.group(5)), 2)
            results["gamma"] = round(float(lat_match.group(6)), 2)
        except Exception:
            pass

    return results


def parse_crystal_output(path: Path) -> dict:
    try:
        co = CRYSTOUT(str(path))
        content: dict = co.info
    except CRYSTOUT_Error as e:
        if "PROPERTIES output with insufficient information" in str(e):
            print(f"CRYSTAL OUTPUT file: {path} is PROPERTIES-only, parsing manually")
            return round_floats(_parse_properties_only(path), 2)
        print(f"CRYSTAL OUTPUT file: {path} is not readable!")
        return round_floats(
            {
                "bandgap": float("nan"),
                "duration": float("nan"),
                "sum_sq_disp": float("nan"),
                "rmsd_disp": float("nan"),
                "chemical_formula": "",
                "techs_1_FMIXING": "",
                "techs_2": "",
                "t1": "",
                "t5": "",
                "k": float("nan"),
                "H": "",
                "smear": float("nan"),
                "spin": float("nan"),
                "optgeom": False,
                "num_opt_cycles": 0,
                "seebeck_avg": float("nan"),
                "temperature": float("nan"),
            },
            2,
        )

    results: dict = {}

    # INPUT parameters from obj.info
    try:
        # results["techs_0_TOLINTEG"] = content.get("techs", [""])[0]
        results["techs_1_FMIXING"] = content.get("techs", ["", ""])[1]
    except IndexError:
        pass
    results["techs_2"] = content.get("techs", ["", "", ""])

    if "optgeom" in co.info.keys():
        if co.info["optgeom"] != []:
            results["optgeom"] = True
        num_opt_cycles = count_optimization_cycles(str(path))
        results["num_opt_cycles"] = num_opt_cycles
    else:
        results["optgeom"] = False
        results["num_opt_cycles"] = 0

    if len(results["techs_2"]) > 2:
        if 'by' in results["techs_2"][2]:
            results["techs_2"] = results["techs_2"][2]
        else:
            results["techs_2"] = ""
    else:
        results["techs_2"] = ""

    # input parms
    input_params = ["MAXCYCLE", "TOLDEE", "TOLLDENS", "TOLLGRID", "SHRINK", "TOLINTEG"]
    for p in input_params:
        match = re.search(rf'{p}\n([^\n]+)', content['input'])
        if match:
            results[p] = match.group(1)

    try:
        # results["techs_3_smear"] = content.get("techs", ["", "", "", ""])[3]
        results["t1"] = content.get("tol", [""])[0]
        results["t5"] = content.get("tol", [""])[-1]
        results["k"] = content.get("k", [float("nan")])[0]
        results["H"] = content.get("H", "")
        results["smear"] = content.get("smear", float("nan"))
        results["spin"] = float(content.get("spin", float("nan")))
    except TypeError:
        pass

    # duration
    try:
        results["duration"] = float(content.get("duration", float("nan")))
    except Exception:
        results["duration"] = float("nan")

    # seebeck
    seebeck_file = path.parent / "SEEBECK.DAT"
    if seebeck_file.exists():
        try:
            avg_s, S_components, temperature = parse_seebeck_first_line(str(seebeck_file))
            results["seebeck_avg"] = avg_s
            results["temperature"] = temperature
        except Exception:
            results["seebeck_avg"] = float("nan")
            results["temperature"] = float("nan")

    # band gap
    bandgap = float("nan")
    cond = content.get("conduction")
    if isinstance(cond, list) and cond:
        bg = cond[-1].get("band_gap", None)
        if bg is not None:
            bandgap = float(bg)
    results["bandgap"] = bandgap

    # last structure: cell > cellpar
    structs = content.get("structures", [])
    try:
        if structs:
            ase_obj = structs[-1]
            a, b, c, alpha, beta, gamma = cell_to_cellpar(ase_obj.get_cell())  # [a,b,c,alpha,beta,gamma]
            results["a"] = round(float(a), 2)
            results["b"] = round(float(b), 2)
            results["c"] = round(float(c), 2)
            results["alpha"] = round(float(alpha), 2)
            results["beta"] = round(float(beta), 2)
            results["gamma"] = round(float(gamma), 2)
            results["chemical_formula"] = get_formula(ase_obj, find_gcd=True)
        else:
            raise KeyError
    except Exception:
        results["a"] = float("nan")
        results["b"] = float("nan")
        results["c"] = float("nan")
        results["alpha"] = float("nan")
        results["beta"] = float("nan")
        results["gamma"] = float("nan")
        results["chemical_formula"] = ""

    # displacement metrics
    results.update(_structure_displacement(structs if isinstance(structs, list) else []))

    return round_floats(results, 2)


if __name__ == "__main__":
    res = parse_crystal_output(
        Path("/data/aiida_crystal_base/0a/2f/a4e3-fb3e-4419-b02f-b1a50c762872/OUTPUT")
    )
    print(res)
