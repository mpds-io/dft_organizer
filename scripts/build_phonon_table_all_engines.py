"""Build a combined three-engine phonon table for the campaign compounds.

Scans AiiDA for FLEUR, ABACUS and CRYSTAL phonon results, keeps only the
allowlisted compounds, and writes phonon_summary_<timestamp>.csv/json via
the standard reporting pipeline. Duplicate runs collapse to the latest
successful one per (formula, engine).

Two campaign nodes need special handling. The YAlO3/62 ABACUS baseline
(pk 137662) predates the force-order fix, so its force constants are taken
from the corrected audit npz given via --yalo3-fc. The MgO/225 ABACUS run
(pk 141508) stored compact force constants, which the summary path rejects,
so they are symmetrized to the full form first.

The CaTiO3/62 FLEUR reference exists only as the manual October force set
(pks 136166/136167), assembled by hand from converged FLEUR SCFs on the
same structure and displacement grid as the ABACUS phase. The regular FLEUR
workchain scan does not see it, so its row is built from that data directly.

Usage:
    python scripts/build_phonon_table_all_engines.py \
        [--output-dir PATH] [--yalo3-fc PATH] [--yalo3-audit PATH]

Input:
    AiiDA database (active profile) and, when the YAlO3 baseline is in
    range, the corrected force constants npz from the campaign audit.

Output:
    phonon_summary_<timestamp>.csv and phonon_summary_<timestamp>.json
    in the output directory.
"""

import argparse
from pathlib import Path

import numpy as np

COMPOUNDS = [
    "GaP",
    "InSb",
    "LaAlO3",
    "YAlO3",
    "Al2O3",
    "MgAl2O4",
    "CaTiO3",
    "NaCl",
    "BN",
    "ZnS",
    "GaAs",
    "SiC",
    "ZnO",
    "SrTiO3",
    "BaTiO3",
    "KNbO3",
    "Cu2O",
    "MgO",
]
FROM_DATE = "2026-08-01"
YALO3_UUID = "500a10b7-9019-4bf3-be17-9ca1d2a56b20"
MGO_PK = 141508
CATIO3_PHONOPY_PK = 136166
CATIO3_FC_PK = 136167


def manual_catio3_fleur_row(t_max, t_step, t_min, method, t_eval):
    """Summary row for the manual October FLEUR CaTiO3/62 force set."""
    from aiida.orm import load_node
    from ase.geometry import cell_to_cellpar
    from phonopy import Phonopy

    from dft_organizer.phonon_utils import (
        DEFAULT_MESH,
        DEFAULT_THRESHOLD_CM1,
        VaspToCm,
        compute_pearson_symbol,
        extract_gamma_freqs,
        get_mpds_phonon_reference,
        integrate_frequencies,
    )

    inst = load_node(CATIO3_PHONOPY_PK).get_phonopy_instance()
    inst.produce_force_constants()
    unitcell = inst.unitcell

    ph = Phonopy(
        unitcell,
        supercell_matrix=inst.supercell_matrix,
        factor=VaspToCm,
    )
    ph.force_constants = inst.force_constants
    ph.symmetrize_force_constants()
    ph.run_mesh(DEFAULT_MESH)
    mesh_data = ph.get_mesh_dict()
    freqs = np.array(mesh_data["frequencies"])
    qpoints = np.array(mesh_data["qpoints"])
    ph.run_qpoints([[0.0, 0.0, 0.0]])
    gamma_freqs = np.array(ph.get_qpoints_dict()["frequencies"])[0]

    fc_node = load_node(CATIO3_FC_PK)
    cell = np.array(unitcell.cell)
    positions = np.array(unitcell.scaled_positions)
    numbers = np.array(unitcell.numbers)
    cellpar = cell_to_cellpar(cell)
    duration = None
    if fc_node.ctime and fc_node.mtime:
        duration = round((fc_node.mtime - fc_node.ctime).total_seconds() / 3600, 4)

    summary = {
        "pk": CATIO3_FC_PK,
        "label": fc_node.label,
        "engine": "fleur",
        "exit_status": fc_node.exit_status,
        "calc_date": fc_node.ctime.strftime("%Y-%m-%d %H:%M:%S"),
        "duration": duration,
        "chemical_formula": "CaTiO3",
        "space_group": 62,
        "pearson": compute_pearson_symbol(cell, positions, numbers),
        "n_imaginary": int(np.sum(freqs < DEFAULT_THRESHOLD_CM1)),
        "n_qpoints": int(freqs.shape[0]),
        "n_bands": int(freqs.shape[1]),
        "a": round(float(cellpar[0]), 6),
        "b": round(float(cellpar[1]), 6),
        "c": round(float(cellpar[2]), 6),
        "alpha": round(float(cellpar[3]), 6),
        "beta": round(float(cellpar[4]), 6),
        "gamma": round(float(cellpar[5]), 6),
    }

    thermo = integrate_frequencies(
        freqs,
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

    gamma_opt = extract_gamma_freqs(freqs, qpoints=qpoints, gamma_freqs_cm1=gamma_freqs)
    for i in range(12):
        summary[f"gamma_opt_{i + 1}_cm1"] = (
            round(gamma_opt[i], 2) if i < len(gamma_opt) else None
        )
    summary["gamma_n_optical"] = len(gamma_opt)

    mpds = get_mpds_phonon_reference("CaTiO3", 62)
    summary["mpds_lo_cm1"] = ", ".join(f"{v:.1f}" for v in mpds["lo_cm1"]) or None
    summary["mpds_to_cm1"] = ", ".join(f"{v:.1f}" for v in mpds["to_cm1"]) or None
    summary["mpds_n_entries"] = mpds["n_entries"]
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path.cwd())
    parser.add_argument(
        "--yalo3-fc",
        type=Path,
        help="corrected YAlO3 force constants npz from the campaign audit",
    )
    parser.add_argument(
        "--yalo3-audit",
        type=Path,
        help="force order audit JSON recorded in the provenance columns",
    )
    args = parser.parse_args()

    from aiida import load_profile

    load_profile()
    from aiida.orm import load_node

    yalo3_pk = load_node(YALO3_UUID).pk

    from dft_organizer.aiida.reporting import save_aiida_phonon_reports
    from dft_organizer.phonon_utils import (
        get_phonon_workchain_summary,
        scan_phonon_workchains,
    )

    store = scan_phonon_workchains(from_date=FROM_DATE, skip_errors=True)
    scanned_pks = {row.get("pk") for row in store}
    before = len(store)
    store = [row for row in store if row.get("chemical_formula") in COMPOUNDS]
    print(f"allowlist: {before} -> {len(store)} rows")

    if yalo3_pk in scanned_pks:
        if args.yalo3_fc is None or not args.yalo3_fc.is_file():
            raise SystemExit(
                f"YAlO3 pk {yalo3_pk} needs the corrected force constants: "
                "pass --yalo3-fc <npz>"
            )
        store = [row for row in store if row.get("pk") != yalo3_pk]
        if args.yalo3_audit is None:
            raise SystemExit("Corrected force constants require --yalo3-audit")
        from aiida.orm import load_node
        from dft_organizer.phonon_utils import load_audited_force_constants

        fc = load_audited_force_constants(
            load_node(yalo3_pk), args.yalo3_fc, args.yalo3_audit
        )
        summary = get_phonon_workchain_summary(yalo3_pk, force_constants_override=fc)
        summary["engine"] = "abacus"
        summary["force_order_corrected"] = True
        if args.yalo3_audit is not None:
            summary["force_order_audit"] = str(args.yalo3_audit)
        summary["force_constants_source"] = str(args.yalo3_fc)
        store.append(summary)
        print(f"YAlO3 pk {yalo3_pk}: rebuilt with corrected force constants")

    if MGO_PK in scanned_pks:
        from aiida.orm import load_node

        store = [row for row in store if row.get("pk") != MGO_PK]
        inst = load_node(MGO_PK).outputs.phonopy_data.get_phonopy_instance()
        inst.produce_force_constants()
        summary = get_phonon_workchain_summary(
            MGO_PK, force_constants_override=inst.force_constants
        )
        summary["engine"] = "abacus"
        summary["force_order_corrected"] = False
        summary["force_constants_source"] = "stored compact FC expanded to full form"
        store.append(summary)
        print(f"MgO pk {MGO_PK}: rebuilt from compact force constants")

    store.append(
        manual_catio3_fleur_row(
            t_max=1000, t_step=100, t_min=0, method="custom", t_eval=300
        )
    )
    print(f"CaTiO3 manual FLEUR reference pk {CATIO3_FC_PK}: added")

    for row in store:
        if row.get("engine") == "abacus":
            row.setdefault("force_order_corrected", False)
            row.setdefault("force_order_audit", None)
            row.setdefault("force_constants_source", None)

    if not store:
        print("Nothing to save.")
        return 1
    save_aiida_phonon_reports(store, output_dir=args.output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
