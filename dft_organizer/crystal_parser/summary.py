from pathlib import Path

from pycrystal import CRYSTOUT, CRYSTOUT_Error


def parse_crystal_output(path: Path):
    """Parse CRYSTAL output file safely using dictionary-style access"""
    try:
        content: dict = CRYSTOUT(str(path)).info
    except CRYSTOUT_Error as e:
        print(f"CRYSTAL OUTPUT file: {path} is not readable!")
        return {
            'bandgap': None,
            'cpu_time': None,
            'total_energy': None,
            's_pop': None,
            'p_pop': None,
            'd_pop': None,
            'total_pop': None
        }

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

if __name__ == "__main__":
    res = parse_crystal_output("/root/projects/dft_organizer/playground_data/20250701_124402_81/OUTPUT")
    print(res)
