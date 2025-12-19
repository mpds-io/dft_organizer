from pathlib import Path
import math
import numpy as np
from pycrystal import CRYSTOUT, CRYSTOUT_Error
from ase.geometry import cell_to_cellpar

from dft_organizer.ase_utils import get_formula


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


def parse_crystal_output(path: Path) -> dict:
    try:
        co = CRYSTOUT(str(path))
        content: dict = co.info
    except CRYSTOUT_Error:
        print(f"CRYSTAL OUTPUT file: {path} is not readable!")
        return round_floats(
            {
                "bandgap": float("nan"),
                "duration": float("nan"),
                "total_energy": float("nan"),   # eV
                "energy_hartree": float("nan"), # Ha
                "sum_sq_disp": float("nan"),
                "rmsd_disp": float("nan"),
                "chemical_formula": "",
            },
            2,
        )

    results: dict = {}

    energy = content.get("energy", float("nan"))
    results["total_energy"] = float("nan") if energy is None else float(energy)
    results["energy_hartree"] = (
        float("nan") if energy is None else float(energy) / 27.2114
    )

    # duration
    try:
        results["duration"] = float(content.get("duration", float("nan")))
    except Exception:
        results["duration"] = float("nan")

    # band gap
    bandgap = float("nan")
    cond = content.get("conduction")
    if isinstance(cond, list) and cond:
        bg = cond[-1].get("band_gap", None)
        if bg is not None:
            bandgap = float(bg)
    results["bandgap"] = bandgap

    # last structure: cell -> cellpar
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
