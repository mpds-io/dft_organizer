## Context

`dft_organizer` currently parses "electronic" outputs of CRYSTAL (`OUTPUT`/`OUTPUT_prop`) and FLEUR (`out`/`out.xml`) into a flat `summary` dictionary and saves `summary_<ts>.csv` + text error reports. Phonon calculations (separate CalcJobs with `PHONON.DAT`/`FREQ.DAT` for CRYSTAL and `phonon.*` for FLEUR) are only detected in `aiida/export.py` (files are copied into archives) and in `aiida/reporting.py` they are lumped into the `properties` category, but their content is **never parsed**. As a result:

- the summary CSV does not reflect whether phonon data is available for a material;
- there is no dedicated table with detailed phonon characteristics;
- to analyse stability/thermodynamics the user manually opens `PHONON.DAT`.

Parser architecture: `crystal_parser/` and `fleur_parser/` encapsulate engine-specific parsing; `reporting.py` orchestrates tree traversal and aggregation. Properties are already split into `crystal_parser/properties/` (see `seebeck.py`), which sets the placement pattern for the phonon parser. Constraints: no heavy new dependencies (phonopy, etc.) may be introduced — parsing reads raw text/binary engine files directly; backward compatibility of CSV columns must be preserved.

## Goals / Non-Goals

**Goals:**
- Parse CRYSTAL phonon outputs (`PHONON.DAT`, `FREQ.DAT`) into a structured dictionary (summary + detailed modes).
- Parse FLEUR phonon outputs (where the format is available); for unsupported variants — graceful no-op.
- Augment the main `summary` with compact phonon fields (`has_phonons`, `phonon_freq_min`, `phonon_freq_max`, `phonon_n_imag`, `phonon_modes_count`).
- Produce a separate `phonon_summary_<ts>.csv` with a detailed phonon breakdown per calculation.
- Integrate into the existing `dft-report` pipeline without new mandatory CLI flags.

**Non-Goals:**
- Plotting phonon dispersion curves — data only.
- Full thermodynamics computation (Cv, S, F) from phonons; take only what is already in the files, or simple aggregates (min/max/n_imag).
- Support for `phonopy`/external libraries — raw-file parsing only.
- Changes to AiiDA export/archiving (only reading already-detected files).
- AiiDA DB schema modifications.

## Decisions

### 1. Parser placement: engine-specific subpackages
**Decision:** `dft_organizer/crystal_parser/properties/phonon.py` (mirroring `seebeck.py`) and `dft_organizer/fleur_parser/phonon.py`.
**Why:** follows the established pattern (`crystal_parser/properties/seebeck.py`), keeps engine isolation, simplifies testing. Alternative — a single `phonon_parser/` outside engines — rejected as it breaks the existing code organisation.

### 2. Parser signature
**Decision:** `parse_phonon_output(path: Path, engine: str) -> dict | None`. Returns `None` if the file is not found / format unsupported; otherwise a dictionary with `summary` (flat) and `details` (list of modes/frequencies) keys. `parse_phonon_output` is exported from `crystal_parser/__init__.py` and `fleur_parser/__init__.py`.
**Why:** unifies with existing `parse_crystal_output`/`parse_fleur_output` by signature (Path -> dict). Alternative — two separate calls — rejected in favour of a single orchestrator.

### 3. Summary format (main fields)
**Decision:** the main `summary` receives 5 compact fields:
- `has_phonons: bool` — whether a file was present and successfully parsed;
- `phonon_freq_min: float | None` (THz, minimum across all modes; imaginary < 0);
- `phonon_freq_max: float | None` (THz, maximum);
- `phonon_n_imag: int | None` — number of imaginary (unstable) modes (below threshold, e.g. `-1e-3` THz);
- `phonon_modes_count: int | None` — total number of modes (across q-points).

The detailed `phonon_summary` contains: `uuid`, `engine`, `chemical_formula`, `output_path` (phonon file), `q_point` (if applicable), `branch_index`, `frequency_thz`, `is_imaginary`, `temperature_k` (if available), `modes_count`.

**Why:** flat fields in `summary` serialise easily to CSV and do not break existing columns (additive). Details go in a separate table.

### 4. Phonon file detection
**Decision:** in `scan_calculations` add detection: for CRYSTAL — presence of `PHONON.DAT` or `FREQ.DAT`; for FLEUR — files matching glob `phonon*` / `phono*` (exact set to be refined during implementation on real data). When found, call `parse_phonon_output` and add fields to `summary`. A separate `phonon_store` list collects detailed records.
**Why:** minimal intrusion into `scan_calculations`, preserves the current `os.walk` loop. Alternative — a separate `scan_phonons(root_dir)` pass — rejected: duplicates filesystem traversal; may still be a thin wrapper calling the same `os.walk`.

### 5. Writing `phonon_summary_<ts>.csv`
**Decision:** extend `save_reports` with an additional `phonon_store: list[dict]` parameter. When the list is non-empty, write `phonon_summary_<ts>.csv` (polars) alongside `summary_<ts>.csv`. `save_reports` is called from `generate_reports_only` (passes `phonon_store`).
**Why:** reuses the save point, single timestamp. The return of `scan_calculations` is extended: either a 4th `phonon_store` value, or a tuple object. Decision — **add a 4th element** `phonon_store` to the returned tuple of `scan_calculations`; update all call sites (2: `generate_reports_only`, `report_aiida_cli`, possibly `__main__`).
**Alternative:** return a dataclass — rejected to avoid overcomplicating the API.

### 6. FLEUR: phonon output format
**Decision:** at implementation time first investigate a representative FLEUR phonon calculation in `data_old/`/`reports/`. If no standard exists — `fleur_parser/phonon.py` returns `None` (graceful), `has_phonons=False`. Never crash.
**Why:** the FLEUR phonon format is variable; a rigid implementation is risky. CRYSTAL is the primary target (fixed `PHONON.DAT`/`FREQ.DAT`).

### 7. Imaginary-mode threshold
**Decision:** a mode is considered imaginary (unstable) if `frequency < -IMAG_THRESHOLD_THZ` with `IMAG_THRESHOLD_THZ = 1e-3` THz (module constant). Frequencies near zero are NOT counted as imaginary.
**Why:** numerical noise near zero; a deterministic threshold is needed for `phonon_n_imag`.

## Risks / Trade-offs

- **[FLEUR phonon format unknown in advance]** → Implementation starts with CRYSTAL; the FLEUR parser is a stub returning `None` with a TODO. Does not block the CRYSTAL release.
- **[Different units in `PHONON.DAT` (cm⁻¹ vs THz)]** → The parser explicitly normalises to THz (1 cm⁻¹ ≈ 0.02998 THz) and stores `frequency_unit="THz"`. Document in README.
- **[Summary-CSV size growth on large trees]** → Only 5 new columns; growth is negligible. The detailed `phonon_summary` grows linearly with modes × q-points — acceptable, the user can filter.
- **[Backward compatibility of `scan_calculations` API]** → Adding a 4th tuple element **may** break unpacking by external callers. → Mitigation: update all internal call sites; note the signature change in README; `[Risk] LOW` since the project is internal.
- **[Large `PHONON.DAT` (thousands of q-points)]** → Parse in a single pass, do not hold all modes in memory longer than necessary; `details` are aggregated row by row.
- **[No phonon files for most calculations]** → Fields `has_phonons=False` and `phonon_* = None`; the detailed table is simply not written. Behaviour is identical to current.

## Migration Plan

1. Changes are purely additive; no schema/database migration.
2. Update internal `scan_calculations` call sites (unpacking the 4-element tuple) in `reporting.py`, `aiida/reporting.py`, CLI modules.
3. Update README: new summary fields and the `phonon_summary_<ts>.csv` file.
4. Release: minor version (semver minor), no breaking change — but the `scan_calculations` signature is extended (document it).
5. Rollback: remove the new summary fields and do not call `parse_phonon_output`; the old CSV format is preserved.

## Open Questions

- The exact set and extensions of FLEUR phonon files — to be clarified during implementation on real data from `data_old/`/`reports/`.
- Whether temperature-dependent fields (`Cv`, `S`) are needed in `phonon_summary` — defer until the user decides; for now only min/max/n_imag/modes_count.
- Whether to add a CLI flag `--phonons/--no-phonons` to disable parsing — for now no, parsing is on by default (fast).