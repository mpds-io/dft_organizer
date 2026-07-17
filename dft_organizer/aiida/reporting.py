from datetime import datetime
from pathlib import Path
from typing import Any

import json
import shutil
import tempfile
import polars as pl
from aiida import load_profile as load_aiida_profile
from aiida.orm import QueryBuilder, CalcJobNode, Computer, load_node, StructureData
import pg8000
import numpy as np

from dft_organizer.aiida.aiida_links_tree import (
    load_db_config,
    fetch_tree_from_db,
    find_first_last_structure_uuids,
)
from dft_organizer.aiida.export import determine_calc_type_summary
from dft_organizer.crystal_parser import parse_phonon_from_output
from dft_organizer.crystal_parser.parse_properties import parse_seebeck_first_line


_aiida_loaded = False


def _ensure_aiida():
    global _aiida_loaded
    if not _aiida_loaded:
        load_aiida_profile()
        _aiida_loaded = True


from dft_organizer.pricing import get_cloud_rate, get_cost


def _fetch_fleur_seebeck(calc) -> dict | None:
    node = calc
    while node is not None:
        ptype = getattr(node, 'process_type', '') or ''
        if 'FleurDOSLocalWorkChain' in ptype:
            try:
                sd = node.outputs.output_seebeck.get_dict()
                pd = node.outputs.output_dos_local_wc_para.get_dict()
                return {
                    "seebeck_coefficient_uvk": sd.get("seebeck_coefficient_uvk"),
                    "mu_ev": sd.get("mu_ev"),
                    "temperature_k": pd.get("temperature_k"),
                }
            except Exception:
                return None
        node = getattr(node, 'caller', None)
    return None


def _get_structure_from_uuid(uuid: str) -> StructureData:
    node = load_node(uuid)
    if isinstance(node, StructureData):
        return node
    if hasattr(node, "outputs") and "structure" in node.outputs:
        out = node.outputs["structure"]
        if isinstance(out, StructureData):
            return out
    raise ValueError(f"Node {uuid} does not provide a StructureData")


def _structure_displacement_ase(atoms_init, atoms_final) -> dict:
    pos_init = atoms_init.get_positions()
    pos_final = atoms_final.get_positions()
    if pos_init.shape != pos_final.shape:
        raise ValueError("Initial and final structures have different sizes/order")
    disp = pos_final - pos_init
    sq = np.sum(disp**2, axis=1)
    return {
        "sum_sq_disp": float(np.sum(sq)),
        "rmsd_disp": float(np.sqrt(np.mean(sq))),
    }


def _get_fleur_displacement(calc, conn) -> dict:
    result = {
        "first_struct_uuid": None,
        "last_struct_uuid": None,
        "sum_sq_disp": None,
        "rmsd_disp": None,
    }

    try:
        links = fetch_tree_from_db(conn, calc.pk)
        first_s_uuid, last_s_uuid = find_first_last_structure_uuids(links)
    except Exception:
        return result

    if first_s_uuid is None or last_s_uuid is None:
        return result

    result["first_struct_uuid"] = first_s_uuid
    result["last_struct_uuid"] = last_s_uuid

    try:
        first_struct = _get_structure_from_uuid(first_s_uuid)
        last_struct = _get_structure_from_uuid(last_s_uuid)
        disp = _structure_displacement_ase(first_struct.get_ase(), last_struct.get_ase())
        result["sum_sq_disp"] = round(disp["sum_sq_disp"], 2)
        result["rmsd_disp"] = round(disp["rmsd_disp"], 2)
    except Exception:
        pass

    return result


def _build_date_filter(from_date: str | None, to_date: str | None) -> dict:
    filt = {}
    if from_date:
        filt['>='] = datetime.strptime(from_date, '%Y-%m-%d')
    if to_date:
        filt['<='] = datetime.strptime(to_date, '%Y-%m-%d')
    return filt


def _formula_from_label(label: str | None) -> str | None:
    if not label or ":" not in label:
        return None
    candidate = label.split(":")[0].strip()
    if not candidate or len(candidate) > 15:
        return None
    if not candidate[0].isupper():
        return None
    return candidate


def _formula_from_workchain_label(label: str | None) -> str | None:
    """Extract a chemical formula from a workchain label like
    ``'MgO/225 seebeck pipeline'`` (``'/'``-separated, first field)."""
    if not label or "/" not in label:
        return None
    candidate = label.split("/")[0].strip()
    if not candidate or len(candidate) > 15:
        return None
    if not candidate[0].isupper():
        return None
    return candidate


def _sgs_from_workchain_label(label: str | None) -> int | None:
    """Extract space-group number from a workchain label like
    ``'Co2As/189 Seebeck direct'`` (integer after ``'/'``)."""
    if not label or "/" not in label:
        return None
    rest = label.split("/", 1)[1].strip()
    if not rest:
        return None
    token = rest.split()[0] if " " in rest else rest
    try:
        return int(token)
    except (TypeError, ValueError):
        return None


def _apply_struct_attrs_to_summary(summary: dict, struct_attrs: dict) -> None:
    """Fill formula / cell / space_group into summary from StructureData attributes."""
    struct_info = _extract_struct_info(struct_attrs)
    for k in ("chemical_formula", "a", "b", "c", "alpha", "beta", "gamma",
              "cell", "positions", "numbers", "symbols"):
        if struct_info.get(k) is not None:
            summary[k] = struct_info[k]
    try:
        import spglib
        cell = struct_attrs.get('cell')
        kinds = struct_attrs.get('kinds', [])
        sites = struct_attrs.get('sites', [])
        kind_to_symbol = {k['name']: k['symbols'][0] for k in kinds if k.get('symbols')}
        symbols_list = [kind_to_symbol.get(s.get('kind_name', ''), '?') for s in sites]
        from ase.data import atomic_numbers as _ase_an
        numbers = [_ase_an.get(sym, 0) for sym in symbols_list]
        positions = [s.get('position', [0, 0, 0]) for s in sites]
        if cell and numbers:
            dataset = spglib.get_symmetry_dataset((cell, positions, numbers))
            if dataset is not None:
                summary["space_group"] = dataset.number
    except Exception:
        pass


def _get_struct_attrs_from_crystal_calc_uuid(uuid_str: str) -> dict | None:
    """Load the CRYSTAL SCF calc referenced by a ``crystal_calc_uuid`` Str
    input and return the attributes of its ``structure`` StructureData input.
    Returns ``None`` if anything is missing."""
    try:
        scf = load_node(uuid_str)
    except Exception:
        return None
    for link in scf.base.links.get_incoming().all():
        if link.link_label == 'structure':
            return link.node.attributes
    return None


def _extract_struct_info(attrs: dict | None) -> dict:
    result = {
        "chemical_formula": None,
        "a": None, "b": None, "c": None,
        "alpha": None, "beta": None, "gamma": None,
        "cell": None, "positions": None, "numbers": None, "symbols": None,
    }
    if not attrs:
        return result
    try:
        cell = attrs.get('cell')
        kinds = attrs.get('kinds', [])
        sites = attrs.get('sites', [])
        if not cell or not sites:
            return result

        import numpy as np
        cell_arr = np.array(cell)
        a_val = float(np.linalg.norm(cell_arr[0]))
        b_val = float(np.linalg.norm(cell_arr[1]))
        c_val = float(np.linalg.norm(cell_arr[2]))
        cos_alpha = np.dot(cell_arr[1], cell_arr[2]) / (b_val * c_val)
        cos_beta = np.dot(cell_arr[0], cell_arr[2]) / (a_val * c_val)
        cos_gamma = np.dot(cell_arr[0], cell_arr[1]) / (a_val * b_val)
        alpha_val = float(np.degrees(np.arccos(np.clip(cos_alpha, -1, 1))))
        beta_val = float(np.degrees(np.arccos(np.clip(cos_beta, -1, 1))))
        gamma_val = float(np.degrees(np.arccos(np.clip(cos_gamma, -1, 1))))

        kind_to_symbol = {k['name']: k['symbols'][0] for k in kinds if k.get('symbols')}
        symbols_list = [kind_to_symbol.get(s.get('kind_name', ''), '?') for s in sites]
        numbers_list = []
        from ase.data import atomic_numbers as ase_atomic_numbers
        for sym in symbols_list:
            numbers_list.append(ase_atomic_numbers.get(sym, 0))
        positions_list = [s.get('position', [0, 0, 0]) for s in sites]

        counts = {}
        for sym in symbols_list:
            counts[sym] = counts.get(sym, 0) + 1
        import math as _math
        g = 0
        for v in counts.values():
            g = _math.gcd(g, v) if g else v
        if g > 1:
            counts = {k: v // g for k, v in counts.items()}
        order = sorted(counts.keys())
        formula = ''.join(k if counts[k] == 1 else f'{k}{counts[k]}' for k in order)

        result["chemical_formula"] = formula
        result["a"] = round(a_val, 6)
        result["b"] = round(b_val, 6)
        result["c"] = round(c_val, 6)
        result["alpha"] = round(alpha_val, 6)
        result["beta"] = round(beta_val, 6)
        result["gamma"] = round(gamma_val, 6)
        result["cell"] = cell
        result["positions"] = positions_list
        result["numbers"] = numbers_list
        result["symbols"] = symbols_list
    except Exception:
        pass
    return result


def _engine_from_process_type(process_type: str | None) -> str | None:
    if not process_type:
        return None
    pt = process_type.lower()
    if 'crystal' in pt:
        return 'crystal'
    if 'fleur' in pt:
        return 'fleur'
    return None


def _get_struct_attrs_from_calc(calc) -> dict | None:
    try:
        struct = calc.inputs.structure
        return struct.base.attributes.all
    except Exception:
        pass
    node = getattr(calc, 'caller', None)
    visited = 0
    while node is not None and visited < 10:
        visited += 1
        try:
            struct = node.inputs.structure
            return struct.base.attributes.all
        except Exception:
            pass
        node = getattr(node, 'caller', None)
    return None


_null_summary_keys = [
    "a", "b", "c", "alpha", "beta", "gamma",
    "cell", "positions", "numbers", "symbols",
    "bandgap", "sum_sq_disp", "rmsd_disp", "output_path",
    "cost_eur", "hetzner_rate",
    "has_phonons", "phonon_freq_min", "phonon_freq_max",
    "phonon_n_imag", "phonon_modes_count",
]


def scan_aiida_calculations(
    label: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    skip_errors: bool = False,
    calc_type_filter: str | None = None,
    engine: str | None = None,
) -> list[dict[str, Any]]:
    """
    Query AiiDA CalcJobNodes and build a summary store for reporting.

    Similar to scan_calculations() but reads from AiiDA DB instead of local files.

    Parameters:
    - label: If set, only include this specific label (exact match)
    - from_date: Only include calcs created on or after this date (YYYY-MM-DD)
    - to_date: Only include calcs created on or before this date (YYYY-MM-DD)
    - skip_errors: Skip calculations with exit_status != 0
    - calc_type_filter: If set, pre-filter rows by label-based calc_type to skip
      expensive enrichment for rows that will be dropped anyway. Note that
      ``transport`` is special: ``scf`` rows are kept (they may be reclassified
      to ``transport`` during enrichment via ``SEEBECK.DAT``), so the final
      ``calc_type`` filtering must still be applied by the caller.
    - engine: If set ('crystal' or 'fleur'), only include calcs of that engine.

    Returns: list of summary dicts
    """
    _ensure_aiida()

    filters = {}
    if label:
        filters['label'] = {'==': label}
    date_filter = _build_date_filter(from_date, to_date)
    if date_filter:
        filters['ctime'] = date_filter
    if engine == 'crystal':
        filters['process_type'] = {'like': '%crystal%'}
    elif engine == 'fleur':
        filters['process_type'] = {'like': '%fleur%'}

    print("Querying AiiDA database...")
    qb = QueryBuilder()
    qb.append(CalcJobNode, tag='calc',
              filters=filters or None,
              project=['uuid', 'label', 'process_type', 'ctime', 'mtime', 'id', 'attributes'])
    qb.append(Computer, with_node='calc', project=['label'], outerjoin=True)

    rows = list(qb.iterall())
    print(f"Found {len(rows)} calculations in database.")

    summary_store = []
    fleur_uuids = []
    crystal_uuids = []

    for uuid, lbl, process_type, ctime, mtime, pk, attrs, comp in rows:
        exit_status = attrs.get('exit_status') if attrs else None
        exit_message = str(attrs.get('exit_message', '')) if attrs else ''

        if skip_errors and (exit_status is None or exit_status != 0):
            continue

        engine = _engine_from_process_type(process_type) or 'unknown'

        # Pre-filter by label-based calc_type to skip expensive enrichment.
        # transport is kept (scf rows may become transport via SEEBECK.DAT).
        if calc_type_filter and calc_type_filter != 'transport':
            pre_type = determine_calc_type_summary(lbl)
            if pre_type != calc_type_filter:
                continue

        duration = None
        if ctime and mtime:
            duration = round((mtime - ctime).total_seconds() / 3600, 4)

        summary = {
            "uuid": uuid,
            "label": lbl,
            "engine": engine,
            "calc_type": determine_calc_type_summary(lbl),
"chemical_formula": _formula_from_label(lbl),
            "duration": duration,
            "pk": pk,
            "computer": comp,
            "calc_date": ctime.strftime("%Y-%m-%d %H:%M:%S") if ctime else None,
            "exit_status": exit_status,
            "exit_message": exit_message,
        }
        for k in _null_summary_keys:
            summary[k] = None

        if comp:
            summary["hetzner_rate"] = get_cloud_rate(comp, provider="hetzner")
            cost = get_cost(duration, comp, provider="hetzner")
            if cost is not None:
                summary["cost_eur"] = cost

        if engine == 'fleur':
            fleur_uuids.append(uuid)
        elif engine == 'crystal':
            crystal_uuids.append(uuid)

        summary_store.append(summary)

    _enrich_with_structure_fast(summary_store, crystal_uuids, fleur_uuids)

    if crystal_uuids:
        print(f"Enriching {len(crystal_uuids)} CRYSTAL calculations (phonon, seebeck)...")
        _enrich_crystal_extras(summary_store, crystal_uuids)

    if fleur_uuids:
        print(f"Enriching {len(fleur_uuids)} FLEUR calculations (Seebeck, displacement)...")
        _enrich_fleur_extras(summary_store, fleur_uuids)

    return summary_store


def _enrich_with_structure_fast(
    summary_store: list[dict[str, Any]],
    crystal_uuids: list[str],
    fleur_uuids: list[str],
) -> None:
    crystal_uuid_set = list(crystal_uuids)
    fleur_uuid_set = set(fleur_uuids)

    print(f"Fetching structure data for {len(crystal_uuid_set)} CRYSTAL calcs (fast)...")
    if crystal_uuid_set:
        qb = QueryBuilder()
        qb.append(CalcJobNode, tag='calc',
                  filters={'uuid': {'in': crystal_uuid_set}},
                  project=['uuid'])
        qb.append(StructureData, with_incoming='calc', project=['attributes'], outerjoin=True)
        struct_map = {}
        for calc_uuid, struct_attrs in qb.iterall():
            if struct_attrs:
                struct_map[calc_uuid] = struct_attrs

        for summary in summary_store:
            if summary['uuid'] in crystal_uuid_set:
                struct_attrs = struct_map.get(summary['uuid'])
                if struct_attrs:
                    struct_info = _extract_struct_info(struct_attrs)
                    for k in ("chemical_formula", "a", "b", "c", "alpha", "beta", "gamma",
                               "cell", "positions", "numbers", "symbols"):
                        if struct_info.get(k) is not None:
                            summary[k] = struct_info[k]
                    try:
                        import spglib as _spglib
                        cell = struct_attrs.get('cell')
                        kinds = struct_attrs.get('kinds', [])
                        sites = struct_attrs.get('sites', [])
                        kind_to_symbol = {k['name']: k['symbols'][0] for k in kinds if k.get('symbols')}
                        symbols_list = [kind_to_symbol.get(s.get('kind_name', ''), '?') for s in sites]
                        from ase.data import atomic_numbers as _ase_an
                        numbers = [_ase_an.get(sym, 0) for sym in symbols_list]
                        positions = [s.get('position', [0, 0, 0]) for s in sites]
                        if cell and numbers:
                            dataset = _spglib.get_symmetry_dataset((cell, positions, numbers))
                            if dataset is not None:
                                summary["space_group"] = dataset.number
                    except Exception:
                        pass

    crystal_no_formula = [s for s in summary_store
                          if s['uuid'] in crystal_uuid_set
                          and not s.get('chemical_formula')]
    if crystal_no_formula:
        print(f"Fallback: fetching structure via provenance for {len(crystal_no_formula)} CRYSTAL calcs without formula...")
        done = 0
        for summary in crystal_no_formula:
            try:
                calc = load_node(summary['uuid'])
                struct_attrs = _get_struct_attrs_from_calc(calc)
                if struct_attrs:
                    struct_info = _extract_struct_info(struct_attrs)
                    for k in ("chemical_formula", "a", "b", "c", "alpha", "beta", "gamma",
                              "cell", "positions", "numbers", "symbols"):
                        if struct_info.get(k) is not None:
                            summary[k] = struct_info[k]
                    try:
                        import spglib as _spglib
                        cell = struct_attrs.get('cell')
                        kinds = struct_attrs.get('kinds', [])
                        sites = struct_attrs.get('sites', [])
                        kind_to_symbol = {k['name']: k['symbols'][0] for k in kinds if k.get('symbols')}
                        symbols_list = [kind_to_symbol.get(s.get('kind_name', ''), '?') for s in sites]
                        from ase.data import atomic_numbers as _ase_an
                        numbers = [_ase_an.get(sym, 0) for sym in symbols_list]
                        positions = [s.get('position', [0, 0, 0]) for s in sites]
                        if cell and numbers:
                            dataset = _spglib.get_symmetry_dataset((cell, positions, numbers))
                            if dataset is not None:
                                summary["space_group"] = dataset.number
                    except Exception:
                        pass
            except Exception:
                pass
            done += 1
            if done % 25 == 0:
                print(f"  CRYSTAL fallback: {done}/{len(crystal_no_formula)}")

    # Second fallback: for CRYSTAL calcs still without formula, try several
    # workchain-input sources (mpds_query, crystal_calc_uuid, workchain label).
    crystal_still_no_formula = [s for s in summary_store
                                if s['uuid'] in crystal_uuid_set
                                and not s.get('chemical_formula')]
    if crystal_still_no_formula:
        for summary in crystal_still_no_formula:
            try:
                calc = load_node(summary['uuid'])
                caller = calc.caller
                if caller is None:
                    continue
                cur = caller
                for _ in range(5):
                    for link in cur.base.links.get_incoming().all():
                        lbl = link.link_label
                        if lbl == 'mpds_query':
                            q = link.node
                            qd = q.get_dict() if hasattr(q, 'get_dict') else {}
                            formulae = qd.get('formulae')
                            sgs = qd.get('sgs')
                            if formulae and not summary.get('chemical_formula'):
                                summary['chemical_formula'] = formulae
                            if sgs and summary.get('space_group') is None:
                                try:
                                    summary['space_group'] = int(sgs)
                                except (TypeError, ValueError):
                                    pass
                        elif lbl == 'crystal_calc_uuid':
                            try:
                                scf_uuid = link.node.value
                                struct_attrs = _get_struct_attrs_from_crystal_calc_uuid(scf_uuid)
                                if struct_attrs:
                                    _apply_struct_attrs_to_summary(summary, struct_attrs)
                            except Exception:
                                pass
                    # workchain label at this level (e.g. 'Co2As/189 Seebeck direct')
                    if cur.label:
                        if not summary.get('chemical_formula'):
                            summary['chemical_formula'] = _formula_from_workchain_label(cur.label)
                        if summary.get('space_group') is None:
                            summary['space_group'] = _sgs_from_workchain_label(cur.label)
                    if summary.get('chemical_formula') and summary.get('space_group') is not None:
                        break
                    parents = [l.node for l in cur.base.links.get_incoming()
                                if l.link_type.name == 'CALL_WORK']
                    if not parents:
                        break
                    cur = parents[0]
            except Exception:
                pass

    if fleur_uuid_set:
        print(f"Fetching structure data for {len(fleur_uuid_set)} FLEUR calcs (via provenance)...")
        done = 0
        for summary in summary_store:
            if summary['uuid'] in fleur_uuid_set:
                try:
                    calc = load_node(summary['uuid'])
                    struct_attrs = _get_struct_attrs_from_calc(calc)
                    if struct_attrs:
                        struct_info = _extract_struct_info(struct_attrs)
                        for k in ("chemical_formula", "a", "b", "c", "alpha", "beta", "gamma",
                                   "cell", "positions", "numbers", "symbols"):
                            if struct_info.get(k) is not None:
                                summary[k] = struct_info[k]
                        try:
                            import spglib
                            cell = struct_attrs.get('cell')
                            kinds = struct_attrs.get('kinds', [])
                            sites = struct_attrs.get('sites', [])
                            kind_to_symbol = {k['name']: k['symbols'][0] for k in kinds if k.get('symbols')}
                            symbols_list = [kind_to_symbol.get(s.get('kind_name', ''), '?') for s in sites]
                            from ase.data import atomic_numbers as _ase_an
                            numbers = [_ase_an.get(sym, 0) for sym in symbols_list]
                            positions = [s.get('position', [0, 0, 0]) for s in sites]
                            if cell and numbers:
                                dataset = spglib.get_symmetry_dataset((cell, positions, numbers))
                                if dataset is not None:
                                    summary["space_group"] = dataset.number
                        except Exception:
                            pass
                except Exception:
                    pass
                done += 1
                if done % 25 == 0:
                    print(f"  FLEUR structure: {done}/{len(fleur_uuid_set)}")


def _retrieved_file_text(calc, fname: str) -> str | None:
    """Read a file from a CalcJobNode retrieved repository as text (utf-8, tolerant)."""
    try:
        repo = calc.outputs.retrieved
        if fname not in repo.list_object_names():
            return None
        with repo.open(fname, "rb") as src:
            return src.read().decode("utf-8", "ignore")
    except Exception:
        return None


def _enrich_crystal_extras(summary_store: list[dict[str, Any]], crystal_uuids: list[str]) -> None:
    """Enrich CRYSTAL summaries with phonon frequencies and Seebeck data.

    For ``calc_type == 'phonon'`` rows, parse the MODES block of the
    retrieved ``OUTPUT`` file (via :func:`parse_phonon_from_output`) and fill
    ``has_phonons``, ``phonon_freq_min``, ``phonon_freq_max``,
    ``phonon_n_imag``, ``phonon_modes_count``. For ``calc_type == 'transport'``
    rows, parse the retrieved ``SEEBECK.DAT`` (via
    :func:`parse_seebeck_first_line`) and fill ``seebeck_coefficient_uvk``,
    ``mu_ev``, ``temperature_k``.

    As a fallback, ``scf`` rows whose retrieved repository contains
    ``SEEBECK.DAT`` are reclassified to ``transport`` (and parsed), matching
    the file-based detection used by the local-filesystem scan
    (``crystal_parser/summary.py``).
    """
    uuid_to_idx = {s["uuid"]: i for i, s in enumerate(summary_store)
                   if s.get("uuid") in set(crystal_uuids)}

    phonon_count = 0
    seebeck_count = 0
    for uuid in crystal_uuids:
        idx = uuid_to_idx.get(uuid)
        if idx is None:
            continue
        summary = summary_store[idx]
        calc_type = summary.get("calc_type")
        try:
            calc = load_node(uuid)
        except Exception:
            continue

        try:
            repo_names = set(calc.outputs.retrieved.list_object_names())
        except Exception:
            repo_names = set()

        effective_type = calc_type
        if calc_type == "scf" and "SEEBECK.DAT" in repo_names:
            effective_type = "transport"
            summary["calc_type"] = "transport"

        if effective_type == "phonon":
            text = _retrieved_file_text(calc, "OUTPUT")
            if not text:
                continue
            try:
                parsed = parse_phonon_from_output(text)
            except Exception:
                parsed = None
            if parsed:
                summary["has_phonons"] = parsed.get("has_phonons")
                summary["phonon_freq_min"] = parsed.get("phonon_freq_min")
                summary["phonon_freq_max"] = parsed.get("phonon_freq_max")
                summary["phonon_n_imag"] = parsed.get("phonon_n_imag")
                summary["phonon_modes_count"] = parsed.get("phonon_modes_count")
            phonon_count += 1
            if phonon_count % 25 == 0:
                print(f"  Crystal phonon: {phonon_count}/{len(crystal_uuids)}")

        elif effective_type == "transport":
            if "SEEBECK.DAT" not in repo_names:
                continue
            try:
                tmp_dir = Path(tempfile.mkdtemp())
                try:
                    dst = tmp_dir / "SEEBECK.DAT"
                    with calc.outputs.retrieved.open("SEEBECK.DAT", "rb") as src, open(dst, "wb") as out:
                        shutil.copyfileobj(src, out)
                    avg_s, _components, temperature, mu = parse_seebeck_first_line(str(dst))
                    summary["seebeck_coefficient_uvk"] = avg_s * 1e6
                    summary["mu_ev"] = mu
                    summary["temperature_k"] = temperature
                finally:
                    shutil.rmtree(tmp_dir, ignore_errors=True)
            except Exception:
                pass
            seebeck_count += 1
            if seebeck_count % 25 == 0:
                print(f"  Crystal seebeck: {seebeck_count}/{len(crystal_uuids)}")


def _enrich_fleur_extras(summary_store: list[dict[str, Any]], fleur_uuids: list[str]) -> None:
    uuid_to_idx = {s['uuid']: i for i, s in enumerate(summary_store) if s.get('uuid') in set(fleur_uuids)}

    print(f"Fetching Seebeck data for {len(fleur_uuids)} FLEUR calcs...")
    done = 0
    for uuid in fleur_uuids:
        try:
            calc = load_node(uuid)
            seebeck = _fetch_fleur_seebeck(calc)
            if seebeck and uuid in uuid_to_idx:
                summary_store[uuid_to_idx[uuid]].update(seebeck)
        except Exception:
            pass
        done += 1
        if done % 25 == 0:
            print(f"  Seebeck: {done}/{len(fleur_uuids)}")

    try:
        db_cfg = load_db_config()
        conn = pg8000.connect(**db_cfg)
        print(f"Fetching displacement data for {len(fleur_uuids)} FLEUR calcs...")
        done = 0
        try:
            for uuid in fleur_uuids:
                try:
                    calc = load_node(uuid)
                    disp = _get_fleur_displacement(calc, conn)
                    if uuid in uuid_to_idx:
                        summary_store[uuid_to_idx[uuid]].update(disp)
                except Exception:
                    pass
                done += 1
                if done % 25 == 0:
                    print(f"  Displacement: {done}/{len(fleur_uuids)}")
        finally:
            conn.close()
    except Exception:
        print("  Skipping displacement data (DB connection failed)")

    import math
    for summary in summary_store:
        if summary.get("engine") == "fleur" and summary.get("calc_type") == "scf":
            sq = summary.get("sum_sq_disp")
            if sq is not None and not (isinstance(sq, float) and math.isnan(sq)) and float(sq) > 0.001:
                summary["calc_type"] = "optimise"


_SUMMARY_CSV_COLUMNS = [
    "duration", "bandgap",
    "has_phonons", "phonon_freq_min", "phonon_freq_max",
    "phonon_n_imag", "phonon_modes_count",
    "a", "b", "c", "alpha", "beta", "gamma",
    "chemical_formula", "sum_sq_disp", "rmsd_disp", "output_path",
    "engine", "calc_type", "calc_date", "uuid",
    "seebeck_coefficient_uvk", "mu_ev", "temperature_k",
    "cost_eur", "label", "pk", "computer", "exit_status", "exit_message",
    "space_group", "pearson", "hetzner_rate",
    "cell", "positions", "numbers", "symbols",
]


def save_aiida_reports(
    summary_store: list[dict[str, Any]],
    output_dir: str | Path = "/tmp",
) -> None:
    """
    Save AiiDA summary CSV, JSON, and error reports.

    Produces the same file format as save_reports() for local scans:
      - summary_<timestamp>.csv   (with column order matching local reports)
      - summary_<timestamp>.json
      - report_crystal_<timestamp>.txt  (if any CRYSTAL errors)
      - report_fleur_<timestamp>.txt    (if any FLEUR errors)

    Parameters:
    - summary_store: List of calculation summary dicts
    - output_dir: Directory to save reports to
    """
    time_now = datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
    save_dir = Path(output_dir).resolve()
    save_dir.mkdir(parents=True, exist_ok=True)

    nested_keys = ["cell", "positions", "numbers", "symbols", "bandgap"]

    if summary_store:
        flat_summary = []
        for row in summary_store:
            try:
                row = dict(row)
                for k in nested_keys:
                    if k in row and row[k] is not None:
                        try:
                            row[k] = json.dumps(row[k])
                        except Exception:
                            row[k] = None
                for col in _SUMMARY_CSV_COLUMNS:
                    row.setdefault(col, None)
                flat_summary.append(row)
            except Exception:
                continue

        if flat_summary:
            df = pl.DataFrame(flat_summary, infer_schema_length=len(flat_summary))
            ordered_cols = [c for c in _SUMMARY_CSV_COLUMNS if c in df.columns]
            remaining_cols = [c for c in df.columns if c not in _SUMMARY_CSV_COLUMNS]
            df = df.select(ordered_cols + remaining_cols)
            df = df.drop(
                [col for col in df.columns if df[col].null_count() == df.height]
            )
            csv_path = save_dir / f"summary_{time_now}.csv"
            df.write_csv(csv_path)
            print(f"Summary CSV saved to: {csv_path}")

        json_path = save_dir / f"summary_{time_now}.json"
        with open(json_path, "w") as f:
            json.dump(summary_store, f, indent=2, default=str)
        print(f"Summary JSON saved to: {json_path}")

    error_dict_crystal = {}
    error_dict_fleur = {}
    for s in summary_store:
        if s.get("exit_status") is not None and s.get("exit_status") != 0:
            engine = s.get("engine", "unknown")
            label = s.get("label", "")
            exit_msg = s.get("exit_message", "") or f"exit_status={s.get('exit_status')}"
            error_key = f"Error: {exit_msg}"
            if engine == "crystal":
                error_dict_crystal.setdefault(error_key, []).append(label or s.get("uuid", ""))
            elif engine == "fleur":
                error_dict_fleur.setdefault(error_key, []).append(label or s.get("uuid", ""))
            else:
                error_dict_crystal.setdefault(error_key, []).append(label or s.get("uuid", ""))

    if error_dict_crystal:
        error_path = save_dir / f"report_crystal_{time_now}.txt"
        with open(error_path, "w") as f:
            f.write("---------REPORT CRYSTAL ERROR---------\n")
            for error_key, dirs in error_dict_crystal.items():
                f.write(f"{error_key}\n")
                f.write(f" {error_key}\n")
                f.write("Calculations:\n")
                for d in dirs:
                    f.write(f"  - {d}\n")
                f.write("\n")
        print(f"Crystal error report saved to: {error_path}")

    if error_dict_fleur:
        error_path = save_dir / f"report_fleur_{time_now}.txt"
        with open(error_path, "w") as f:
            f.write("---------REPORT FLEUR ERROR---------\n")
            for error_key, dirs in error_dict_fleur.items():
                f.write(f"{error_key}\n")
                f.write(f" {error_key}\n")
                f.write("Calculations:\n")
                for d in dirs:
                    f.write(f"  - {d}\n")
                f.write("\n")
        print(f"FLEUR error report saved to: {error_path}")

    if not error_dict_crystal and not error_dict_fleur:
        print("No errors found (all calculations completed successfully).")

    print(f"Total calculations in report: {len(summary_store)}")
    print("=" * 60 + "\n")


def generate_aiida_reports(
    label: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    skip_errors: bool = False,
    output_dir: str | Path = "/tmp",
    calc_type: str | None = None,
    engine: str | None = None,
) -> None:
    """
    Generate summary CSV, JSON, and error report from AiiDA database.

    Convenience function that combines scan_aiida_calculations() and save_aiida_reports().

    Parameters:
    - calc_type: If set (e.g. 'phonon', 'transport', 'scf'), only keep rows whose
      ``calc_type`` matches. Note that ``calc_type`` is refined during enrichment
      (e.g. ``scf`` with ``SEEBECK.DAT`` becomes ``transport``), so filtering is
      applied after the full scan.
    - engine: If set ('crystal' or 'fleur'), only query calcs of that engine
      (avoids fetching the other engine entirely — much faster for crystal-only
      reports).
    """
    print("\n" + "=" * 60)
    print("GENERATING REPORTS FROM AiiDA DATABASE")
    print("=" * 60 + "\n")

    summary_store = scan_aiida_calculations(
        label=label,
        from_date=from_date,
        to_date=to_date,
        skip_errors=skip_errors,
        calc_type_filter=calc_type,
        engine=engine,
    )

    if calc_type and calc_type != "transport" and summary_store:
        before = len(summary_store)
        summary_store = [s for s in summary_store if s.get("calc_type") == calc_type]
        print(f"Filtering calc_type={calc_type!r}: {before} -> {len(summary_store)} rows")

    if summary_store:
        empty_transport = [s for s in summary_store
                           if s.get("calc_type") == "transport"
                           and s.get("seebeck_coefficient_uvk") is None]
        if empty_transport:
            print(f"Dropping {len(empty_transport)} transport calcs with empty Seebeck (exit_status=0 but no data)")
            summary_store = [s for s in summary_store
                             if not (s.get("calc_type") == "transport"
                                     and s.get("seebeck_coefficient_uvk") is None)]

    if not summary_store:
        print("No calculations found for the given criteria.")
        return

    print(f"Found {len(summary_store)} calculations. Saving reports...\n")
    save_aiida_reports(summary_store, output_dir=output_dir)
