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
YALO3_PK = 137662
MGO_PK = 141508


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

    if YALO3_PK in scanned_pks:
        if args.yalo3_fc is None or not args.yalo3_fc.is_file():
            raise SystemExit(
                f"YAlO3 pk {YALO3_PK} needs the corrected force constants: "
                "pass --yalo3-fc <npz>"
            )
        store = [row for row in store if row.get("pk") != YALO3_PK]
        fc = np.load(args.yalo3_fc)["force_constants"]
        summary = get_phonon_workchain_summary(YALO3_PK, force_constants_override=fc)
        summary["engine"] = "abacus"
        summary["force_order_corrected"] = True
        if args.yalo3_audit is not None:
            summary["force_order_audit"] = str(args.yalo3_audit)
        summary["force_constants_source"] = str(args.yalo3_fc)
        store.append(summary)
        print(f"YAlO3 pk {YALO3_PK}: rebuilt with corrected force constants")

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
