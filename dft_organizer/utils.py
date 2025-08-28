
from dft_organizer.crystal_parser.summary import parse_content as parse_crystal_output
from dft_organizer.fleur_parser.summary import parse_fleur_output
import pandas as pd


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