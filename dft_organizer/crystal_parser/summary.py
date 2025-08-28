from pycrystal import CRYSTOUT
from pathlib import Path

def parse_content(path: Path):
    """Parse CRYSTAL output file safely using dictionary-style access"""
    content: dict = CRYSTOUT(path).info  

    # electrons -> basis_set -> bs
    mulliken_dict = {}
    if 'electrons' in content and 'basis_set' in content['electrons'] and 'bs' in content['electrons']['basis_set']:
        mulliken_dict = content['electrons']['basis_set']['bs']

    def sum_orbital(orb_type):
        total = 0.0
        for atom, shells in mulliken_dict.items():
            for shell in shells:
                if not shell or shell[0] != orb_type:
                    continue
                for pair in shell[1:]:
                    if len(pair) >= 2:
                        total += pair[1]
        return total

    s_pop = sum_orbital('S')
    p_pop = sum_orbital('P')
    d_pop = sum_orbital('D')
    total_pop = s_pop + p_pop + d_pop

    # bandgap
    bandgap = None
    if 'conduction' in content and isinstance(content['conduction'], list) and len(content['conduction']) > 0:
        bandgap = content['conduction'][-1].get('band_gap', None)

    # duration, energy 
    try:
        cpu_time = float(content['duration'])
    except:
        cpu_time = None
    total_energy = content.get('energy', None)

    return {
        'bandgap': bandgap,
        'cpu_time': cpu_time,
        'total_energy': total_energy,
        's_pop': s_pop,
        'p_pop': p_pop,
        'd_pop': d_pop,
        'total_pop': total_pop
    }

def get_crystal_table_string(crystal_res: dict):
    """Builds a table string from CRYSTAL results"""
    lines = []
    lines.append(f"{'Parameter':<20} {'CRYSTAL23':<20}")
    lines.append("-"*40)

    for key, label in [('total_energy', 'Total Energy (a.u.)'),
                       ('cpu_time', 'Calculation Time (s)'),
                       ('s_pop', 's-population'),
                       ('p_pop', 'p-population'),
                       ('d_pop', 'd-population'),
                       ('total_pop', 'Total population'),
                       ('bandgap', 'Band Gap (eV)')]:
        val = crystal_res.get(key, 'N/A')
        lines.append(f"{label:<20} {val if val is not None else 'N/A':<20}")

    return "\n".join(lines)

if __name__ == "__main__":
    res = parse_content("output_crystal/20250628_115541_8/OUTPUT")
    table = get_crystal_table_string(res)
    print(table)
