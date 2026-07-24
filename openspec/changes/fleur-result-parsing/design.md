## Context

The AiiDA-DB summary enrichment for FLEUR (`_enrich_fleur_extras` in `dft_organizer/aiida/reporting.py`) extracted only three things: Seebeck (via `_fetch_fleur_seebeck`), displacement (via `pg8000` direct DB connection), and a `scf`→`optimise` calc_type reclassification based on displacement. The local-filesystem scan (`dft_organizer/reporting.py`) already used `parse_fleur_output` to extract `bandgap` from `out.xml`, but the AiiDA-DB path never read the equivalent `output_parameters` output port available on every `fleur.fleur` CalcJobNode.

Two bugs and one missing filter were identified:

1. **Seebeck bug**: `_fetch_fleur_seebeck` called `.get_dict()` on `output_seebeck` and `output_dos_local_wc_para` nodes. These are `data.pythonjob.builtins.dict.Dict` (a custom plugin node type), not `aiida.orm.Dict`, so `.get_dict()` raises `AttributeError`. The `except Exception: return None` swallowed it silently, resulting in Seebeck being **never populated** for any FLEUR calculation (0/279 rows in the previous CSV). The data was physically present in `.base.attributes.all`.

2. **Missing `output_parameters` read**: FLEUR `fleur.fleur` CalcJobNodes expose an `output_parameters` port containing `bandgap` (eV), `energy` (total energy, eV), `fermi_energy` (Hartree), `spin_dependent_charge_total` (per-spin charges, magnetic moment = difference), `number_of_iterations_total`, `number_of_kpoints`, and many other fields. ~99% of successful `fleur.fleur` calcs have `bandgap` populated. The enrichment simply never read this port.

3. **`fleur.inpgen` clutter**: 2204 `fleur.inpgen` CalcJobNodes (input generator, no SCF results) were included in the FLEUR set, contributing 2204 null-result rows to the summary.

FLEUR phonon calculations (`phonopy.fleur` workchains, 8 nodes) are all unfinished (`exit_status=None`) with no frequency output port — no phonon data is available. The `fleur_parser/phonon.py` stub remains a no-op.

## Goals / Non-Goals

**Goals:**
- Fix the Seebeck `.get_dict()` bug so `seebeck_coefficient_uvk`, `mu_ev`, `temperature_k` are populated for FLEUR DOS calculations.
- Read `output_parameters` to populate `bandgap`, `total_energy`, `fermi_energy`, `magnetic_moment`, `n_iterations` for FLEUR SCF/DOS calculations.
- Filter out `fleur.inpgen` input-generator calculations from the summary.
- Add the four new columns to the CSV schema.

**Non-Goals:**
- FLEUR phonon parsing (no completed phonon workchains exist in the DB).
- Fixing the displacement `pg8000` performance issue (pre-existing, not introduced by this change).
- Changing the `scf`→`optimise` reclassification logic (unchanged).
- Adding a local-filesystem `output_parameters` equivalent (the local scan already uses `parse_fleur_output` from `out.xml`).

## Decisions

### 1. Seebeck fix: `.base.attributes.all` instead of `.get_dict()`
**Decision:** Replace `node.outputs.output_seebeck.get_dict()` with `node.outputs.output_seebeck.base.attributes.all` (and same for `output_dos_local_wc_para`). Apply in both `dft_organizer/aiida/reporting.py` (`_fetch_fleur_seebeck`, line 43–44) and `dft_organizer/reporting.py` (duplicate `_fetch_fleur_seebeck`, line 134–135).
**Why:** `.base.attributes.all` works on all node types (returns the raw attributes dict), while `.get_dict()` is specific to `aiida.orm.Dict`. The custom `data.pythonjob.builtins.dict.Dict` plugin stores its data in attributes, accessible via `.base.attributes.all`.
**Note:** FLEUR Seebeck values are already in μV/K (unlike CRYSTAL where `avg_s * 1e6` is applied). No unit conversion needed.

### 2. `output_parameters` reading in `_enrich_fleur_extras`
**Decision:** Add a new loop after the Seebeck loop in `_enrich_fleur_extras` that iterates over `fleur_uuids`, reads `calc.outputs.output_parameters.base.attributes.all`, and populates:
- `bandgap` (already in eV, no conversion)
- `total_energy` from `energy` (already in eV)
- `fermi_energy` from `fermi_energy * 27.2114` (Hartree → eV)
- `magnetic_moment` from `abs(spin_dependent_charge_total[0] - spin_dependent_charge_total[1])` (μB)
- `n_iterations` from `number_of_iterations_total` (int)
Progress logged every 25 items (same pattern as Seebeck and displacement loops).
**Why:** `output_parameters` is the standard FLEUR results port, available on ~99% of successful `fleur.fleur` calcs. It is the AiiDA equivalent of the `out.xml` parsing done by the local scan.

### 3. `fleur.inpgen` filtering
**Decision:** Skip `fleur.inpgen` CalcJobNodes in `scan_aiida_calculations` via a post-query check: `if 'inpgen' in (process_type or ''): continue`. The SQL-level `not_like` operator is not supported by AiiDA's QueryBuilder, so the filter is applied after the query, before any enrichment.
**Why:** `fleur.inpgen` (2204 nodes) produces no calculation results — it only generates input files. Including them adds 2204 null rows to the CSV. Filtering them out is cleaner. The post-query check is cheap (string match on already-loaded `process_type`).

### 4. New CSV columns
**Decision:** Add `total_energy`, `fermi_energy`, `magnetic_moment`, `n_iterations` to `_null_summary_keys` (initialized to `None` for all engines) and `_SUMMARY_CSV_COLUMNS` (inserted after `bandgap`).
**Why:** These fields are FLEUR-specific (from `output_parameters`) but the columns are engine-agnostic — CRYSTAL rows will have `None` (CRYSTAL does not populate these in the AiiDA-DB path; the local scan extracts `total_energy` from `OUTPUT`). The additive approach preserves backward compatibility.

### 5. Duplicate `_fetch_fleur_seebeck` in `reporting.py`
**Decision:** Fix the duplicate in `dft_organizer/reporting.py` (line 134–135) with the same `.base.attributes.all` fix, keeping the two copies in sync.
**Why:** Refactoring into a shared helper was considered but rejected to minimize the scope of this change — the two files have different import structures and the function is small (16 lines). A future refactor should extract it into a shared module.

## Risks / Trade-offs

- **[`pg8000` displacement remains slow]** → Pre-existing issue, not addressed here. The displacement loop can take minutes for hundreds of FLEUR calcs. Users can use `--calc-type transport` to skip most FLEUR rows, or `--engine crystal` to skip FLEUR entirely. A future change should migrate displacement to QueryBuilder-based provenance walk.
- **[`output_parameters` missing on some calcs]** → The `try/except Exception: pass` pattern means missing ports are silently skipped (fields stay `None`). This is consistent with the existing enrichment pattern for CRYSTAL.
- **[Seebeck values already in μV/K]** → No `*1e6` conversion is applied for FLEUR (unlike CRYSTAL at reporting.py:674). This is correct — verified on real data (AlAs=28.3, MgO=76.2 μV/K are realistic Seebeck values).
- **[`fermi_energy` unit conversion]** → `fermi_energy` in `output_parameters` is in Hartree; converted to eV via `*27.2114`. If the field is already in eV in some plugin versions, the conversion would be wrong — but verified on the current DB that it is in Hartree.
- **[Magnetic moment for non-magnetic calcs]** → `spin_dependent_charge_total` may have equal values for both spins (non-magnetic), giving `magnetic_moment=0.0`. This is correct behavior, not a bug.

## Migration Plan

1. Changes are additive — no schema or API migration needed.
2. The CSV gains 4 new columns; existing consumers that parse the CSV by column name are unaffected. Consumers parsing by column index need updating.
3. `fleur.inpgen` rows disappear from the CSV — any consumer relying on their presence should switch to `process_type` filtering.
4. Rollback: revert the `_fetch_fleur_seebeck` fix and remove the `output_parameters` loop; FLEUR rows return to null results (previous behavior).

## Open Questions

- Whether to extract `_fetch_fleur_seebeck` into a shared helper to avoid the duplicate in `reporting.py` and `aiida/reporting.py` — defer to a refactor change.
- Whether to populate `total_energy` / `fermi_energy` for CRYSTAL in the AiiDA-DB path (currently only local scan does) — separate change.
- Whether to add `n_kpoints` as a column — deferred; `n_iterations` is more useful for quality assessment.