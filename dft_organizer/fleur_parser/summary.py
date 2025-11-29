from masci_tools.io.parsers.fleur import outxml_parser
from pathlib import Path
from ase.io import read


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

    return results

