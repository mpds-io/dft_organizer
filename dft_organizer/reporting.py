import os
from datetime import datetime
from pathlib import Path
from typing import Any
import math

import json
import polars as pl

from aiida import load_profile as load_aiida_profile
from aiida.orm import load_node, StructureData
import pg8000
import numpy as np

from dft_organizer.aiida_utils import extract_uuid_from_path
from dft_organizer.utils import detect_engine, get_table_string
from dft_organizer.pricing import get_cloud_rate, get_cost
from dft_organizer.crystal_parser import (
    parse_crystal_output,
    is_properties_output,
    make_report as make_report_crystal,
    print_report as print_report_crystal,
    save_report as save_report_crystal,
    parse_phonon_output as parse_phonon_output_crystal,
    parse_phonon_from_output,
)
from dft_organizer.fleur_parser import (
    parse_fleur_output,
    make_report as make_report_fleur,
    print_report as print_report_fleur,
    save_report as save_report_fleur,
    parse_phonon_output as parse_phonon_output_fleur,
)
from dft_organizer.aiida.aiida_links_tree import (
    load_db_config,
    fetch_tree_from_db,
    find_first_last_structure_uuids,
)


def _get_structure_from_uuid(uuid: str) -> StructureData:
    """Upload StructureData node by UUID"""
    node = load_node(uuid)
    if isinstance(node, StructureData):
        return node
    if hasattr(node, "outputs") and "structure" in node.outputs:
        out = node.outputs["structure"]
        if isinstance(out, StructureData):
            return out
    raise ValueError(f"Node {uuid} does not provide a StructureData")


def structure_displacement_ase(atoms_init, atoms_final) -> dict:
    pos_init = atoms_init.get_positions()
    pos_final = atoms_final.get_positions()
    if pos_init.shape != pos_final.shape:
        raise ValueError("Initial and final structures have different sizes/order")
    disp = pos_final - pos_init
    sq = np.sum(disp**2, axis=1)
    sum_sq = float(np.sum(sq))
    rmsd = float(np.sqrt(np.mean(sq)))
    return {"sum_sq_disp": sum_sq, "rmsd_disp": rmsd}


def enrich_with_aiida_data(summary_store: list[dict[str, Any]]) -> None:
    """Add pk, space_group, cost_eur from AiiDA CalcJobNode.

    For each summary with a uuid:
    - Load CalcJobNode, get .pk
    - Get input structure → spglib → space_group number
    - Get computer name → cloud rate → cost = duration * rate
    Skips if uuid missing or node not loadable (sets fields to None).
    Modifies summary_store in-place.
    """
    load_aiida_profile()

    for summary in summary_store:
        calc_uuid = summary.get("uuid")
        if not calc_uuid:
            continue

        summary["pk"] = None
        summary["space_group"] = None
        summary["cost_eur"] = None
        summary["calc_date"] = None

        try:
            calc = load_node(calc_uuid)
        except Exception:
            continue

        summary["pk"] = calc.pk
        summary["calc_date"] = calc.ctime.strftime("%Y-%m-%d %H:%M:%S")

        try:
            struct = calc.inputs.structure
            ase_atoms = struct.get_ase()
            import spglib
            dataset = spglib.get_symmetry_dataset((
                ase_atoms.cell,
                ase_atoms.positions,
                ase_atoms.get_atomic_numbers(),
            ))
            if dataset is not None:
                summary["space_group"] = dataset.number
        except Exception:
            pass

        try:
            duration = summary.get("duration")
            cost = get_cost(duration, calc.computer.label if calc.computer else "", provider="hetzner")
            if cost is not None:
                summary["cost_eur"] = cost
        except Exception:
            pass

        if summary.get("engine") == "fleur":
            try:
                seebeck = _fetch_fleur_seebeck(calc)
                if seebeck:
                    summary.update(seebeck)
            except Exception:
                pass


def _fetch_fleur_seebeck(calc) -> dict | None:
    """Walk up caller chain from a FLEUR CalcJobNode to find
    FleurDOSLocalWorkChain and extract Seebeck data."""
    node = calc
    while node is not None:
        ptype = getattr(node, 'process_type', '') or ''
        if 'FleurDOSLocalWorkChain' in ptype:
            try:
                sd = node.outputs.output_seebeck.base.attributes.all
                pd = node.outputs.output_dos_local_wc_para.base.attributes.all
                return {
                    "seebeck_coefficient_uvk": sd.get("seebeck_coefficient_uvk"),
                    "mu_ev": sd.get("mu_ev"),
                    "temperature_k": pd.get("temperature_k"),
                }
            except Exception:
                return None
        node = getattr(node, 'caller', None)
    return None


def enrich_fleur_with_displacement(summary_store: list[dict[str, Any]]) -> None:
    """
    For each summary with engine='fleur' ​​and field 'uuid' (CalcJobNode FLEUR):
    - Builds a tree around the CalcJob;
    - Finds the first and last StructureData by pk;
    - Calculates the coordinate offset between them;
    - Adds to the summary:
    'first_struct_uuid', 'last_struct_uuid',
    'sum_sq_disp', 'rmsd_disp',
    Modifies summary_store in-place.
    """
    load_aiida_profile()
    db_cfg = load_db_config()
    conn = pg8000.connect(**db_cfg)

    try:
        for summary in summary_store:
            if summary.get("engine") != "fleur":
                continue
            calc_uuid = summary.get("uuid")
            if not calc_uuid:
                continue

            summary["first_struct_uuid"] = None
            summary["last_struct_uuid"] = None
            summary["sum_sq_disp"] = None
            summary["rmsd_disp"] = None

            try:
                calc = load_node(calc_uuid)
            except Exception as e:
                print(f"Cannot load CalcJobNode {calc_uuid}: {e}")
                continue

            start_pk = calc.pk

            try:
                links = fetch_tree_from_db(conn, start_pk)
                first_s_uuid, last_s_uuid = find_first_last_structure_uuids(links)
            except Exception as e:
                print(f"Cannot build provenance tree for pk={start_pk}: {e}")
                continue

            if first_s_uuid is None or last_s_uuid is None:
                continue

            summary["first_struct_uuid"] = first_s_uuid
            summary["last_struct_uuid"] = last_s_uuid

            try:
                first_struct = _get_structure_from_uuid(first_s_uuid)
                last_struct = _get_structure_from_uuid(last_s_uuid)
                ase_first = first_struct.get_ase()
                ase_last = last_struct.get_ase()
                disp = structure_displacement_ase(ase_first, ase_last)
                summary["sum_sq_disp"] = round(disp["sum_sq_disp"], 2)
                summary["rmsd_disp"]   = round(disp["rmsd_disp"], 2)
            except Exception as e:
                print(f"Cannot compute displacement for CalcJob {calc_uuid}: {e}")
                continue

    finally:
        conn.close()


def _enrich_summary_with_phonons(
    summary: dict[str, Any],
    calc_dir: Path,
    phonon_store: list[dict[str, Any]],
    engine: str,
) -> None:
    """Detect phonon output files in the calculation directory, parse them,
    add compact phonon fields to ``summary`` in-place, and append detailed
    per-mode records to ``phonon_store``.

    When no phonon files are found (or the parser returns ``None``), the
    summary gets ``has_phonons=False`` and ``phonon_*`` fields set to ``None``,
    and nothing is appended to ``phonon_store``.
    """
    summary.setdefault("has_phonons", False)
    summary.setdefault("phonon_freq_min", None)
    summary.setdefault("phonon_freq_max", None)
    summary.setdefault("phonon_n_imag", None)
    summary.setdefault("phonon_modes_count", None)

    try:
        if engine == "crystal":
            parsed = parse_phonon_output_crystal(calc_dir)
            if not parsed:
                output_path = summary.get("output_path")
                if output_path:
                    try:
                        text = Path(output_path).read_text(encoding="utf-8", errors="ignore")
                        parsed = parse_phonon_from_output(text)
                    except Exception:
                        parsed = None
        elif engine == "fleur":
            parsed = parse_phonon_output_fleur(calc_dir)
        else:
            parsed = None
    except Exception as e:
        print(f"Phonon parse error in {calc_dir}: {e}")
        parsed = None

    if not parsed:
        return

    summary["has_phonons"] = parsed.get("has_phonons", False)
    summary["phonon_freq_min"] = parsed.get("phonon_freq_min")
    summary["phonon_freq_max"] = parsed.get("phonon_freq_max")
    summary["phonon_n_imag"] = parsed.get("phonon_n_imag")
    summary["phonon_modes_count"] = parsed.get("phonon_modes_count")

    details = parsed.get("details") or []
    uuid = summary.get("uuid")
    formula = summary.get("chemical_formula")
    for d in details:
        record = {
            "uuid": uuid,
            "engine": engine,
            "chemical_formula": formula,
            "output_path": parsed.get("source_file"),
            "q_point": d.get("q_point"),
            "branch_index": d.get("branch_index"),
            "frequency_thz": d.get("frequency_thz"),
            "is_imaginary": d.get("is_imaginary"),
            "temperature_k": d.get("temperature_k"),
            "modes_count": parsed.get("phonon_modes_count"),
        }
        phonon_store.append(record)


def _refine_crystal_properties_type(calc_dir: Path, output_path: Path) -> str:
    """Refine a CRYSTAL ``properties`` calc_type into a specific subtype.

    Detection order (first match wins):
    1. ``SEEBECK.DAT`` / ``SIGMA.DAT`` / ``KAPPA.DAT`` / ``TDF.DAT`` present -> ``transport``
    2. ``PHONON.DAT`` / ``FREQ.DAT`` present, or ``FREQCALC`` / ``FREQUENCY CALCULATION``
       in the OUTPUT text -> ``phonon``
    3. ``ELASTIC.DAT`` present, or ``ELASTIC`` in the OUTPUT text -> ``elastic``
    4. ``BAND.DAT`` / ``DOSS.DAT`` present -> ``electron``
    5. otherwise ``properties`` (unchanged)
    """
    try:
        names = set(p.name.upper() for p in calc_dir.iterdir() if p.is_file())
    except Exception:
        names = set()

    transport_files = {"SEEBECK.DAT", "SIGMA.DAT", "KAPPA.DAT", "TDF.DAT", "SIGMAS.DAT"}
    if names & transport_files:
        return "transport"
    if {"PHONON.DAT", "FREQ.DAT"} & names:
        return "phonon"
    if "ELASTIC.DAT" in names:
        return "elastic"
    if {"BAND.DAT", "DOSS.DAT"} & names:
        return "electron"

    try:
        text = output_path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return "properties"
    if "FREQCALC" in text or "FREQUENCY CALCULATION" in text:
        return "phonon"
    if "ELASTIC" in text:
        return "elastic"
    return "properties"


def scan_calculations(
    root_dir: Path,
    aiida: bool = False,
    verbose: bool = True,
    skip_errors: bool = False,
    calculation_type: str = "all",
    engine_type: str | None = None,
) -> tuple[list[dict[str, Any]], dict, dict, list[dict[str, Any]]]:
    """
    Go through directory tree, parse outputs and generate error reports.

    Parameters:
    - root_dir: Path to the root directory to scan.
    - aiida: Whether to enrich with AiiDA data (pk, space_group, cost_eur, displacement).
            UUID is always extracted from path regardless of this flag.
    - verbose: Whether to print summaries to stdout.
    - skip_errors: Whether to skip entries with parsing errors in the summary.
    - calculation_type: Filter by calculation type: "all", "optimise", "scf", "properties".
    - engine_type: Filter by engine: None (all), "crystal", or "fleur".

    Returns a 4-tuple ``(summary_store, error_dict_crystal, error_dict_fleur, phonon_store)``.
    """
    root_path = Path(root_dir).resolve()

    valid_engines = {"crystal", "fleur"}
    if engine_type is not None and engine_type not in valid_engines:
        raise ValueError(f"engine_type must be one of {valid_engines} or None, got: {engine_type!r}")

    summary_store: list[dict[str, Any]] = []
    error_dict_crystal: dict = {}
    error_dict_fleur: dict = {}
    phonon_store: list[dict[str, Any]] = []

    for dirpath, dirnames, filenames in os.walk(root_path, topdown=False):
        current_dir = Path(dirpath)
        if current_dir == root_path:
            continue

        engine = detect_engine(filenames, current_dir)

        if engine == "crystal" and ("OUTPUT" in filenames or "OUTPUT_prop" in filenames):
            if engine_type and engine_type != "crystal":
                continue
            if "OUTPUT_prop" in filenames:
                output_path = current_dir / "OUTPUT_prop"
            else:
                output_path = current_dir / "OUTPUT"

            if is_properties_output(output_path):
                calc_type = "properties"
            elif "OUTPUT_prop" in filenames:
                calc_type = "properties"
            else:
                calc_type = "scf"

            summary = parse_crystal_output(output_path)

            if calc_type == "scf" and summary.get("optgeom") is True:
                calc_type = "optimise"

            if calc_type == "properties":
                calc_type = _refine_crystal_properties_type(current_dir, output_path)
            elif calc_type == "scf":
                refined = _refine_crystal_properties_type(current_dir, output_path)
                if refined != "properties":
                    calc_type = refined

            if calculation_type != "all" and calc_type != calculation_type:
                continue

            summary["output_path"] = str(output_path)
            summary["engine"] = engine
            summary["calc_type"] = calc_type
            summary["calc_date"] = datetime.fromtimestamp(output_path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            uuid = extract_uuid_from_path(output_path, root_path)
            summary["uuid"] = uuid
            if skip_errors and math.isnan(summary.get('duration', float('nan'))):
                continue
            summary_store.append(summary)
            _enrich_summary_with_phonons(summary, current_dir, phonon_store, engine="crystal")
            if verbose:
                print(f"{engine.upper()} OUTPUT FOUND IN {output_path}")
                print(get_table_string(summary))

        elif engine == "fleur" and ("out" in filenames or "out.xml" in filenames):
            if engine_type and engine_type != "fleur":
                continue
            output_path = current_dir / ("out.xml" if "out.xml" in filenames else "out")
            summary = parse_fleur_output(output_path)
            summary["output_path"] = str(output_path)
            summary["engine"] = engine
            fleur_modes = summary.get("fleur_modes", {})
            is_relax = isinstance(fleur_modes, dict) and fleur_modes.get("relax", False)
            has_disp = summary.get("sum_sq_disp") is not None and not (
                isinstance(summary.get("sum_sq_disp"), float) and math.isnan(summary.get("sum_sq_disp", 0))
            ) and float(summary.get("sum_sq_disp", 0)) > 0.001
            summary["calc_type"] = "optimise" if (is_relax or has_disp) else "scf"
            summary.pop("fleur_modes", None)
            summary["calc_date"] = datetime.fromtimestamp(output_path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            uuid = extract_uuid_from_path(output_path, root_path)
            summary["uuid"] = uuid
            if skip_errors and math.isnan(summary.get('duration', float('nan'))):
                continue
            summary_store.append(summary)
            _enrich_summary_with_phonons(summary, current_dir, phonon_store, engine="fleur")
            if verbose:
                print(f"{engine.upper()} OUTPUT FOUND IN {output_path}")
                print(get_table_string(summary))

        if engine == "crystal":
            error_dict_crystal = make_report_crystal(
                current_dir, filenames, error_dict_crystal
            )
        elif engine == "fleur":
            error_dict_fleur = make_report_fleur(
                current_dir, filenames, error_dict_fleur
            )

    if aiida and summary_store:
        enrich_fleur_with_displacement(summary_store)
        enrich_with_aiida_data(summary_store)

        for summary in summary_store:
            if summary.get("engine") == "fleur" and summary.get("calc_type") == "scf":
                sq = summary.get("sum_sq_disp")
                if sq is not None and not (isinstance(sq, float) and math.isnan(sq)) and float(sq) > 0.001:
                    summary["calc_type"] = "optimise"

    return summary_store, error_dict_crystal, error_dict_fleur, phonon_store


def find_calculation_by_uuid(root_dir: Path, uuid: str) -> Path:
    """Find calculation directory by UUID in AiiDA structure"""
    root_path = Path(root_dir).resolve()

    if not root_path.exists():
        raise FileNotFoundError(f"Directory does not exist: {root_path}")

    if len(uuid) < 4:
        raise ValueError(f"UUID too short: {uuid}")

    first_dir = uuid[:2]
    second_dir = uuid[2:4]
    calc_dir = uuid[4:]

    expected_path = root_path / first_dir / second_dir / calc_dir

    if expected_path.exists():
        return expected_path

    for dirpath, dirnames, filenames in os.walk(root_path):
        current_dir = Path(dirpath)
        extracted_uuid = extract_uuid_from_path(current_dir, root_path)
        if extracted_uuid == uuid:
            return current_dir

    raise FileNotFoundError(f"Calculation with UUID {uuid} not found in {root_path}")


def save_reports(
    root_path: Path,
    summary_store: list[dict],
    error_dict_crystal: dict,
    error_dict_fleur: dict,
    phonon_store: list[dict] | None = None,
    output_dir: Path | None = None,
) -> None:
    time_now = datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
    save_dir = Path(output_dir) if output_dir else root_path.parent
    save_dir = save_dir.resolve()
    save_dir.mkdir(parents=True, exist_ok=True)

    def _serialize_nested(v):
        if v is None:
            return ""
        return json.dumps(v)

    if summary_store:
        nested_keys = ["cell", "positions", "pbc", "numbers", "symbols", "bandgap", "space_group", "q_point"]
        _DROP_KEYS = {
            "techs_1_FMIXING", "techs_2", "optgeom", "num_opt_cycles",
            "MAXCYCLE", "TOLDEE", "TOLLDENS", "TOLLGRID", "SHRINK",
            "t1", "t5", "k", "H", "smear", "spin", "TOLINTEG",
        }
        flat_summary = []

        for row in summary_store:
            try:
                row = dict(row)
                for dk in _DROP_KEYS:
                    row.pop(dk, None)
                for k in nested_keys:
                    if k in row:
                        try:
                            row[k] = _serialize_nested(row[k])
                        except Exception:
                            row[k] = None
                flat_summary.append(row)
            except Exception:
                continue

        if flat_summary:
            df = pl.DataFrame(flat_summary)
            df.write_csv(save_dir / f"summary_{time_now}.csv")

            json_path = save_dir / f"summary_{time_now}.json"
            with open(json_path, "w") as f:
                json.dump(flat_summary, f, indent=2, default=str)
            print(f"Summary JSON saved to: {json_path}")

    if phonon_store:
        phonon_flat: list[dict] = []
        phonon_nested_keys = ["q_point"]
        for row in phonon_store:
            try:
                row = dict(row)
                for k in phonon_nested_keys:
                    if k in row:
                        try:
                            row[k] = _serialize_nested(row[k])
                        except Exception:
                            row[k] = None
                phonon_flat.append(row)
            except Exception:
                continue
        if phonon_flat:
            try:
                phonon_df = pl.DataFrame(phonon_flat)
                phonon_csv = save_dir / f"phonon_summary_{time_now}.csv"
                phonon_df.write_csv(phonon_csv)
                print(f"Phonon summary CSV saved to: {phonon_csv}")
            except Exception as e:
                print(f"Failed to write phonon_summary CSV: {e}")

    if error_dict_fleur:
        print_report_fleur(error_dict_fleur)
        save_report_fleur(
            error_dict_fleur,
            save_dir / f"report_fleur_{time_now}.txt",
        )

    if error_dict_crystal:
        print_report_crystal(error_dict_crystal)
        save_report_crystal(
            error_dict_crystal,
            save_dir / f"report_crystal_{time_now}.txt",
        )


def generate_report_for_uuid(root_dir: Path, uuid: str) -> dict:
    """Generate report for a specific calculation by UUID"""
    try:
        calc_dir = find_calculation_by_uuid(root_dir, uuid)
        print(f"Found calculation at: {calc_dir}")

        filenames = [f.name for f in calc_dir.iterdir() if f.is_file()]

        error_dict = {}

        engine = detect_engine(filenames, calc_dir)

        if engine == "crystal":
            error_dict = make_report_crystal(str(calc_dir), filenames, {})
            output_file = calc_dir / "OUTPUT"
            parse_output = parse_crystal_output
            print_report = print_report_crystal
            save_report = save_report_crystal
        elif engine == "fleur":
            error_dict = make_report_fleur(str(calc_dir), filenames, {})
            output_file = calc_dir / "out"
            parse_output = parse_fleur_output
            print_report = print_report_fleur
            save_report = save_report_fleur
        else:
            print(f"Unknown engine detected for {calc_dir}")
            return None

        summary = None

        if output_file.exists():
            summary = parse_output(output_file)
            summary["output_path"] = str(output_file)
            summary["uuid"] = uuid
            summary["engine"] = engine
        else:
            print(f"Output file not found in {calc_dir}")
            summary = {
                "output_path": str(calc_dir),
                "uuid": uuid,
                "engine": engine,
                "error": "Output file not found",
            }

        print("\n" + "=" * 60)
        print(f"CALCULATION REPORT FOR UUID: {uuid}")
        print("=" * 60)

        if "error" not in summary:
            print(get_table_string(summary))

        print("\n--- ERROR REPORT ---")
        print_report(error_dict)
        print("=" * 60)

        root_path = Path(root_dir).resolve()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        if summary:
            summary_file = root_path.parent / f"summary_uuid_{uuid}_{timestamp}.csv"
            df = pl.DataFrame([summary])
            df.write_csv(summary_file)
            print(f"\nSummary saved to: {summary_file}")

        error_report_file = root_path.parent / f"report_uuid_{uuid}_{timestamp}.txt"
        save_report(error_dict, str(error_report_file))
        print(f"Error report saved to: {error_report_file}")

        return summary

    except FileNotFoundError as e:
        print(f"Error: {e}")
        return None
    except Exception as e:
        print(f"Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return None


def generate_reports_only(root_dir: Path, aiida: bool = False, skip_errors: bool = False, calculation_type: str = "all", output_dir: Path | None = None, engine_type: str | None = None, from_date: str | None = None) -> None:
    """
    Scan a calculation tree, print a short summary to stdout
    and save a summary CSV plus error reports.

    Parameters:
    - output_dir: Directory to save CSV and reports. Defaults to /tmp/.
    - calculation_type: Filter by calculation type: "all", "optimise", "scf", "properties".
    - engine_type: Filter by engine: None (all), "crystal", or "fleur".
    - from_date: Only include calculations modified on or after this date (YYYY-MM-DD).
    """
    root_path = Path(root_dir).resolve()
    if not root_path.exists():
        print(f"Directory does not exist: {root_path}")
        return

    save_dir = Path(output_dir) if output_dir else Path("/tmp")

    print("\n" + "=" * 60)
    print("GENERATING REPORTS FOR ALL CALCULATIONS")
    print("=" * 60 + "\n")

    summary_store, err_cr, err_fl, phonon_store = scan_calculations(
        root_path,
        aiida=aiida,
        verbose=True,
        skip_errors=skip_errors,
        calculation_type=calculation_type,
        engine_type=engine_type,
    )

    if from_date and summary_store:
        from datetime import datetime
        cutoff = datetime.strptime(from_date, "%Y-%m-%d")
        summary_store = [
            s for s in summary_store
            if s.get("calc_date") and datetime.strptime(s["calc_date"], "%Y-%m-%d %H:%M:%S") >= cutoff
        ]

    save_reports(root_path, summary_store, err_cr, err_fl, phonon_store=phonon_store, output_dir=save_dir)

    print("\n" + "=" * 60)
    print("REPORTS GENERATION COMPLETE")
    print("=" * 60 + "\n")


if __name__ == "__main__":

    # summary_store, err_cr, err_fl, phonon_store = scan_calculations(Path("/data/aiida"), aiida=True, verbose=True)
    # root_path = Path("./")
    # save_reports(root_path, summary_store, err_cr, err_fl, phonon_store=phonon_store)

    generate_reports_only(Path("/root/projects/dft_organizer/dft_organizer/fleur_data_part"), aiida=True, skip_errors=True)
