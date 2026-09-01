"""Phonon utilities: extract frequencies from AiiDA WorkChains and integrate thermodynamic properties."""

from __future__ import annotations

import math
from typing import Any

import numpy as np

DEFAULT_MESH = [8, 8, 8]
DEFAULT_THRESHOLD_CM1 = -1.67
VaspToCm = 521.4708336735473

_CRYSTAL_SYSTEMS = {
    (1, 2): "a",
    (3, 15): "m",
    (16, 74): "o",
    (75, 142): "t",
    (143, 194): "h",
    (195, 230): "c",
}


def _crystal_letter(spg: int) -> str:
    for (lo, hi), letter in _CRYSTAL_SYSTEMS.items():
        if lo <= spg <= hi:
            return letter
    return "a"


def compute_pearson_symbol(cell, positions, numbers) -> str | None:
    import spglib

    dataset = spglib.get_symmetry_dataset((cell, positions, numbers))
    if dataset is None:
        return None
    spg = dataset.number
    centering = dataset.international[0] if dataset.international else "P"
    natoms = len(dataset.std_types)
    return f"{_crystal_letter(spg)}{centering}{natoms}"


def extract_frequencies_from_workchain(
    pk: int,
    mesh: list[int] | None = None,
    threshold: float = DEFAULT_THRESHOLD_CM1,
) -> dict[str, Any]:
    """Extract phonon frequencies from a PhonopyFleurWorkChain."""
    if mesh is None:
        mesh = DEFAULT_MESH

    from aiida.orm import load_node
    from phonopy import Phonopy
    from phonopy.structure.atoms import PhonopyAtoms

    wc = load_node(pk)
    has_fc = False
    try:
        has_fc = wc.outputs.output_phonopy.output_force_constants is not None
    except Exception:
        pass
    if not has_fc:
        return {
            "error": f"PK {pk} has no force constants (exit_status={wc.exit_status})"
        }

    structure = wc.inputs.structure
    supercell_matrix = np.array(wc.inputs.supercell_matrix.get_list())
    fc = wc.outputs.output_phonopy.output_force_constants.get_array("force_constants")

    ase_atoms = structure.get_ase()
    unitcell = PhonopyAtoms(
        symbols=ase_atoms.get_chemical_symbols(),
        cell=ase_atoms.get_cell(),
        scaled_positions=ase_atoms.get_scaled_positions(),
    )

    ph = Phonopy(unitcell, supercell_matrix=supercell_matrix, factor=VaspToCm)
    ph.force_constants = fc
    ph.symmetrize_force_constants()

    ph.run_mesh(list(mesh))
    mesh_data = ph.get_mesh_dict()
    all_freqs = np.array(mesh_data["frequencies"])
    qpoints = np.array(mesh_data["qpoints"])

    n_imag = int(np.sum(all_freqs < threshold))

    spg_info = None
    try:
        out_params = wc.outputs.output_phonopy.output_parameters.get_dict()
        spg_info = out_params.get("space_group", {})
    except Exception:
        pass

    return {
        "freqs_cm1": all_freqs,
        "qpoints": qpoints,
        "n_imaginary": n_imag,
        "n_qpoints": int(all_freqs.shape[0]),
        "n_bands": int(all_freqs.shape[1]),
        "space_group": spg_info.get("number") if spg_info else None,
        "space_group_type": spg_info.get("type") if spg_info else None,
    }


def integrate_frequencies(
    freqs_cm1: np.ndarray,
    t_max: int = 1000,
    t_step: int = 100,
    t_min: int = 0,
    method: str = "custom",
    t_eval: int = 300,
    threshold: float = DEFAULT_THRESHOLD_CM1,
) -> dict[str, Any]:
    """Integrate phonon thermodynamic properties from frequency array."""
    from ab_initio_calculations.calculations.phonon_thermo import (
        THZ_TO_CM1,
        Constants,
        _MockMesh,
        _integrate_one_ase,
    )

    n_qpoints = freqs_cm1.shape[0]
    n_imag = int(np.sum(freqs_cm1 < threshold))

    freqs_thz = freqs_cm1 / THZ_TO_CM1
    weights = np.ones(n_qpoints, dtype=int)

    if method == "phonopy":
        from phonopy.phonon.thermal_properties import ThermalProperties as PhTP

        mesh_obj = _MockMesh(freqs_thz, weights)
        tp = PhTP(mesh_obj, pretend_real=True)
        tp.run(t_min=t_min, t_max=t_max, t_step=t_step)
        temps, fe, entropy, cv = tp.thermal_properties
        zpe = float(tp.zero_point_energy)
    elif method == "custom":
        from ab_initio_calculations.calculations.phonon_thermo import ThermalProperties

        eigs = (freqs_thz / Constants.VaspToTHz) ** 2
        tp = ThermalProperties(eigs, weights)
        tp.set_thermal_properties(t_step=t_step, t_max=t_max, t_min=t_min)
        arr = tp.get_thermal_properties()
        temps, fe, entropy, cv = arr[0], arr[1], arr[2], arr[3]
        zpe = float(tp.get_zero_point_energy())
    elif method == "ase":
        res = _integrate_one_ase(freqs_thz, t_max, t_step, t_min)
        tp_arr = res["thermal_properties"]
        temps = tp_arr[:, 0]
        fe = tp_arr[:, 1]
        entropy = tp_arr[:, 2]
        cv = tp_arr[:, 3]
        zpe = res["zero_point_energy"]
    else:
        raise ValueError(f"Unknown method '{method}'. Valid: custom, phonopy, ase")

    if t_eval in list(temps):
        idx = list(temps).index(t_eval)
    else:
        idx = min(range(len(temps)), key=lambda i: abs(temps[i] - t_eval))

    return {
        "zpe_kjmol": zpe,
        "f_at_t_kjmol": float(fe[idx]),
        "s_at_t_jkmol": float(entropy[idx]),
        "cv_at_t_jkmol": float(cv[idx]),
        "n_imaginary": n_imag,
        "t_eval_actual": float(temps[idx]),
    }


def _get_reduced_formula(symbols: list[str]) -> str:
    from collections import Counter

    cnt = Counter(symbols)
    order = list(dict.fromkeys(symbols))
    g = 0
    for v in cnt.values():
        g = math.gcd(g, v) if g else v
    if g > 1:
        cnt = {k: v // g for k, v in cnt.items()}
    return "".join(k if cnt[k] == 1 else f"{k}{cnt[k]}" for k in order)


def get_phonon_workchain_summary(
    pk: int,
    mesh: list[int] | None = None,
    t_max: int = 1000,
    t_step: int = 100,
    t_min: int = 0,
    method: str = "custom",
    t_eval: int = 300,
    provider: str | None = None,
    machine_type: str | None = None,
) -> dict[str, Any]:
    """Get full phonon summary for a single PhonopyFleurWorkChain."""
    from aiida.orm import load_node

    wc = load_node(pk)
    exit_status = wc.exit_status

    structure = wc.inputs.structure
    ase_atoms = structure.get_ase()

    import spglib as _spglib

    cell = np.array(ase_atoms.get_cell())
    positions = np.array(ase_atoms.get_positions())
    numbers = np.array(ase_atoms.get_atomic_numbers())
    symbols = ase_atoms.get_chemical_symbols()

    dataset = _spglib.get_symmetry_dataset((cell, positions, numbers))
    space_group = dataset.number if dataset is not None else None
    pearson = compute_pearson_symbol(cell, positions, numbers) if dataset else None

    from ase.geometry import cell_to_cellpar as _cellpar

    cellpar = _cellpar(cell)

    from dft_organizer.pricing import resolve_provider_and_rate

    computer = None
    try:
        computer = wc.computer.label
    except Exception:
        pass

    duration = None
    if wc.ctime and wc.mtime:
        duration = round((wc.mtime - wc.ctime).total_seconds() / 3600, 4)

    cost = None
    currency = None
    cloud_rate = None
    if computer:
        try:
            prov, rate, curr = resolve_provider_and_rate(
                computer, provider=provider, machine_type=machine_type
            )
            if curr is not None:
                currency = curr
            if rate is not None:
                cloud_rate = rate
                if duration is not None and not (
                    isinstance(duration, float) and math.isnan(duration)
                ):
                    cost = round(duration * rate, 2)
        except Exception:
            pass

    summary: dict[str, Any] = {
        "pk": pk,
        "label": wc.label,
        "exit_status": exit_status,
        "calc_date": wc.ctime.strftime("%Y-%m-%d %H:%M:%S") if wc.ctime else None,
        "computer": computer,
        "duration": duration,
        "cost": cost,
        "currency": currency,
        "cloud_rate": cloud_rate,
        "chemical_formula": _get_reduced_formula(symbols),
        "space_group": space_group,
        "pearson": pearson,
        "a": round(cellpar[0], 6),
        "b": round(cellpar[1], 6),
        "c": round(cellpar[2], 6),
        "alpha": round(cellpar[3], 6),
        "beta": round(cellpar[4], 6),
        "gamma": round(cellpar[5], 6),
    }

    freq_data = extract_frequencies_from_workchain(pk, mesh=mesh)
    if "error" in freq_data:
        summary["error"] = freq_data["error"]
        summary["n_imaginary"] = None
        summary["n_qpoints"] = None
        summary["n_bands"] = None
        summary["zpe_kjmol"] = None
        summary["f_at_t_kjmol"] = None
        summary["s_at_t_jkmol"] = None
        summary["cv_at_t_jkmol"] = None
        summary["t_eval"] = t_eval
        return summary

    summary["n_imaginary"] = freq_data["n_imaginary"]
    summary["n_qpoints"] = freq_data["n_qpoints"]
    summary["n_bands"] = freq_data["n_bands"]

    thermo = integrate_frequencies(
        freq_data["freqs_cm1"],
        t_max=t_max,
        t_step=t_step,
        t_min=t_min,
        method=method,
        t_eval=t_eval,
    )
    summary["zpe_kjmol"] = thermo["zpe_kjmol"]
    summary["f_at_t_kjmol"] = thermo["f_at_t_kjmol"]
    summary["s_at_t_jkmol"] = thermo["s_at_t_jkmol"]
    summary["cv_at_t_jkmol"] = thermo["cv_at_t_jkmol"]
    summary["t_eval"] = t_eval

    return summary


def extract_frequencies_from_crystal_calc(pk: int) -> dict[str, Any]:
    """Extract phonon frequencies from a CRYSTAL phonon CalcJobNode.

    Parses the MODES block from the retrieved OUTPUT file and groups
    frequencies into q-points (each block of n_modes lines = one q-point).

    Returns dict with freqs_cm1, n_imaginary, n_qpoints, n_bands.
    """
    from aiida.orm import load_node
    from dft_organizer.crystal_parser import parse_phonon_from_output

    calc = load_node(pk)
    retrieved = calc.outputs.retrieved
    output_text = retrieved.base.repository.get_object_content("OUTPUT")
    if not output_text:
        return {"error": f"PK {pk}: no OUTPUT in retrieved"}

    parsed = parse_phonon_from_output(output_text)
    if not parsed or not parsed.get("has_phonons"):
        return {"error": f"PK {pk}: no phonon frequencies in OUTPUT"}

    details = parsed.get("details", [])
    n_modes = parsed.get("phonon_modes_count", 0)
    if not details or n_modes == 0:
        return {"error": f"PK {pk}: empty phonon details"}

    # Group details into q-points: each block of n_modes entries = one q-point
    n_qpoints = len(details) // n_modes
    freqs_thz = []
    for q in range(n_qpoints):
        block = details[q * n_modes : (q + 1) * n_modes]
        freqs_thz.append([d["frequency_thz"] for d in block])

    freqs_thz_arr = np.array(freqs_thz)
    # Convert THz → cm⁻¹
    from ab_initio_calculations.calculations.phonon_thermo import THZ_TO_CM1

    freqs_cm1 = freqs_thz_arr / THZ_TO_CM1

    n_imag = int(np.sum(freqs_cm1 < DEFAULT_THRESHOLD_CM1))

    return {
        "freqs_cm1": freqs_cm1,
        "n_imaginary": n_imag,
        "n_qpoints": int(n_qpoints),
        "n_bands": int(n_modes),
        # Also include CRYSTAL-specific summary columns
        "has_phonons": True,
        "phonon_freq_min": parsed["phonon_freq_min"],
        "phonon_freq_max": parsed["phonon_freq_max"],
        "phonon_freq_mean": parsed["phonon_freq_mean"],
        "phonon_freq_std": parsed["phonon_freq_std"],
        "phonon_n_imag": parsed["phonon_n_imag"],
        "phonon_modes_count": parsed["phonon_modes_count"],
    }


def get_crystal_phonon_summary(
    pk: int,
    t_max: int = 1000,
    t_step: int = 100,
    t_min: int = 0,
    method: str = "custom",
    t_eval: int = 300,
    provider: str | None = None,
    machine_type: str | None = None,
) -> dict[str, Any]:
    """Get full phonon summary for a CRYSTAL phonon CalcJobNode."""
    from aiida.orm import load_node

    calc = load_node(pk)
    exit_status = calc.exit_status

    # Structure from inputs
    structure = calc.inputs.structure
    ase_atoms = structure.get_ase()

    import spglib as _spglib

    cell = np.array(ase_atoms.get_cell())
    positions = np.array(ase_atoms.get_positions())
    numbers = np.array(ase_atoms.get_atomic_numbers())
    symbols = ase_atoms.get_chemical_symbols()

    dataset = _spglib.get_symmetry_dataset((cell, positions, numbers))
    space_group = dataset.number if dataset is not None else None
    pearson = compute_pearson_symbol(cell, positions, numbers) if dataset else None

    from ase.geometry import cell_to_cellpar as _cellpar

    cellpar = _cellpar(cell)

    from dft_organizer.pricing import resolve_provider_and_rate

    computer = None
    try:
        computer = calc.computer.label
    except Exception:
        pass

    duration = None
    if calc.ctime and calc.mtime:
        duration = round((calc.mtime - calc.ctime).total_seconds() / 3600, 4)

    cost = None
    currency = None
    cloud_rate = None
    if computer:
        try:
            prov, rate, curr = resolve_provider_and_rate(
                computer, provider=provider, machine_type=machine_type
            )
            if curr is not None:
                currency = curr
            if rate is not None:
                cloud_rate = rate
                if duration is not None and not (
                    isinstance(duration, float) and math.isnan(duration)
                ):
                    cost = round(duration * rate, 2)
        except Exception:
            pass

    summary: dict[str, Any] = {
        "pk": pk,
        "label": calc.label,
        "engine": "crystal",
        "exit_status": exit_status,
        "calc_date": calc.ctime.strftime("%Y-%m-%d %H:%M:%S") if calc.ctime else None,
        "computer": computer,
        "duration": duration,
        "cost": cost,
        "currency": currency,
        "cloud_rate": cloud_rate,
        "chemical_formula": _get_reduced_formula(symbols),
        "space_group": space_group,
        "pearson": pearson,
        "a": round(cellpar[0], 6),
        "b": round(cellpar[1], 6),
        "c": round(cellpar[2], 6),
        "alpha": round(cellpar[3], 6),
        "beta": round(cellpar[4], 6),
        "gamma": round(cellpar[5], 6),
    }

    freq_data = extract_frequencies_from_crystal_calc(pk)
    if "error" in freq_data:
        summary["error"] = freq_data["error"]
        for k in (
            "n_imaginary",
            "n_qpoints",
            "n_bands",
            "zpe_kjmol",
            "f_at_t_kjmol",
            "s_at_t_jkmol",
            "cv_at_t_jkmol",
            "has_phonons",
            "phonon_freq_min",
            "phonon_freq_max",
            "phonon_freq_mean",
            "phonon_freq_std",
            "phonon_n_imag",
            "phonon_modes_count",
        ):
            summary[k] = None
        summary["t_eval"] = t_eval
        return summary

    # CRYSTAL-specific columns
    summary["has_phonons"] = freq_data["has_phonons"]
    summary["phonon_freq_min"] = freq_data["phonon_freq_min"]
    summary["phonon_freq_max"] = freq_data["phonon_freq_max"]
    summary["phonon_freq_mean"] = freq_data["phonon_freq_mean"]
    summary["phonon_freq_std"] = freq_data["phonon_freq_std"]
    summary["phonon_n_imag"] = freq_data["phonon_n_imag"]
    summary["phonon_modes_count"] = freq_data["phonon_modes_count"]

    # Thermodynamic integration columns
    summary["n_imaginary"] = freq_data["n_imaginary"]
    summary["n_qpoints"] = freq_data["n_qpoints"]
    summary["n_bands"] = freq_data["n_bands"]

    thermo = integrate_frequencies(
        freq_data["freqs_cm1"],
        t_max=t_max,
        t_step=t_step,
        t_min=t_min,
        method=method,
        t_eval=t_eval,
    )
    summary["zpe_kjmol"] = thermo["zpe_kjmol"]
    summary["f_at_t_kjmol"] = thermo["f_at_t_kjmol"]
    summary["s_at_t_jkmol"] = thermo["s_at_t_jkmol"]
    summary["cv_at_t_jkmol"] = thermo["cv_at_t_jkmol"]
    summary["t_eval"] = t_eval

    return summary


def scan_phonon_workchains(
    from_date: str | None = None,
    to_date: str | None = None,
    skip_errors: bool = False,
    mesh: list[int] | None = None,
    t_max: int = 1000,
    t_step: int = 100,
    t_min: int = 0,
    method: str = "custom",
    t_eval: int = 300,
    provider: str | None = None,
    machine_type: str | None = None,
) -> list[dict[str, Any]]:
    """Scan AiiDA for phonon calculations (FLEUR WorkChains + CRYSTAL CalcJobs)."""
    from datetime import datetime

    from aiida.orm import QueryBuilder, WorkChainNode, CalcJobNode

    date_filter: dict[str, Any] = {}
    if from_date:
        date_filter[">="] = datetime.strptime(from_date, "%Y-%m-%d")
    if to_date:
        date_filter["<="] = datetime.strptime(to_date, "%Y-%m-%d")

    # --- FLEUR: PhonopyFleurWorkChain ---
    fleur_filters: dict[str, Any] = {"process_type": {"like": "%phonopy.fleur%"}}
    if date_filter:
        fleur_filters["ctime"] = date_filter

    print("Querying AiiDA for PhonopyFleurWorkChain nodes...")
    qb = QueryBuilder()
    qb.append(
        WorkChainNode,
        filters=fleur_filters,
        project=["id", "label", "attributes", "ctime", "mtime"],
    )
    fleur_rows = list(qb.iterall())
    print(f"Found {len(fleur_rows)} FLEUR phonon WorkChains.")

    # --- CRYSTAL: CalcJobNode with "phonon" in label ---
    crystal_filters: dict[str, Any] = {
        "process_type": {"like": "%crystal%"},
    }
    if date_filter:
        crystal_filters["ctime"] = date_filter

    print("Querying AiiDA for CRYSTAL phonon CalcJobs...")
    qb2 = QueryBuilder()
    qb2.append(
        CalcJobNode,
        filters=crystal_filters,
        project=["id", "label", "attributes", "ctime", "mtime"],
    )
    crystal_rows = [r for r in qb2.iterall() if r[1] and "phonon" in r[1].lower()]
    print(f"Found {len(crystal_rows)} CRYSTAL phonon CalcJobs.")

    # Filter by exit_status
    if skip_errors:
        fleur_rows = [r for r in fleur_rows if r[2] and r[2].get("exit_status") == 0]
        crystal_rows = [
            r for r in crystal_rows if r[2] and r[2].get("exit_status") == 0
        ]
        print(
            f"After skip_errors: {len(fleur_rows)} FLEUR, {len(crystal_rows)} CRYSTAL."
        )

    summary_store = []

    # Process FLEUR
    done = 0
    for pk, label, attrs, ctime, mtime in fleur_rows:
        try:
            summary = get_phonon_workchain_summary(
                pk,
                mesh=mesh,
                t_max=t_max,
                t_step=t_step,
                t_min=t_min,
                method=method,
                t_eval=t_eval,
                provider=provider,
                machine_type=machine_type,
            )
            summary["engine"] = "fleur"
            summary_store.append(summary)
        except Exception as e:
            summary_store.append(
                {
                    "pk": pk,
                    "label": label,
                    "engine": "fleur",
                    "exit_status": attrs.get("exit_status") if attrs else None,
                    "error": str(e),
                }
            )
        done += 1
        if done % 5 == 0 or done == len(fleur_rows):
            print(f"  FLEUR: {done}/{len(fleur_rows)}")

    # Process CRYSTAL
    done = 0
    for pk, label, attrs, ctime, mtime in crystal_rows:
        try:
            summary = get_crystal_phonon_summary(
                pk,
                t_max=t_max,
                t_step=t_step,
                t_min=t_min,
                method=method,
                t_eval=t_eval,
                provider=provider,
                machine_type=machine_type,
            )
            summary_store.append(summary)
        except Exception as e:
            summary_store.append(
                {
                    "pk": pk,
                    "label": label,
                    "engine": "crystal",
                    "exit_status": attrs.get("exit_status") if attrs else None,
                    "error": str(e),
                }
            )
        done += 1
        if done % 5 == 0 or done == len(crystal_rows):
            print(f"  CRYSTAL: {done}/{len(crystal_rows)}")

    return summary_store
