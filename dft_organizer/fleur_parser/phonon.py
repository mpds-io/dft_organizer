"""FLEUR phonon output parser.

FLEUR phonon outputs are not part of the standard ``out.xml`` and come in
multiple engine-specific formats (e.g. ``phonon.out``, ``photon`` files
produced by FLEUR's phonon workflow). The exact on-disk layout varies across
FLEUR versions and workflows and no representative sample is available in
this repository's test data.

This module therefore implements a graceful no-op: it scans the calculation
directory for candidate phonon files (glob ``phonon*`` / ``phono*``) and, if
none are recognized, returns ``None``. When a recognized format becomes
available, parsing can be added here without changing the public API.
"""

from __future__ import annotations

from pathlib import Path

_FLEUR_PHONON_GLOBS = ("phonon*", "phono*")


def _find_fleur_phonon_file(directory: Path) -> Path | None:
    for pattern in _FLEUR_PHONON_GLOBS:
        for p in directory.glob(pattern):
            if p.is_file():
                return p
    return None


def parse_phonon_output(path: Path, engine: str = "fleur") -> dict | None:
    """Parse a FLEUR phonon output file.

    Returns ``None`` when no recognized phonon file is present (graceful
    no-op). Never raises on missing/unsupported input.

    TODO: implement actual parsing once representative FLEUR phonon output
    files are available in the test data.
    """
    path = Path(path)

    if path.is_dir():
        candidate = _find_fleur_phonon_file(path)
        if candidate is None:
            return None
        target = candidate
    elif path.is_file():
        target = path
    else:
        return None

    name = target.name.lower()
    if not name.startswith(("phonon", "phono")):
        return None

    return None