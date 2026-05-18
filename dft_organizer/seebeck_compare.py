import json
import re
import math
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import polars as pl


_ALL_ELEMENTS = {
    "H", "He", "Li", "Be", "B", "C", "N", "O", "F", "Ne",
    "Na", "Mg", "Al", "Si", "P", "S", "Cl", "Ar", "K", "Ca",
    "Sc", "Ti", "V", "Cr", "Mn", "Fe", "Co", "Ni", "Cu", "Zn",
    "Ga", "Ge", "As", "Se", "Br", "Kr", "Rb", "Sr", "Y", "Zr",
    "Nb", "Mo", "Tc", "Ru", "Rh", "Pd", "Ag", "Cd", "In", "Sn",
    "Sb", "Te", "I", "Xe", "Cs", "Ba", "La", "Ce", "Pr", "Nd",
    "Pm", "Sm", "Eu", "Gd", "Tb", "Dy", "Ho", "Er", "Tm", "Yb",
    "Lu", "Hf", "Ta", "W", "Re", "Os", "Ir", "Pt", "Au", "Hg",
    "Tl", "Pb", "Bi", "Po", "At", "Rn", "Fr", "Ra", "Ac", "Th",
    "Pa", "U", "Np", "Pu",
}

_ELEMENTS_SORTED = sorted(_ALL_ELEMENTS, key=lambda x: (-len(x), x))
_ELEM_RE = re.compile("|".join(_ELEMENTS_SORTED))


def _parse_formula(formula: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    pos = 0
    while pos < len(formula):
        m = _ELEM_RE.match(formula, pos)
        if not m:
            pos += 1
            continue
        elem = m.group()
        pos = m.end()
        num_match = re.match(r"(\d+)", formula[pos:])
        if num_match:
            num = int(num_match.group())
            pos += num_match.end()
        else:
            num = 1
        counts[elem] = counts.get(elem, 0) + num
    return counts


def normalize_formula(formula: str) -> str:
    if not formula or not isinstance(formula, str):
        return formula

    formula_title = _capitalize_elements(formula)
    counts = _parse_formula(formula_title)
    if not counts:
        return formula

    g = 0
    for v in counts.values():
        g = math.gcd(g, v) if g else v
    if g > 1:
        counts = {k: v // g for k, v in counts.items()}

    return "".join(k if counts[k] == 1 else f"{k}{counts[k]}" for k in sorted(counts.keys()))


def _capitalize_elements(formula: str) -> str:
    """Convert formula to proper element capitalization.

    Greedily matches element symbols: try 2-letter (e.g. Ba, Al, As) before 1-letter.
    E.g. 'OBA' -> 'OBa', 'ASAL' -> 'AsAl', 'O2SRCU' -> 'O2SrCu'
    """
    result = []
    i = 0
    while i < len(formula):
        if formula[i].isdigit():
            result.append(formula[i])
            i += 1
            while i < len(formula) and formula[i].isdigit():
                result.append(formula[i])
                i += 1
        elif formula[i].isupper():
            if i + 1 < len(formula) and formula[i + 1].islower():
                result.append(formula[i] + formula[i + 1])
                i += 2
            elif i + 1 < len(formula) and formula[i + 1].isupper() and (formula[i] + formula[i + 1].lower()) in _ALL_ELEMENTS:
                result.append(formula[i] + formula[i + 1].lower())
                i += 2
            else:
                result.append(formula[i])
                i += 1
        else:
            result.append(formula[i])
            i += 1
    return "".join(result)


def _load_mpds_seebeck(mpds_dir: str | Path) -> pl.DataFrame:
    mpds_path = Path(mpds_dir).resolve()
    if mpds_path.is_file():
        return _read_mpds_csv(mpds_path)

    csv_files = sorted(mpds_path.glob("*.csv"))
    if not csv_files:
        raise FileNotFoundError(f"No CSV files found in {mpds_path}")

    dfs = []
    for f in csv_files:
        try:
            df = _read_mpds_csv(f)
            dfs.append(df)
        except Exception:
            pass

    if not dfs:
        raise FileNotFoundError(f"No valid CSV files in {mpds_path}")

    return pl.concat(dfs)


def _read_mpds_csv(path: Path) -> pl.DataFrame:
    df = pl.read_csv(path)
    col_types = {
        "phase_id": pl.Int64,
        "formula": pl.String,
        "sg": pl.Int64,
        "entry": pl.String,
        "seebeck": pl.Float64,
        "temperature": pl.Float64,
    }
    casts = []
    for col, dtype in col_types.items():
        if col in df.columns and df[col].dtype != dtype:
            casts.append(pl.col(col).cast(dtype))
    if casts:
        df = df.with_columns(casts)
    return df


def compare_seebeck(
    csv_path: str | Path,
    mpds_dir: str | Path,
    output_dir: str | Path | None = None,
) -> pl.DataFrame:
    """
    Read a summary CSV, extract Seebeck calculations, and compare with MPDS data.

    One row per formula. s_fleur and s_crystal merged into the same row.
    Multiple rows only if there are multiple calculations with the same engine.

    Output columns: chem_formula, s_fleur, s_crystal, s_mpds, sg_mpds, calc_date_fleur, calc_date_crystal, temp, mu_fleur, mu_crystal
    """
    df = pl.read_csv(csv_path)

    seeb = df.filter(
        pl.col("seebeck_coefficient_uvk").is_not_null()
    )
    seeb = seeb.filter(
        pl.col("seebeck_coefficient_uvk").cast(pl.Float64).is_not_nan()
    )

    if seeb.height == 0:
        print("No Seebeck data found in CSV.")
        return pl.DataFrame()

    mpds_df = _load_mpds_seebeck(mpds_dir)

    mpds_lookup: dict[str, list[dict]] = {}
    for row in mpds_df.iter_rows(named=True):
        formula = normalize_formula(row.get("formula", ""))
        if formula not in mpds_lookup:
            mpds_lookup[formula] = []
        mpds_lookup[formula].append({
            "phase_id": row.get("phase_id"),
            "s_mpds": row.get("seebeck"),
            "sg_mpds": row.get("sg"),
        })

    formula_entries: dict[str, dict[str, list[dict]]] = defaultdict(lambda: {"fleur": [], "crystal": []})
    for row_data in seeb.iter_rows(named=True):
        formula = normalize_formula(row_data.get("chemical_formula", ""))
        engine = row_data.get("engine", "")
        seebeck_val = row_data.get("seebeck_coefficient_uvk")
        mu = row_data.get("mu_ev")
        temp = row_data.get("temperature_k")
        calc_date = row_data.get("calc_date", "")

        entry = {
            "s_val": round(float(seebeck_val), 6) if seebeck_val is not None else None,
            "mu": mu,
            "temp": temp,
            "calc_date": calc_date,
        }
        if engine == "fleur":
            formula_entries[formula]["fleur"].append(entry)
        elif engine == "crystal":
            formula_entries[formula]["crystal"].append(entry)

    rows = []
    for formula in sorted(formula_entries.keys()):
        fleur_list = formula_entries[formula]["fleur"]
        crystal_list = formula_entries[formula]["crystal"]

        max_rows = max(len(fleur_list), len(crystal_list), 1)

        mpds_matches = mpds_lookup.get(formula, [])

        for i in range(max_rows):
            fleur = fleur_list[min(i, len(fleur_list) - 1)] if fleur_list else None
            crystal = crystal_list[min(i, len(crystal_list) - 1)] if crystal_list else None

            temp = None
            if fleur:
                temp = fleur.get("temp")
            elif crystal:
                temp = crystal.get("temp")

            if mpds_matches:
                for mpds in mpds_matches:
                    rows.append({
                        "chem_formula": formula,
                        "s_fleur": fleur["s_val"] if fleur else None,
                        "s_crystal": crystal["s_val"] if crystal else None,
                        "s_mpds": round(float(mpds["s_mpds"]), 6) if mpds["s_mpds"] is not None else None,
                        "sg_mpds": mpds["sg_mpds"],
                        "calc_date_fleur": fleur["calc_date"] if fleur else None,
                        "calc_date_crystal": crystal["calc_date"] if crystal else None,
                        "temp": temp,
                        "mu_fleur": fleur["mu"] if fleur else None,
                        "mu_crystal": crystal["mu"] if crystal else None,
                    })
            else:
                rows.append({
                    "chem_formula": formula,
                    "s_fleur": fleur["s_val"] if fleur else None,
                    "s_crystal": crystal["s_val"] if crystal else None,
                    "s_mpds": None,
                    "sg_mpds": None,
                    "calc_date_fleur": fleur["calc_date"] if fleur else None,
                    "calc_date_crystal": crystal["calc_date"] if crystal else None,
                    "temp": temp,
                    "mu_fleur": fleur["mu"] if fleur else None,
                    "mu_crystal": crystal["mu"] if crystal else None,
                })

    result = pl.DataFrame(rows)

    if output_dir is None:
        output_dir = Path(csv_path).parent
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    time_now = datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
    csv_out = output_dir / f"seebeck_comparison_{time_now}.csv"
    result.write_csv(csv_out)
    print(f"Seebeck comparison saved to: {csv_out}")

    json_out = output_dir / f"seebeck_comparison_{time_now}.json"
    with open(json_out, "w") as f:
        json.dump(rows, f, indent=2, default=str)
    print(f"Seebeck comparison JSON saved to: {json_out}")

    return result