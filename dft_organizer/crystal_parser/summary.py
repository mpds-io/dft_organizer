from pathlib import Path
import numpy as np
from pycrystal import CRYSTOUT, CRYSTOUT_Error


def _structure_displacement(structures: list) -> dict:
    """
    Compute integral displacement between first and last structures.
    Returns sum of squared displacements and RMSD.
    """
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
    sum_sq = float(np.sum(sq))                
    rmsd = float(np.sqrt(np.mean(sq)))        

    return {"sum_sq_disp": sum_sq, "rmsd_disp": rmsd}

def parse_crystal_output(path: Path) -> dict:
    """Parse CRYSTAL OUTPUT file into a flat results dict."""
    try:
        co = CRYSTOUT(str(path))
        content: dict = co.info
    except CRYSTOUT_Error:
        print(f"CRYSTAL OUTPUT file: {path} is not readable!")
        return {
            "bandgap": float("nan"),
            "duration": float("nan"),
            "total_energy": float("nan"),      # eV
            "energy_hartree": float("nan"),    # Ha
            "cell": float("nan"),
            "positions": float("nan"),
            "pbc": float("nan"),
            "numbers": float("nan"),
            "symbols": float("nan"),
        }

    results: dict = {}

    energy = content.get("energy", float("nan"))
    results["total_energy"] = energy
    results["energy_hartree"] = energy / 27.2114 if energy != None else float("nan")

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

    # last structure
    try:
        structs = content.get("structures", [])
        if structs:
            ase_obj = structs[-1]
            results["cell"]     = ase_obj.get_cell().tolist()
            results["positions"] = ase_obj.get_positions().tolist()
            results["pbc"]      = ase_obj.get_pbc().tolist()
            results["numbers"]  = ase_obj.get_atomic_numbers().tolist()
            results["symbols"]  = ase_obj.get_chemical_symbols()
        else:
            raise KeyError
    except Exception:
        results["cell"] = float("nan")
        results["positions"] = float("nan")
        results["pbc"] = float("nan")
        results["numbers"] = float("nan")
        results["symbols"] = float("nan")
        
    # integral displacement metrics
    disp_metrics = _structure_displacement(structs if isinstance(structs, list) else [])
    results.update(disp_metrics)

    return results


if __name__ == "__main__":
    res = parse_crystal_output(
        Path("/data/aiida_crystal_base/0a/2f/a4e3-fb3e-4419-b02f-b1a50c762872/OUTPUT")
    )
    print(res)
