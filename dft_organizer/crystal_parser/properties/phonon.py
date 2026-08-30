"""Parser for CRYSTAL phonon output files (PHONON.DAT, FREQ.DAT).

CRYSTAL writes phonon frequencies in cm^-1. This module normalizes to THz
(1 cm^-1 ≈ 0.02998 THz) and classifies imaginary (unstable) modes using a
threshold below -IMAG_THRESHOLD_THZ.

Also parses phonon frequencies directly from a CRYSTAL ``OUTPUT`` file,
where the frequencies are reported in the ``MODES ... EIGV ... FREQUENCIES
... (CM**-1) (THZ)`` blocks. This is the path used by the AiiDA-DB scan,
since the retrieved repository of CRYSTAL CalcJobNodes typically contains
only ``OUTPUT`` (not the standalone ``PHONON.DAT``/``FREQ.DAT`` files).
"""

from __future__ import annotations

import math
import re
from pathlib import Path

CM1_TO_THZ = 0.02998
IMAG_THRESHOLD_THZ = 1e-3

_MODES_HEADER_RE = re.compile(
    r"MODES\s+EIGV\s+FREQUENCIES[^\n]*\n[^\n]*\(CM\*\*-1\)\s*\(THZ\)",
    re.IGNORECASE,
)
_MODES_DATA_RE = re.compile(
    r"^\s*(\d+)\s*-\s*(\d+)\s+\S+\s+[-\d.]+\s+([-\d.]+)\s",
    re.MULTILINE,
)


def _freq_cm1_to_thz(freq_cm1: float) -> float:
    return freq_cm1 * CM1_TO_THZ


def _is_imaginary(freq_thz: float) -> bool:
    return freq_thz < -IMAG_THRESHOLD_THZ


def _parse_phonon_dat(path: Path) -> dict | None:
    """Parse a CRYSTAL PHONON.DAT file.

    Format (representative):
        header / comments
        q-point block(s) with mode frequencies in cm^-1

    The parser is tolerant: it scans numeric tokens and groups them into
    q-point blocks. Each block is expected to contain `n_modes` frequencies.
    When the number of modes per q-point cannot be inferred from a header,
    we assume the first numeric block (Γ point) holds the modes count and
    subsequent blocks of the same size are other q-points.
    """
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
    except Exception as e:
        print(f"Error reading phonon file {path}: {e}")
        return None

    q_points: list[tuple[float, float, float]] = []
    freqs_per_q: list[list[float]] = []

    lines = content.splitlines()
    current_q: tuple[float, float, float] | None = None
    current_freqs: list[float] = []

    for raw in lines:
        line = raw.strip()
        if not line:
            continue

        parts = line.split()
        floats: list[float] = []
        for p in parts:
            try:
                floats.append(float(p))
            except ValueError:
                pass

        if len(floats) >= 3 and len(floats) <= 4 and not current_freqs:
            q_candidate = (floats[0], floats[1], floats[2])
            if all(-1.0 <= c <= 1.0 + 1e-6 for c in q_candidate):
                if current_freqs:
                    q_points.append(current_q)
                    freqs_per_q.append(current_freqs)
                    current_freqs = []
                current_q = q_candidate
                continue

        if current_q is None and not current_freqs:
            current_q = (0.0, 0.0, 0.0)

        for v in floats:
            if math.isfinite(v):
                current_freqs.append(v)

    if current_freqs:
        q_points.append(current_q if current_q is not None else (0.0, 0.0, 0.0))
        freqs_per_q.append(current_freqs)

    if not freqs_per_q:
        return None

    n_modes = len(freqs_per_q[0])

    details: list[dict] = []
    all_freqs_thz: list[float] = []
    n_imag = 0

    for q, freqs in zip(q_points, freqs_per_q):
        for branch_index, f_cm1 in enumerate(freqs):
            f_thz = _freq_cm1_to_thz(f_cm1)
            imag = _is_imaginary(f_thz)
            if imag:
                n_imag += 1
            all_freqs_thz.append(f_thz)
            details.append({
                "q_point": list(q),
                "branch_index": branch_index,
                "frequency_thz": round(f_thz, 6),
                "is_imaginary": imag,
                "temperature_k": None,
            })

    if not all_freqs_thz:
        return None

    import statistics
    freq_mean = statistics.fmean(all_freqs_thz) if len(all_freqs_thz) > 0 else 0.0
    freq_std = statistics.pstdev(all_freqs_thz) if len(all_freqs_thz) > 1 else 0.0

    return {
        "has_phonons": True,
        "phonon_freq_min": round(min(all_freqs_thz), 6),
        "phonon_freq_max": round(max(all_freqs_thz), 6),
        "phonon_freq_mean": round(freq_mean, 6),
        "phonon_freq_std": round(freq_std, 6),
        "phonon_n_imag": n_imag,
        "phonon_modes_count": n_modes,
        "temperature_k": 0.0,
        "frequency_unit": "THz",
        "source_file": str(path),
        "details": details,
    }


def _parse_freq_dat(path: Path) -> dict | None:
    """Parse a CRYSTAL FREQ.DAT file (frequencies in cm^-1, one q-point block per line group)."""
    return _parse_phonon_dat(path)


def parse_phonon_output(path: Path, engine: str = "crystal") -> dict | None:
    """Parse a CRYSTAL phonon output file.

    Prefers ``PHONON.DAT``; falls back to ``FREQ.DAT``. Returns ``None`` when
    neither file is present or the file is unparseable. Never raises on
    missing/unsupported input.
    """
    path = Path(path)
    if path.is_dir():
        candidate = path / "PHONON.DAT"
        if candidate.is_file():
            return _parse_phonon_dat(candidate)
        candidate = path / "FREQ.DAT"
        if candidate.is_file():
            return _parse_freq_dat(candidate)
        return None

    if not path.is_file():
        return None

    name = path.name.upper()
    if name == "PHONON.DAT":
        return _parse_phonon_dat(path)
    if name == "FREQ.DAT":
        return _parse_freq_dat(path)

    try:
        return _parse_phonon_dat(path)
    except Exception:
        return None


def parse_phonon_from_output(text: str) -> dict | None:
    """Parse phonon frequencies from the text of a CRYSTAL ``OUTPUT`` file.

    Scans all ``MODES ... EIGV ... FREQUENCIES ... (CM**-1) (THZ)`` blocks and
    collects the per-mode THz values. Returns the same summary shape as
    ``parse_phonon_output`` (``has_phonons``, ``phonon_freq_min``,
    ``phonon_freq_max``, ``phonon_n_imag``, ``phonon_modes_count``,
    ``frequency_unit``, ``source_file``, ``details``). The ``details`` list
    has one entry per mode across all q-point blocks. Returns ``None`` when
    no MODES block is found.
    """
    if not text:
        return None

    headers = list(_MODES_HEADER_RE.finditer(text))
    if not headers:
        return None

    all_freqs_thz: list[float] = []
    details: list[dict] = []
    n_modes = 0
    n_imag = 0

    for block_idx, h in enumerate(headers):
        start = h.end()
        end = len(text)
        # bound by the next header or a clearly unrelated section
        for nxt in headers[block_idx + 1:]:
            if nxt.start() > start:
                end = min(end, nxt.start())
                break
        block = text[start:end]

        for m in _MODES_DATA_RE.finditer(block):
            mode_lo = int(m.group(1))
            mode_hi = int(m.group(2))
            freq_thz = float(m.group(3))
            if n_modes == 0:
                n_modes = mode_hi
            imag = _is_imaginary(freq_thz)
            if imag:
                n_imag += 1
            all_freqs_thz.append(freq_thz)
            for branch_index in range(mode_lo, mode_hi + 1):
                details.append({
                    "q_point": [None, None, None],
                    "branch_index": branch_index,
                    "frequency_thz": round(freq_thz, 6),
                    "is_imaginary": imag,
                    "temperature_k": None,
                })

    if not all_freqs_thz:
        return None

    import statistics
    freq_mean = statistics.fmean(all_freqs_thz) if len(all_freqs_thz) > 0 else 0.0
    freq_std = statistics.pstdev(all_freqs_thz) if len(all_freqs_thz) > 1 else 0.0

    return {
        "has_phonons": True,
        "phonon_freq_min": round(min(all_freqs_thz), 6),
        "phonon_freq_max": round(max(all_freqs_thz), 6),
        "phonon_freq_mean": round(freq_mean, 6),
        "phonon_freq_std": round(freq_std, 6),
        "phonon_n_imag": n_imag,
        "phonon_modes_count": n_modes,
        "temperature_k": 0.0,
        "frequency_unit": "THz",
        "source_file": None,
        "details": details,
    }