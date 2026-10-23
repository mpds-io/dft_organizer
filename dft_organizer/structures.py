"""Lightweight structure helpers shared by parsers and reporting modules.

Kept separate from ``dft_organizer.utils`` to avoid a circular import:
``utils`` imports the CRYSTAL/FLEUR parsers, which in turn need these
helpers, so they live here with no dependency on the parsers.
"""
from __future__ import annotations

import math
import warnings


def get_space_group_robust(cell, positions, numbers) -> int | None:
    """Determine space-group number via spglib with a tolerant fallback chain.

    Tries ``spglib.get_symmetry_dataset`` at the default ``symprec`` (1e-5),
    then at a looser ``1e-4``; if both fail, standardizes the cell and retries.
    Returns ``None`` when symmetry cannot be determined. Emits a warning when
    all attempts fail so silent empty ``space_group`` columns are easier to
    diagnose.
    """
    try:
        import spglib
    except ImportError:
        return None

    args = (cell, positions, numbers)

    for symprec in (1e-5, 1e-4):
        try:
            dataset = spglib.get_symmetry_dataset(args, symprec=symprec)
            if dataset is not None and dataset.number is not None:
                return dataset.number
        except Exception as e:
            warnings.warn(f"spglib.get_symmetry_dataset(symprec={symprec}) raised: {e}")

    try:
        standardized = spglib.standardize_cell(args, to_primitive=False)
        if standardized is not None:
            dataset = spglib.get_symmetry_dataset(standardized, symprec=1e-4)
            if dataset is not None and dataset.number is not None:
                return dataset.number
    except Exception as e:
        warnings.warn(f"spglib standardize fallback raised: {e}")

    return None


def composition_n_atoms(chemical_formula: str | None, n_atoms: int | None) -> str:
    """Compact ML descriptor: ``"Al2O3|10"`` (formula + atom count in unit cell).

    Returns an empty string when the formula is missing.
    """
    if not chemical_formula:
        return ""
    n = n_atoms if n_atoms is not None else ""
    return f"{chemical_formula}|{n}"


def format_cell_compact(a, b, c, alpha, beta, gamma) -> str:
    """Compact human-readable cell string for the CSV table.

    Drops the angles when all are 90° (within ±0.5° tolerance), otherwise
    appends ``alpha beta gamma``. Inputs are expected to be numbers (floats).
    NaN values are rendered as ``""``.
    """

    def _is_nan(v) -> bool:
        try:
            return v is None or (isinstance(v, float) and math.isnan(v))
        except Exception:
            return True

    if any(_is_nan(v) for v in (a, b, c)):
        return ""

    lengths = f"{a:.4g} {b:.4g} {c:.4g}"
    angles = (alpha, beta, gamma)
    if any(_is_nan(v) for v in angles):
        return lengths
    if all(abs(float(v) - 90.0) <= 0.5 for v in angles):
        return lengths
    return f"{lengths} {float(alpha):.4g} {float(beta):.4g} {float(gamma):.4g}"


def nullify_right_angles(row: dict) -> None:
    """Set ``alpha/beta/gamma`` to ``None`` when all three are ~90° (±0.5°).

    Mutates the row in place. Keeps the CSV compact for cubic/orthorhombic
    cells where the angles carry no information. Non-right angles are kept
    untouched. Missing/NaN angles are left as-is.
    """
    angles = ("alpha", "beta", "gamma")
    vals = []
    for k in angles:
        v = row.get(k)
        if v is None:
            return
        try:
            vals.append(float(v))
        except (TypeError, ValueError):
            return
    if all(abs(v - 90.0) <= 0.5 for v in vals):
        for k in angles:
            row[k] = None