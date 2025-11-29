from pathlib import Path

from pycrystal import CRYSTOUT, CRYSTOUT_Error


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
    results["energy_hartree"] = energy / 27.2114 if energy == energy else float("nan")

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

    return results


if __name__ == "__main__":
    res = parse_crystal_output(
        Path("/data/aiida_crystal_base/0a/2f/a4e3-fb3e-4419-b02f-b1a50c762872/OUTPUT")
    )
    print(res)
