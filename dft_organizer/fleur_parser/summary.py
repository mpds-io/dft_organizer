import re
from masci_tools.io.parsers.fleur import outxml_parser
from pathlib import Path
from ase.io import read

import numpy as np

def structure_displacement(initial_file: Path, final_file: Path) -> dict:
    """
    Compute integral displacement between initial and optimized structures.
    Returns sum of squared displacements and RMSD.
    """
    atoms_init = read(initial_file, format="fleur-xml")               # read(initial_file, format="fleur-inpxml")
    atoms_final = read(final_file, format="fleur-outxml")

    pos_init = atoms_init.get_positions()
    pos_final = atoms_final.get_positions()

    if pos_init.shape != pos_final.shape:
        raise ValueError("Initial and final structures have different sizes/order")

    disp = pos_final - pos_init          
    sq = np.sum(disp**2, axis=1)        
    sum_sq = float(np.sum(sq))         
    rmsd = float(np.sqrt(np.mean(sq)))  

    return {
        "sum_sq_disp": sum_sq,
        "rmsd_disp": rmsd,
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

    # total energy (eV)
    results["total_energy"] = parsed_data.get("energy", float("nan"))

    # CPU time: walltime in sec -> in hours
    walltime_sec = parsed_data.get("walltime", float("nan"))
    results["duration"] = walltime_sec / 3600 if walltime_sec else float("nan")

    results["bandgap"] = parsed_data.get("bandgap", float("nan"))

    results["energy_hartree"] = parsed_data.get('energy_hartree', float("nan"))
    
    # structure data
    ase_obj = read(filename, format="fleur-outxml")
    results["cell"]     = ase_obj.get_cell().tolist()
    results["positions"] = ase_obj.get_positions().tolist()
    results["pbc"]      = ase_obj.get_pbc().tolist()
    results["numbers"]  = ase_obj.get_atomic_numbers().tolist()
    results["symbols"]  = ase_obj.get_chemical_symbols()
    
    inp_path = filename.parent / "inp.xml"
    if inp_path.is_file():
        disp = structure_displacement(inp_path, filename)
        results.update(disp)
    return results


def parse_fleur_output(filename: Path):
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

    energy_match = re.search(r"total energy=\s*([-\d\.E+]+)", content)
    if energy_match:
        results["total_energy"] = float(energy_match.group(1))

    time_match = re.search(r"Total execution time:\s*(\d+)sec", content)
    if time_match:
        results["duration"] = float(time_match.group(1)) / 3600

    bandgap_match = re.search(
        r"bandgap\s*:\s*([\d\.E+-]+)\s*htr", content, re.IGNORECASE
    )
    if not bandgap_match:
        bandgap_match = re.search(
            r"FERHIS:\s*Fermi-Energy by histogram:\s*bandgap\s*:\s*([\d\.E+-]+)\s*htr",
            content,
            re.IGNORECASE,
        )

    if bandgap_match:
        results["bandgap"] = (
            float(bandgap_match.group(1)) * 27.2114
        )  # convert Hartree -> eV

    charges_match = re.search(
        r"l-like charge.*?1\s+([\d\.]+)\s+([\d\.]+)\s+([\d\.]+)\s+([\d\.]+)\s+([\d\.]+)",
        content,
        re.DOTALL,
    )
    
    results["energy_hartree"] = results["total_energy"] / 27.21
    
    # TODO: fix it
    # no information for structure in .out files
    results["cell"] = float("nan")
    results["positions"] = float("nan")
    results["pbc"] = float("nan")
    results["numbers"] = float("nan")
    results["symbols"] = float("nan")
    return results
    

def get_fleur_table_string(fleur_res: dict) -> str:
    """
    Create a formatted table string from FLEUR results
    """
    def fmt(val, prec=6):
        if isinstance(val, (int, float)):
            if val != val:  
                return "N/A"
            return f"{val:.{prec}g}"
        return str(val)

    lines = []
    lines.append(f"{'Parameter':<25} {'Value':<20}")
    lines.append("-" * 50)

    rows = [
        ("Total Energy (eV)",      fmt(fleur_res.get("total_energy"))),
        ("Total Energy (Ha)",      fmt(fleur_res.get("energy_hartree"))),
        ("Duration (h)",           fmt(fleur_res.get("duration"), prec=4)),
        ("Band Gap (eV)",          fmt(fleur_res.get("bandgap"))),
    ]

    for label, val in rows:
        lines.append(f"{label:<25} {val:<20}")

    return "\n".join(lines)
