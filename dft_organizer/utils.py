
import pandas as pd

from dft_organizer.crystal_parser.summary import parse_crystal_output
from dft_organizer.fleur_parser.summary import parse_fleur_output


def get_table_string(res: dict):
    """Builds a table string from results"""
    lines = []
    lines.append(f"{'Parameter':<20} {'Value':<20}")
    lines.append("-"*40)

    for key, label in [('total_energy', 'Total Energy (a.u.)'),
                       ('cpu_time', 'Calculation Time (h)'),
                       ('s_pop', 's-population'),
                       ('p_pop', 'p-population'),
                       ('d_pop', 'd-population'),
                       ('total_pop', 'Total population'),
                       ('bandgap', 'Band Gap (eV)')]:
        val = res.get(key, 'N/A')
        lines.append(f"{label:<20} {val if val is not None else 'N/A':<20}")

    return "\n".join(lines)

def detect_engine(filenames: list) -> str:
    """Detect DFT engine based on presence of specific files"""
    if 'OUTPUT' in filenames or 'INPUT' in filenames:
        return 'crystal'
    elif 'fleur.out' in filenames or 'inp.xml' in filenames or 'out' in filenames:
        return 'fleur'
    else:
        # by default assume crystal
        return 'crystal'
    
    
def create_summary_table(path_dict: dict):
    """Create summary table comparing CRYSTAL and FLEUR results
    
    Args:
        path_dict (dict): Dictionary with formula as keys and paths to output files as values.
                          Example: {'H': {'crystal': 'path/to/OUTPUT', 'fleur': 'path/to/out'}, ...}
    Returns:
        pd.DataFrame: DataFrame summarizing CPU time and bandgap from both codes."""
    
    summary_data = []
    for formula, paths in path_dict.items():
        row_data = {'Element': formula}
        crystal_file = paths.get('crystal')
        fleur_file = paths.get('fleur')

        if crystal_file:
            if formula == 'P':
                print()
            crystal_res = parse_crystal_output(crystal_file)
            row_data.update({
                'CRYSTAL_Time': crystal_res.get('cpu_time', 'N/A'),
                'CRYSTAL_Bandgap': crystal_res.get('bandgap', 'N/A')
            })
        else:
            row_data.update({'CRYSTAL_Time':'N/A','CRYSTAL_Bandgap':'N/A'})

        if fleur_file:
            fleur_res = parse_fleur_output(fleur_file)
            row_data.update({
                'FLEUR_Time': fleur_res.get('cpu_time', 'N/A'),
                'FLEUR_Bandgap': fleur_res.get('bandgap', 'N/A')
            })
        else:
            row_data.update({'FLEUR_Time':'N/A','FLEUR_Bandgap':'N/A'})

        summary_data.append(row_data)
    return pd.DataFrame(summary_data)