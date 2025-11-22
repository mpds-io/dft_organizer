import re
from masci_tools.io.parsers.fleur import outxml_parser
from pathlib import Path


def parse_fleur_out_xml(filename: Path, large_symmary: bool = False) -> dict:
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
    results["cpu_time"] = walltime_sec / 3600 if walltime_sec else float("nan")

    results["bandgap"] = parsed_data.get("bandgap", float("nan"))

    # no information about charges in out.xml, set to nan
    results["s_pop"] = float("nan")
    results["p_pop"] = float("nan")
    results["d_pop"] = float("nan")
    results["total_pop"] = float("nan")

    if large_symmary:
        results["fermi_energy"] = parsed_data.get("fermi_energy", float("nan"))
        results["number_of_iterations"] = parsed_data.get("number_of_iterations", 0)
        results["density_convergence"] = parsed_data.get(
            "density_convergence", float("nan")
        )

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
        results["cpu_time"] = float(time_match.group(1)) / 3600

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
    if charges_match:
        populations = [float(x) for x in charges_match.groups()]
        results["s_pop"] = populations[0]
        results["p_pop"] = populations[1]
        results["d_pop"] = populations[2]
        results["total_pop"] = populations[4]

    return results


def get_fleur_table_string(fleur_res: dict):
    "Create a formatted table string from FLEUR results"
    lines = []
    lines.append(f"{'Parameter':<20} {'Value':<20}")
    lines.append("-" * 40)

    for key, label in [
        ("total_energy", "Total Energy (a.u.)"),
        ("cpu_time", "Calculation Time (h)"),
        ("s_pop", "s-population"),
        ("p_pop", "p-population"),
        ("d_pop", "d-population"),
        ("total_pop", "Total population"),
        ("bandgap", "Band Gap (eV)"),
    ]:
        val = fleur_res.get(key, "N/A")
        lines.append(f"{label:<20} {val:<20}")

    return "\n".join(lines)
