## 1. Fix Seebeck bug

- [x] 1.1 In `dft_organizer/aiida/reporting.py` `_fetch_fleur_seebeck` (line 43–44): replace `.get_dict()` with `.base.attributes.all` for both `output_seebeck` and `output_dos_local_wc_para`
- [x] 1.2 In `dft_organizer/reporting.py` duplicate `_fetch_fleur_seebeck` (line 134–135): apply the same fix
- [x] 1.3 Verify no `*1e6` conversion is applied (FLEUR Seebeck values are already in μV/K)
- [x] 1.4 Test on real FLEUR DOS calcs: AlAs → seebeck_coefficient_uvk=28.31, MgO → 76.23 (previously both None)

## 2. Read output_parameters for FLEUR

- [x] 2.1 In `_enrich_fleur_extras`, add a new loop after the Seebeck loop that reads `calc.outputs.output_parameters.base.attributes.all` for each FLEUR uuid
- [x] 2.2 Populate `bandgap` (eV, no conversion)
- [x] 2.3 Populate `total_energy` from `energy` (eV)
- [x] 2.4 Populate `fermi_energy` from `fermi_energy * 27.2114` (Hartree → eV)
- [x] 2.5 Populate `magnetic_moment` from `abs(spin_dependent_charge_total[0] - spin_dependent_charge_total[1])` (μB)
- [x] 2.6 Populate `n_iterations` from `number_of_iterations_total` (int)
- [x] 2.7 Add progress logging every 25 items (matching existing Seebeck/displacement pattern)
- [x] 2.8 Wrap in try/except to skip calcs without `output_parameters` (e.g. failed calcs)

## 3. Filter out fleur.inpgen

- [x] 3.1 In `scan_aiida_calculations`, add post-query check: `if 'inpgen' in (process_type or ''): continue` (SQL `not_like` not supported by AiiDA QueryBuilder)
- [x] 3.2 Verify inpgen calcs (2204 nodes) are excluded from the summary

## 4. Update CSV schema

- [x] 4.1 Add `total_energy`, `fermi_energy`, `magnetic_moment`, `n_iterations` to `_null_summary_keys`
- [x] 4.2 Add the same four fields to `_SUMMARY_CSV_COLUMNS` (inserted after `bandgap`)
- [x] 4.3 Verify polars `infer_schema_length` handles mixed None/float/int without errors

## 5. Documentation

- [x] 5.1 Update `README.md` "CSV Summary Fields" section with the new FLEUR-specific fields and their units

## 6. Testing & verification

- [x] 6.1 Run `ruff check` on changed files; confirm no new errors introduced (pre-existing E402/F841/F401 are unchanged)
- [x] 6.2 Test `_fetch_fleur_seebeck` on real FLEUR DOS calcs (AlAs, MgO) — Seebeck now populated (was None)
- [x] 6.3 Test `output_parameters` reading on real FLEUR calcs — bandgap, n_iterations populated
- [ ] 6.4 Run full `dft-report-aiida --engine fleur` and verify CSV contains populated bandgap/seebeck/total_energy columns (blocked by pre-existing pg8000 displacement performance issue — the displacement loop hangs; the enrichment itself works as verified by direct node-level tests)
- [ ] 6.5 Verify `fleur.inpgen` rows are absent from the CSV