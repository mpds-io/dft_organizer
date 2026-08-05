from datetime import datetime
from pathlib import Path
from typing import Any

import json
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


_aiida_loaded = False


def _ensure_aiida():
    global _aiida_loaded
    if not _aiida_loaded:
        load_aiida_profile()
        _aiida_loaded = True


from dft_organizer.pricing import (
    read_provider_and_machine_type_from_config,
    resolve_provider_and_rate,
)


def _fetch_fleur_seebeck(calc) -> dict | None:
    node = calc
    while node is not None:
        ptype = getattr(node, "process_type", "") or ""
        if "FleurDOSLocalWorkChain" in ptype:
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
        node = getattr(node, "caller", None)
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
        disp = _structure_displacement_ase(
            first_struct.get_ase(), last_struct.get_ase()
        )
        result["sum_sq_disp"] = round(disp["sum_sq_disp"], 2)
        result["rmsd_disp"] = round(disp["rmsd_disp"], 2)
    except Exception:
        pass

    return result


def _build_date_filter(from_date: str | None, to_date: str | None) -> dict:
    filt = {}
    if from_date:
        filt[">="] = datetime.strptime(from_date, "%Y-%m-%d")
    if to_date:
        filt["<="] = datetime.strptime(to_date, "%Y-%m-%d")
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


def _determine_calc_type(label: str) -> str:
    label_lower = label.lower()
    if any(kw in label_lower for kw in ("phonon", "elastic", "fort.34", "fort.9")):
        return "properties"
    if any(
        kw in label_lower
        for kw in ("band", "doss", "fort.25", "transport", "seebeck", "sigma", "kappa")
    ):
        return "properties"
    if any(kw in label_lower for kw in ("geometry", "optim", "relax")):
        return "optimise"
    return "scf"


def _formula_from_label(label: str | None) -> str | None:
    if not label or ":" not in label:
        return None
    candidate = label.split(":")[0].strip()
    if not candidate or len(candidate) > 15:
        return None
    if not candidate[0].isupper():
        return None
    return candidate


def _extract_struct_info(attrs: dict | None) -> dict:
    result = {
        "chemical_formula": None,
        "a": None,
        "b": None,
        "c": None,
        "alpha": None,
        "beta": None,
        "gamma": None,
        "cell": None,
        "positions": None,
        "numbers": None,
        "symbols": None,
    }
    if not attrs:
        return result
    try:
        cell = attrs.get("cell")
        kinds = attrs.get("kinds", [])
        sites = attrs.get("sites", [])
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

        kind_to_symbol = {k["name"]: k["symbols"][0] for k in kinds if k.get("symbols")}
        symbols_list = [kind_to_symbol.get(s.get("kind_name", ""), "?") for s in sites]
        numbers_list = []
        from ase.data import atomic_numbers as ase_atomic_numbers

        for sym in symbols_list:
            numbers_list.append(ase_atomic_numbers.get(sym, 0))
        positions_list = [s.get("position", [0, 0, 0]) for s in sites]

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
        formula = "".join(k if counts[k] == 1 else f"{k}{counts[k]}" for k in order)

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
    if "crystal" in pt:
        return "crystal"
    if "fleur" in pt:
        return "fleur"
    return None


def _get_struct_attrs_from_calc(calc) -> dict | None:
    try:
        struct = calc.inputs.structure
        return struct.base.attributes.all
    except Exception:
        pass
    node = getattr(calc, "caller", None)
    visited = 0
    while node is not None and visited < 10:
        visited += 1
        try:
            struct = node.inputs.structure
            return struct.base.attributes.all
        except Exception:
            pass
        node = getattr(node, "caller", None)
    return None


_null_summary_keys = [
    "a",
    "b",
    "c",
    "alpha",
    "beta",
    "gamma",
    "cell",
    "positions",
    "numbers",
    "symbols",
    "bandgap",
    "sum_sq_disp",
    "rmsd_disp",
    "output_path",
    "cost",
    "cloud_rate",
    "currency",
]


def scan_aiida_calculations(
    label: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    skip_errors: bool = False,
    provider: str | None = None,
    engine: str | None = None,
    machine_type: str | None = None,
) -> list[dict[str, Any]]:
    """
    Query AiiDA CalcJobNodes and build a summary store for reporting.

    Similar to scan_calculations() but reads from AiiDA DB instead of local files.

    Parameters:
    - label: If set, only include this specific label (exact match)
    - from_date: Only include calcs created on or after this date (YYYY-MM-DD)
    - to_date: Only include calcs created on or before this date (YYYY-MM-DD)
    - skip_errors: Skip calculations with exit_status != 0
    - provider: Override cloud provider for cost calculation ("hetzner"/"vultr_usa");
      when None, auto-detect from computer name via detect_provider()
    - engine: Filter by calculation engine ("crystal"/"fleur"); when None, include all
    - machine_type: Override machine type (plan name, e.g. "vbm-24c-256gb-amd") for
      cost calculation; when None, falls back to computer name lookup

    Returns: list of summary dicts
    """
    _ensure_aiida()

    filters = {}
    if label:
        filters["label"] = {"==": label}
    date_filter = _build_date_filter(from_date, to_date)
    if date_filter:
        filters["ctime"] = date_filter
    if engine:
        filters["process_type"] = {"like": f"%{engine}%"}

    print("Querying AiiDA database...")
    qb = QueryBuilder()
    qb.append(
        CalcJobNode,
        tag="calc",
        filters=filters or None,
        project=["uuid", "label", "process_type", "ctime", "mtime", "id", "attributes"],
    )
    qb.append(Computer, with_node="calc", project=["label"], outerjoin=True)

    rows = list(qb.iterall())
    print(f"Found {len(rows)} calculations in database.")

    summary_store = []
    fleur_uuids = []
    crystal_uuids = []

    for uuid, lbl, process_type, ctime, mtime, pk, attrs, comp in rows:
        exit_status = attrs.get("exit_status") if attrs else None
        exit_message = str(attrs.get("exit_message", "")) if attrs else ""

        if skip_errors and exit_status is not None and exit_status != 0:
            continue

        engine = _engine_from_process_type(process_type) or "unknown"

        duration = None
        if ctime and mtime:
            duration = round((mtime - ctime).total_seconds() / 3600, 4)

        summary = {
            "uuid": uuid,
            "label": lbl,
            "engine": engine,
            "calc_type": _determine_calc_type(lbl),
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
            prov, rate, currency = resolve_provider_and_rate(
                comp, provider=provider, machine_type=machine_type
            )
            if currency is not None:
                summary["currency"] = currency
            if rate is not None:
                summary["cloud_rate"] = rate
                if duration is not None:
                    import math as _math

                    if not (isinstance(duration, float) and _math.isnan(duration)):
                        summary["cost"] = round(duration * rate, 2)

        if engine == "fleur":
            fleur_uuids.append(uuid)
        elif engine == "crystal":
            crystal_uuids.append(uuid)

        summary_store.append(summary)

    _enrich_with_structure_fast(summary_store, crystal_uuids, fleur_uuids)

    if fleur_uuids:
        print(
            f"Enriching {len(fleur_uuids)} FLEUR calculations (Seebeck, displacement)..."
        )
        _enrich_fleur_extras(summary_store, fleur_uuids)

    return summary_store


def _enrich_with_structure_fast(
    summary_store: list[dict[str, Any]],
    crystal_uuids: list[str],
    fleur_uuids: list[str],
) -> None:
    crystal_uuid_set = list(crystal_uuids)
    fleur_uuid_set = set(fleur_uuids)

    print(
        f"Fetching structure data for {len(crystal_uuid_set)} CRYSTAL calcs (fast)..."
    )
    if crystal_uuid_set:
        qb = QueryBuilder()
        qb.append(
            CalcJobNode,
            tag="calc",
            filters={"uuid": {"in": crystal_uuid_set}},
            project=["uuid"],
        )
        qb.append(
            StructureData, with_incoming="calc", project=["attributes"], outerjoin=True
        )
        struct_map = {}
        for calc_uuid, struct_attrs in qb.iterall():
            if struct_attrs:
                struct_map[calc_uuid] = struct_attrs

        for summary in summary_store:
            if summary["uuid"] in crystal_uuid_set:
                struct_attrs = struct_map.get(summary["uuid"])
                if struct_attrs:
                    struct_info = _extract_struct_info(struct_attrs)
                    for k in (
                        "chemical_formula",
                        "a",
                        "b",
                        "c",
                        "alpha",
                        "beta",
                        "gamma",
                        "cell",
                        "positions",
                        "numbers",
                        "symbols",
                    ):
                        if struct_info.get(k) is not None:
                            summary[k] = struct_info[k]
                    try:
                        import spglib as _spglib

                        cell = struct_attrs.get("cell")
                        kinds = struct_attrs.get("kinds", [])
                        sites = struct_attrs.get("sites", [])
                        kind_to_symbol = {
                            k["name"]: k["symbols"][0]
                            for k in kinds
                            if k.get("symbols")
                        }
                        symbols_list = [
                            kind_to_symbol.get(s.get("kind_name", ""), "?")
                            for s in sites
                        ]
                        from ase.data import atomic_numbers as _ase_an

                        numbers = [_ase_an.get(sym, 0) for sym in symbols_list]
                        positions = [s.get("position", [0, 0, 0]) for s in sites]
                        if cell and numbers:
                            dataset = _spglib.get_symmetry_dataset(
                                (cell, positions, numbers)
                            )
                            if dataset is not None:
                                summary["space_group"] = dataset.number
                    except Exception:
                        pass

    crystal_no_formula = [
        s
        for s in summary_store
        if s["uuid"] in crystal_uuid_set and not s.get("chemical_formula")
    ]
    if crystal_no_formula:
        print(
            f"Fallback: fetching structure via provenance for {len(crystal_no_formula)} CRYSTAL calcs without formula..."
        )
        done = 0
        for summary in crystal_no_formula:
            try:
                calc = load_node(summary["uuid"])
                struct_attrs = _get_struct_attrs_from_calc(calc)
                if struct_attrs:
                    struct_info = _extract_struct_info(struct_attrs)
                    for k in (
                        "chemical_formula",
                        "a",
                        "b",
                        "c",
                        "alpha",
                        "beta",
                        "gamma",
                        "cell",
                        "positions",
                        "numbers",
                        "symbols",
                    ):
                        if struct_info.get(k) is not None:
                            summary[k] = struct_info[k]
                    try:
                        import spglib as _spglib

                        cell = struct_attrs.get("cell")
                        kinds = struct_attrs.get("kinds", [])
                        sites = struct_attrs.get("sites", [])
                        kind_to_symbol = {
                            k["name"]: k["symbols"][0]
                            for k in kinds
                            if k.get("symbols")
                        }
                        symbols_list = [
                            kind_to_symbol.get(s.get("kind_name", ""), "?")
                            for s in sites
                        ]
                        from ase.data import atomic_numbers as _ase_an

                        numbers = [_ase_an.get(sym, 0) for sym in symbols_list]
                        positions = [s.get("position", [0, 0, 0]) for s in sites]
                        if cell and numbers:
                            dataset = _spglib.get_symmetry_dataset(
                                (cell, positions, numbers)
                            )
                            if dataset is not None:
                                summary["space_group"] = dataset.number
                    except Exception:
                        pass
            except Exception:
                pass
            done += 1
            if done % 25 == 0:
                print(f"  CRYSTAL fallback: {done}/{len(crystal_no_formula)}")

    if fleur_uuid_set:
        print(
            f"Fetching structure data for {len(fleur_uuid_set)} FLEUR calcs (via provenance)..."
        )
        done = 0
        for summary in summary_store:
            if summary["uuid"] in fleur_uuid_set:
                try:
                    calc = load_node(summary["uuid"])
                    struct_attrs = _get_struct_attrs_from_calc(calc)
                    if struct_attrs:
                        struct_info = _extract_struct_info(struct_attrs)
                        for k in (
                            "chemical_formula",
                            "a",
                            "b",
                            "c",
                            "alpha",
                            "beta",
                            "gamma",
                            "cell",
                            "positions",
                            "numbers",
                            "symbols",
                        ):
                            if struct_info.get(k) is not None:
                                summary[k] = struct_info[k]
                        try:
                            import spglib

                            cell = struct_attrs.get("cell")
                            kinds = struct_attrs.get("kinds", [])
                            sites = struct_attrs.get("sites", [])
                            kind_to_symbol = {
                                k["name"]: k["symbols"][0]
                                for k in kinds
                                if k.get("symbols")
                            }
                            symbols_list = [
                                kind_to_symbol.get(s.get("kind_name", ""), "?")
                                for s in sites
                            ]
                            from ase.data import atomic_numbers as _ase_an

                            numbers = [_ase_an.get(sym, 0) for sym in symbols_list]
                            positions = [s.get("position", [0, 0, 0]) for s in sites]
                            if cell and numbers:
                                dataset = spglib.get_symmetry_dataset(
                                    (cell, positions, numbers)
                                )
                                if dataset is not None:
                                    summary["space_group"] = dataset.number
                        except Exception:
                            pass
                except Exception:
                    pass
                done += 1
                if done % 25 == 0:
                    print(f"  FLEUR structure: {done}/{len(fleur_uuid_set)}")


def _enrich_fleur_extras(
    summary_store: list[dict[str, Any]], fleur_uuids: list[str]
) -> None:
    uuid_to_idx = {
        s["uuid"]: i
        for i, s in enumerate(summary_store)
        if s.get("uuid") in set(fleur_uuids)
    }

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
            if (
                sq is not None
                and not (isinstance(sq, float) and math.isnan(sq))
                and float(sq) > 0.001
            ):
                summary["calc_type"] = "optimise"


_SUMMARY_CSV_COLUMNS = [
    "duration",
    "bandgap",
    "a",
    "b",
    "c",
    "alpha",
    "beta",
    "gamma",
    "chemical_formula",
    "sum_sq_disp",
    "rmsd_disp",
    "output_path",
    "engine",
    "calc_type",
    "calc_date",
    "uuid",
    "seebeck_coefficient_uvk",
    "mu_ev",
    "temperature_k",
    "cost",
    "currency",
    "label",
    "pk",
    "computer",
    "exit_status",
    "exit_message",
    "space_group",
    "pearson",
    "cloud_rate",
    "cell",
    "positions",
    "numbers",
    "symbols",
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
            df = pl.DataFrame(flat_summary)
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
            exit_msg = (
                s.get("exit_message", "") or f"exit_status={s.get('exit_status')}"
            )
            error_key = f"Error: {exit_msg}"
            if engine == "crystal":
                error_dict_crystal.setdefault(error_key, []).append(
                    label or s.get("uuid", "")
                )
            elif engine == "fleur":
                error_dict_fleur.setdefault(error_key, []).append(
                    label or s.get("uuid", "")
                )
            else:
                error_dict_crystal.setdefault(error_key, []).append(
                    label or s.get("uuid", "")
                )

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
    provider: str | None = None,
    engine: str | None = None,
    machine_type: str | None = None,
) -> None:
    """
    Generate summary CSV, JSON, and error report from AiiDA database.

    Convenience function that combines scan_aiida_calculations() and save_aiida_reports().
    When ``machine_type`` or ``provider`` is None, attempts to read them from the
    yascheduler config (``/etc/yascheduler/yascheduler.conf``). When neither is
    available, cost is still attempted via auto-detection from the AiiDA computer
    name; cost columns are omitted only when no rate can be determined.
    """
    if machine_type is None or provider is None:
        cfg_provider, cfg_machine_type = read_provider_and_machine_type_from_config()
        if machine_type is None:
            machine_type = cfg_machine_type
        if provider is None:
            provider = cfg_provider

    print("\n" + "=" * 60)
    print("GENERATING REPORTS FROM AiiDA DATABASE")
    print("=" * 60 + "\n")

    summary_store = scan_aiida_calculations(
        label=label,
        from_date=from_date,
        to_date=to_date,
        skip_errors=skip_errors,
        provider=provider,
        engine=engine,
        machine_type=machine_type,
    )

    if not summary_store:
        print("No calculations found for the given criteria.")
        return

    print(f"Found {len(summary_store)} calculations. Saving reports...\n")
    save_aiida_reports(summary_store, output_dir=output_dir)
