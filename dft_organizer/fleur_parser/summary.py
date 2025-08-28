import re

def parse_fleur_output(filename):
    """
    Parse FLEUR output file and return results dictionary
    """
    try:
        with open(filename, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
    except Exception as e:
        print(f"Error reading file {filename}: {e}")
        return {}

    results = {}

    energy_match = re.search(r'total energy=\s*([-\d\.E+]+)', content)
    if energy_match:
        results['total_energy'] = float(energy_match.group(1))

    time_match = re.search(r'Total execution time:\s*(\d+)sec', content)
    if time_match:
        results['cpu_time'] = float(time_match.group(1))

    bandgap_match = re.search(r'bandgap\s*:\s*([\d\.E+-]+)\s*htr', content, re.IGNORECASE)
    if not bandgap_match:
        bandgap_match = re.search(r'FERHIS:\s*Fermi-Energy by histogram:\s*bandgap\s*:\s*([\d\.E+-]+)\s*htr',
                                 content, re.IGNORECASE)

    if bandgap_match:
        results['bandgap'] = float(bandgap_match.group(1)) * 27.2114  # convert Hartree -> eV

    charges_match = re.search(
        r'l-like charge.*?1\s+([\d\.]+)\s+([\d\.]+)\s+([\d\.]+)\s+([\d\.]+)\s+([\d\.]+)', content, re.DOTALL)
    if charges_match:
        populations = [float(x) for x in charges_match.groups()]
        results['s_pop'] = populations[0]
        results['p_pop'] = populations[1]
        results['d_pop'] = populations[2]
        results['total_pop'] = populations[4]

    return results


def get_fleur_table_string(fleur_res):
    "Create a formatted table string from FLEUR results"
    lines = []
    lines.append(f"{'Parameter':<20} {'FLEUR':<20}")
    lines.append("-"*40)

    for key, label in [('total_energy', 'Total Energy (a.u.)'),
                       ('cpu_time', 'Calculation Time (s)'),
                       ('s_pop', 's-population'),
                       ('p_pop', 'p-population'),
                       ('d_pop', 'd-population'),
                       ('total_pop', 'Total population'),
                       ('bandgap', 'Band Gap (eV)')]:
        val = fleur_res.get(key, 'N/A')
        lines.append(f"{label:<20} {val:<20}")

    return "\n".join(lines)


fleur_res = parse_fleur_output("output_fleur/20250623_171647_827/out")
table_str = get_fleur_table_string(fleur_res)
print(table_str)
