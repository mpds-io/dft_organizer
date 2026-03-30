from pathlib import Path
import shutil
from enum import StrEnum, unique

from aiida.orm import load_node, QueryBuilder, CalcJobNode
from aiida_crystal_dft.io.d12 import D12
from aiida import load_profile

load_profile()

from dft_organizer.core import compress_with_7z, extract_7z

@unique
class CalcLabel(StrEnum):
    ELECTRON = 'ELECTRON'
    PHONON = 'PHONON'
    HFORM = 'HFORM'
    ELASTIC = 'ELASTIC'
    TRANSPORT = 'TRANSPORT'
    STRUCT = 'STRUCT'


FILES_FOR_TYPE = {
    CalcLabel.ELECTRON: ['BAND.DAT', 'DOSS.DAT', 'fort.25'],
    CalcLabel.STRUCT: ['fort.34', 'fort.9'],
    CalcLabel.TRANSPORT: ['SEEBECK.DAT', 'SIGMA.DAT', 'README.txt'],
}


def calculations_for_label(label: str):
    "Searches AiiDA database for calculations with given label and returns dict {label: uuid}"
    qb = QueryBuilder()
    qb.append(
        CalcJobNode,
        filters={'label': {'like': f'%{label}%'}},
        project=['label', 'uuid']
    )
    return {lbl: uuid for lbl, uuid in qb.iterall()}


def get_files(calc_label, uuid, root_folder):
    """
    Copies relevant files from AiiDA repository for calculation 
    with given uuid to a structured folder in root_folder.
    """
    calc = load_node(uuid)
    repo_folder = calc.outputs.retrieved

    # Определяем тип расчета по лейблу
    label_lower = calc_label.lower()
    if 'band' in label_lower or 'doss' in label_lower or 'fort.25' in label_lower:
        calc_type = CalcLabel.ELECTRON
    elif 'geometry' in label_lower or 'fort.34' in label_lower:
        calc_type = CalcLabel.STRUCT
    elif 'transport' in label_lower or 'seebeck' in label_lower or 'sigma' in label_lower:
        calc_type = CalcLabel.TRANSPORT
    else:
        print(f"Warning: cannot determine type for {calc_label}, skipping")
        return

    dst_folder = Path(root_folder) / calc_type.value
    dst_folder.mkdir(parents=True, exist_ok=True)

    input_dict = calc.inputs.parameters.get_dict()
    input_path = dst_folder / 'INPUT'
    if 'properties' not in label_lower:
        # CRYSTAL run
        basis_family = calc.inputs.basis_family
        basis_family.set_structure(calc.inputs.structure)
        input_d12 = D12(input_dict, basis_family)
        input_path.write_text(str(input_d12))
    else:
        from aiida_crystal_dft.io.d3 import D3
        d3 = D3(parameters=input_dict)
        with input_path.open('w') as f:
            d3.write(f)

    output_files_in_repo = repo_folder.list_object_names()
    output_dst = dst_folder / 'OUTPUT'
    if 'OUTPUT' in output_files_in_repo:
        with repo_folder.open('OUTPUT', 'rb') as src, output_dst.open('wb') as dst:
            shutil.copyfileobj(src, dst)
    elif '_scheduler-stderr.txt' in output_files_in_repo:
        with repo_folder.open('_scheduler-stderr.txt', 'rb') as src, output_dst.open('wb') as dst:
            shutil.copyfileobj(src, dst)
    else:
        print(f"Warning: no OUTPUT or _scheduler-stderr.txt found in {repo_folder}")

    # check which files are relevant for this type of calculation and copy them
    for fname in FILES_FOR_TYPE[calc_type]:
        if fname in output_files_in_repo:
            with repo_folder.open(fname, 'rb') as src, (dst_folder / fname).open('wb') as dst:
                shutil.copyfileobj(src, dst)

    print(f"Files for '{calc_label}' (uuid={uuid}) copied to {dst_folder}")
    print(f"Available files in repo_folder: {output_files_in_repo}")
    
def launch_aiida_export(label: str = 'ZnSe/216', root_folder: str = 'examples/aiida_test_files', calc_folder_name: str = 'externalArchive', archive_name: str = 'calc.7z'):
    """
    Collects files from AiiDA calculations, distributes them by type into subfolders, and archives them.

    Structure:
    root_folder/
        calc_folder_name/
            ELECTRON/
            STRUCT/
            TRANSPORT/
    """
    # create externalArchive
    external_folder = Path(root_folder) / calc_folder_name
    external_folder.mkdir(parents=True, exist_ok=True)

    for calc_type in [CalcLabel.ELECTRON, CalcLabel.STRUCT, CalcLabel.TRANSPORT]:
        (external_folder / calc_type.value).mkdir(exist_ok=True)

    calcs = calculations_for_label(label)
    for label, uuid in calcs.items():
        get_files(label, uuid, external_folder)

    # archive (not removing original files, as they are in a separate folder)
    compress_with_7z(external_folder, Path(root_folder) / archive_name)

if __name__ == "__main__":
    ROOT_FOLDER = 'examples/aiida_test_files'
    ARCHIVE_FILE = Path(ROOT_FOLDER).parent / 'calc.7z'

    launch_aiida_export(label='ZnSe/216', root_folder=ROOT_FOLDER, calc_folder_name='externalArchive', archive_name='calc.7z')
    extract_7z(Path(ARCHIVE_FILE), Path(ROOT_FOLDER).parent)