from pathlib import Path
import shutil
import re
from datetime import datetime
from enum import StrEnum, unique

from aiida.orm import load_node, QueryBuilder, CalcJobNode
from aiida_crystal_dft.io.d12 import D12
from aiida import load_profile as load_aiida_profile

from dft_organizer.core import compress_with_7z, extract_7z

_aiida_loaded = False

def _ensure_aiida():
    global _aiida_loaded
    if not _aiida_loaded:
        load_aiida_profile()
        _aiida_loaded = True


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
    CalcLabel.TRANSPORT: ['SEEBECK.DAT', 'SIGMA.DAT', 'SIGMAS.DAT', 'KAPPA.DAT', 'TDF.DAT', 'README.txt'],
}

_CRYSTAL_SYSTEMS = {
    (1, 2): 'a',
    (3, 15): 'm',
    (16, 74): 'o',
    (75, 142): 't',
    (143, 194): 'h',
    (195, 230): 'c',
}

def _crystal_letter(spg: int) -> str:
    for (lo, hi), letter in _CRYSTAL_SYSTEMS.items():
        if lo <= spg <= hi:
            return letter
    return 'a'


def _get_reduced_formula(ase_atoms) -> str:
    from collections import Counter
    import math
    symbols = ase_atoms.get_chemical_symbols()
    order = list(dict.fromkeys(symbols))
    cnt = Counter(symbols)
    g = 0
    for v in cnt.values():
        g = math.gcd(g, v) if g else v
    if g > 1:
        cnt = {k: v // g for k, v in cnt.items()}
    return ''.join(k if cnt[k] == 1 else f'{k}{cnt[k]}' for k in order)


def _get_structure_metadata(uuid: str) -> tuple:
    """
    From an AiiDA calc UUID, load the input structure and determine:
    (chemical_formula, space_group_number, pearson_symbol).
    Falls back to provenance resolution if no input structure.
    """
    try:
        calc = load_node(uuid)
        struct = calc.inputs.structure
        ase_atoms = struct.get_ase()
        formula = _get_reduced_formula(ase_atoms)

        import spglib
        dataset = spglib.get_symmetry_dataset((
            ase_atoms.cell,
            ase_atoms.positions,
            ase_atoms.get_atomic_numbers(),
        ))
        if dataset is None:
            return formula, None, None

        spg = dataset.number
        centering = dataset.international[0] if dataset.international else 'P'
        natoms = len(dataset.std_types)
        pearson = f"{_crystal_letter(spg)}{centering}{natoms}"
        return formula, spg, pearson
    except Exception:
        pass

    return _resolve_from_provenance(uuid)


def _resolve_from_provenance(uuid: str) -> tuple:
    """
    Walk up AiiDA provenance to find material info for calcs without structure.
    Returns (formula, spg, None) or (None, None, None).
    """
    import re
    try:
        calc = load_node(uuid)
        caller = calc.caller
        if caller and caller.caller:
            gp = caller.caller
            m = re.match(r'([A-Za-z]\w*)/(\d+)', gp.label or '')
            if m:
                return m.group(1), int(m.group(2)), None
    except Exception:
        pass
    return None, None, None


def _sanitize(name: str) -> str:
    return re.sub(r'[^a-zA-Z0-9_.-]', '_', name).strip('_')


def _url_safe(name: str) -> str:
    return re.sub(r'[^a-zA-Z0-9_.-]', '', name)


def _extract_base_formula(label: str) -> str:
    return label.split('/')[0] if '/' in label else label


def _build_date_filter(from_date: str | None, to_date: str | None) -> dict:
    """Build AiiDA filter dict for ctime range. Dates in YYYY-MM-DD format."""
    filt = {}
    if from_date:
        filt['>='] = datetime.strptime(from_date, '%Y-%m-%d')
    if to_date:
        filt['<='] = datetime.strptime(to_date, '%Y-%m-%d')
    return filt


def _determine_calc_type(calc_label: str) -> CalcLabel | None:
    label_lower = calc_label.lower()
    if any(kw in label_lower for kw in ('band', 'doss', 'fort.25')):
        return CalcLabel.ELECTRON
    if any(kw in label_lower for kw in ('phonon', 'elastic')):
        return CalcLabel.STRUCT
    if any(kw in label_lower for kw in ('geometry', 'fort.34', 'fort.9')):
        return CalcLabel.STRUCT
    if any(kw in label_lower for kw in ('transport', 'seebeck', 'sigma')):
        return CalcLabel.TRANSPORT
    return None


def _guess_calc_type_from_files(repo_folder) -> CalcLabel | None:
    names = set(repo_folder.list_object_names())
    transport_files = {'SEEBECK.DAT', 'KAPPA.DAT', 'SIGMAS.DAT', 'TDF.DAT', 'SIGMA.DAT'}
    electron_files = {'BAND.DAT', 'DOSS.DAT', 'fort.25'}
    struct_files = {'fort.34', 'fort.9'}
    if names & transport_files:
        return CalcLabel.TRANSPORT
    if names & electron_files:
        return CalcLabel.ELECTRON
    if names & struct_files:
        return CalcLabel.STRUCT
    return None


def calculations_for_label(label: str, from_date: str | None = None, to_date: str | None = None) -> dict:
    """Exact match on label + optional ctime range, returns {label: [uuid, ...]}"""
    _ensure_aiida()
    filters = {'label': {'==': label}}
    date_filter = _build_date_filter(from_date, to_date)
    if date_filter:
        filters['ctime'] = date_filter
    qb = QueryBuilder()
    qb.append(CalcJobNode, filters=filters, project=['label', 'uuid'])
    result = {}
    for lbl, uuid in qb.iterall():
        result.setdefault(lbl, []).append(uuid)
    return result


def all_systems(from_date: str | None = None, to_date: str | None = None) -> dict[str, list]:
    """
    Group CalcJobNodes by material (formula+spg+pearson).
    Calcs without structure are resolved via provenance and merged
    with the correct material group if pearson can be inherited.
    Returns {archive_label: [(label, uuid), ...]}.
    """
    _ensure_aiida()
    filters = {}
    date_filter = _build_date_filter(from_date, to_date)
    if date_filter:
        filters['ctime'] = date_filter
    qb = QueryBuilder()
    qb.append(CalcJobNode, filters=filters or None, project=['label', 'uuid'])

    all_meta = {}
    for lbl, uuid in qb.iterall():
        formula, spg, pearson = _get_structure_metadata(uuid)
        all_meta[uuid] = (lbl, formula, spg, pearson)

    # Propagate pearson: for calcs resolved via provenance (spg but no pearson),
    # find any sibling calc with same (formula, spg) that has pearson
    pearson_map = {}
    for uuid, (lbl, formula, spg, pearson) in all_meta.items():
        if formula and spg and pearson:
            pearson_map[(formula, spg)] = pearson

    for uuid, (lbl, formula, spg, pearson) in all_meta.items():
        if formula and spg and not pearson:
            key = (formula, spg)
            if key in pearson_map:
                all_meta[uuid] = (lbl, formula, spg, pearson_map[key])

    # Second pass: for calcs still without pearson, try formula-only match
    # (provenance spg may differ from spglib-standardized spg of same material)
    import re as _re
    def _norm_f(f):
        return ''.join(sorted(_re.findall(r'[A-Z][a-z]*', f)))

    formula_pearson_map = {}
    for uuid, (lbl, formula, spg, pearson) in all_meta.items():
        if formula and pearson:
            formula_pearson_map[_norm_f(formula)] = (formula, spg, pearson)

    for uuid, (lbl, formula, spg, pearson) in all_meta.items():
        if formula and not pearson:
            nf = _norm_f(formula)
            if nf in formula_pearson_map:
                match_f, match_spg, match_pearson = formula_pearson_map[nf]
                all_meta[uuid] = (lbl, match_f, match_spg, match_pearson)

    groups = {}
    for uuid, (lbl, formula, spg, pearson) in all_meta.items():
        if spg and pearson:
            key = f"{formula}_{spg}_{pearson}"
        elif spg:
            key = f"{formula}_{spg}"
        elif formula:
            key = _sanitize(formula)
        else:
            key = _extract_base_formula(lbl)
        groups.setdefault(key, []).append((lbl, uuid))
    return groups


def _copy_file(repo_folder, fname, dst):
    if fname in repo_folder.list_object_names():
        with repo_folder.open(fname, 'rb') as src, dst.open('wb') as dst_f:
            shutil.copyfileobj(src, dst_f)
        return True
    return False


def get_files(calc_label: str, uuid: str, dst_folder: Path) -> bool:
    """
    Copy relevant files from AiiDA repository to dst_folder/<TYPE>/.
    Returns True if any files were copied.
    """
    _ensure_aiida()
    calc = load_node(uuid)
    repo_folder = calc.outputs.retrieved

    calc_type = _determine_calc_type(calc_label)
    if calc_type is None:
        calc_type = _guess_calc_type_from_files(repo_folder)
    if calc_type is None:
        print(f"Warning: unknown calc type for '{calc_label}', skipping")
        return False

    type_folder = dst_folder / calc_type.value
    type_folder.mkdir(parents=True, exist_ok=True)
    copied_any = False

    try:
        input_dict = calc.inputs.parameters.get_dict()
        input_path = type_folder / 'INPUT'
        try:
            basis_family = calc.inputs.basis_family
            basis_family.set_structure(calc.inputs.structure)
            input_d12 = D12(input_dict, basis_family)
            input_path.write_text(str(input_d12))
            copied_any = True
        except Exception as e:
            print(f"Warning: could not write INPUT for '{calc_label}': {e}")
    except Exception:
        print(f"  (no parameters input for '{calc_label}', skipping INPUT)")

    output_files_in_repo = repo_folder.list_object_names()
    output_dst = type_folder / 'OUTPUT'
    if 'OUTPUT' in output_files_in_repo:
        with repo_folder.open('OUTPUT', 'rb') as src, output_dst.open('wb') as dst:
            shutil.copyfileobj(src, dst)
        copied_any = True
    elif '_scheduler-stderr.txt' in output_files_in_repo:
        with repo_folder.open('_scheduler-stderr.txt', 'rb') as src, output_dst.open('wb') as dst:
            shutil.copyfileobj(src, dst)
        copied_any = True
    else:
        print(f"Warning: no OUTPUT or _scheduler-stderr.txt in {repo_folder}")

    for fname in FILES_FOR_TYPE.get(calc_type, []):
        if _copy_file(repo_folder, fname, type_folder / fname):
            copied_any = True

    print(f"Files for '{calc_label}' (uuid={uuid}) copied to {type_folder}")
    return copied_any


def generate_readme(system_formula: str, spg: int | None, pearson: str | None, root_folder: Path) -> None:
    """Write README.txt in exact MPDS format"""
    safe = _url_safe(system_formula)
    if spg and pearson:
        phase_url = f"https://mpds.io/phase/{safe}/{spg}/{pearson}"
        archive_url = f"https://mpds.io/calculations/{safe}_{spg}_{pearson}.7z"
    else:
        phase_url = f"https://mpds.io/phase/{safe}"
        archive_url = f"https://mpds.io/calculations/{safe}.7z"

    lines = [
        "In-house MPDS / PAULING FILE ab initio calculations data",
        "(c) by Sobolev, Civalleri, Maschio, Erba, Dovesi, Villars, Blokhin",
        "",
        "Please, cite as:",
        "Sobolev, Civalleri, Maschio, Erba, Dovesi, Villars, Blokhin,",
        phase_url,
        archive_url,
        "",
        "These data are licensed under a Creative Commons Attribution 4.0 International License.",
        "http://creativecommons.org/licenses/by/4.0",
        "",
        "The calculations are done using the CRYSTAL code:",
        "Dovesi, Erba, Orlando, Zicovich-Wilson, Civalleri, Maschio, Rerat, Casassa,",
        "Baima, Salustro, Kirtman. WIREs Comput Mol Sci. (2018),",
        "https://doi.org/10.1002/wcms.1360",
        "Dovesi, Saunders, Roetti, Orlando, Zicovich-Wilson, Pascale, Civalleri, Doll,",
        "Harrison, Bush, D'Arco, Llunell, Causa, Noel, Maschio, Erba, Rerat, Casassa.",
        "CRYSTAL17 User Manual (University of Turin, 2017), http://www.crystal.unito.it",
        "",
        "The automation is done using the AiiDA code:",
        "Pizzi, Cepellotti, Sabatini, Marzari, Kozinsky. Comp Mat Sci (2016),",
        "https://doi.org/10.1016/j.commatsci.2015.09.013",
    ]
    (root_folder / 'README.txt').write_text('\n'.join(lines))


def _is_calc_failed(uuid: str) -> bool:
    from aiida.orm import load_node
    calc = load_node(uuid)
    exit_status = calc.exit_status
    return exit_status is not None and exit_status != 0


def export_system(calcs: list, output_dir: Path, skip_errors: bool = False) -> bool:
    """
    Export a system: copy files, write README, create 7z archive.
    Archive is named {formula}_{spg}_{pearson}.7z per MPDS convention.
    calcs is a list of (label, uuid) tuples.
    Returns True on success.
    """
    _ensure_aiida()

    formula, spg, pearson = None, None, None
    for lbl, uuid in calcs:
        formula, spg, pearson = _get_structure_metadata(uuid)
        if formula:
            break
    if not formula and calcs:
        formula = _extract_base_formula(calcs[0][0])
    if not formula:
        print("No formula could be determined, skipping")
        return False

    if spg and pearson:
        dir_name = f"{formula}_{spg}_{pearson}"
    else:
        dir_name = _sanitize(formula)
    archive_name = f"{dir_name}.7z"

    work_dir = output_dir / dir_name
    archive_path = output_dir / archive_name
    existed_before = archive_path.exists()

    if existed_before:
        work_dir.mkdir(parents=True, exist_ok=True)
        extract_7z(archive_path, work_dir)
        archive_path.unlink()
    elif work_dir.exists():
        shutil.rmtree(work_dir)
        work_dir.mkdir(parents=True, exist_ok=True)
    else:
        work_dir.mkdir(parents=True, exist_ok=True)

    any_copied = False
    try:
        for lbl, uuid in calcs:
            if skip_errors and _is_calc_failed(uuid):
                print(f"  (skipping failed calc '{lbl}', uuid={uuid[:8]})")
                continue
            if get_files(lbl, uuid, work_dir):
                any_copied = True

        if not any_copied and not existed_before:
            print(f"No files copied for '{formula}', skipping archive creation")
            return False

        generate_readme(formula, spg, pearson, work_dir)

        success = compress_with_7z(work_dir, archive_path)
        if success:
            print(f"Archive created: {archive_path}")
        return success
    finally:
        if work_dir.exists():
            shutil.rmtree(work_dir, ignore_errors=True)


def launch_aiida_export(
    label: str | None = None,
    export_all: bool = False,
    output_dir: str | Path = '/tmp',
    from_date: str | None = None,
    to_date: str | None = None,
    skip_errors: bool = False,
) -> None:
    """
    Collect files from AiiDA calculations and create MPDS-format 7z archives.

    Archives are named {formula}_{spg}_{pearson}.7z per MPDS convention.
    Each contains ELECTRON/, STRUCT/, TRANSPORT/ subfolders and a README.txt.

    Provide --label for a single system (exact match), or --export-all for all.
    Use --from-date / --to-date to filter by creation date (YYYY-MM-DD).
    """
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    if export_all:
        systems = all_systems(from_date=from_date, to_date=to_date)
        if not systems:
            print("No calculations found in AiiDA database.")
            return
        print(f"Found {len(systems)} unique systems. Starting export...")
        sorted_names = sorted(systems, key=str.casefold)
        for sys_name in sorted_names:
            calcs = systems[sys_name]
            export_system(calcs, output_dir, skip_errors=skip_errors)
        print(f"Export complete. Archives saved to {output_dir}")
        return

    if not label:
        print("Provide --label or use --export-all")
        return

    calcs = calculations_for_label(label, from_date=from_date, to_date=to_date)
    if not calcs:
        print(f"Error: no calculations found with label '{label}' in AiiDA database.")
        return

    flat = [(lbl, uuid) for lbl, uuids in calcs.items() for uuid in uuids]
    export_system(flat, output_dir, skip_errors=skip_errors)
