## 1. CRYSTAL phonon parser

- [x] 1.1 Investigate sample CRYSTAL `PHONON.DAT` / `FREQ.DAT` files in `data_old/` or `reports/` to confirm exact format and units (cm⁻¹ vs THz)
- [x] 1.2 Create `dft_organizer/crystal_parser/properties/phonon.py` with `parse_phonon_output(path: Path, engine: str = "crystal") -> dict | None`
- [x] 1.3 Parse summary fields: `has_phonons`, `phonon_freq_min`, `phonon_freq_max`, `phonon_n_imag`, `phonon_modes_count`
- [x] 1.4 Build `details` list of per-mode records: `q_point`, `branch_index`, `frequency_thz`, `is_imaginary`, `temperature_k`
- [x] 1.5 Normalize frequencies to THz (1 cm⁻¹ ≈ 0.02998 THz) and set `frequency_unit="THz"`
- [x] 1.6 Apply `IMAG_THRESHOLD_THZ = 1e-3` constant for imaginary-mode classification
- [x] 1.7 Handle `FREQ.DAT` as fallback when `PHONON.DAT` is absent
- [x] 1.8 Return `None` when neither file is present; never raise on missing/unsupported
- [x] 1.9 Added `parse_phonon_from_output(text)` to parse frequencies directly from CRYSTAL `OUTPUT` text (MODES block), used by the AiiDA-DB scan when `PHONON.DAT`/`FREQ.DAT` are not in the retrieved repository

## 2. FLEUR phonon parser

- [x] 2.1 Inspect `data_old/`/`reports/` for any FLEUR phonon output files (glob `phonon*`/`phono*`)
- [x] 2.2 Create `dft_organizer/fleur_parser/phonon.py` with `parse_phonon_output(path: Path, engine: str = "fleur") -> dict | None`
- [x] 2.3 If a recognized FLEUR phonon format exists, implement parsing reusing the CRYSTAL summary shape
- [x] 2.4 Otherwise implement graceful no-op returning `None` (with `has_phonons=False`); document as TODO

## 3. Package exports

- [x] 3.1 Export `parse_phonon_output` from `dft_organizer/crystal_parser/__init__.py`
- [x] 3.2 Export `parse_phonon_output` from `dft_organizer/fleur_parser/__init__.py`
- [x] 3.3 Export `parse_phonon_from_output` from `dft_organizer/crystal_parser/__init__.py`

## 4. Integrate into scan_calculations

- [x] 4.1 In `reporting.scan_calculations`, detect CRYSTAL phonon files (`PHONON.DAT` / `FREQ.DAT`) inside the existing `os.walk` loop
- [x] 4.2 Detect FLEUR phonon files (per `fleur_parser/phonon.py`) in the FLEUR branch
- [x] 4.3 Call `parse_phonon_output` and add compact fields (`has_phonons`, `phonon_freq_min`, `phonon_freq_max`, `phonon_n_imag`, `phonon_modes_count`) to the main `summary` dict
- [x] 4.4 Append detailed records to a new `phonon_store: list[dict]`
- [x] 4.5 Return 4-tuple `(summary_store, error_dict_crystal, error_dict_fleur, phonon_store)`
- [x] 4.6 Added fallback: parse phonon frequencies from `OUTPUT` text via `parse_phonon_from_output` when `PHONON.DAT`/`FREQ.DAT` are absent (common in AiiDA retrieved repos)
- [x] 4.7 Refined local `calc_type` detection: `properties`/`scf` rows are reclassified into `phonon`/`transport`/`elastic`/`electron` based on sibling files and OUTPUT keywords

## 5. Update callers of scan_calculations

- [x] 5.1 Update unpacking in `reporting.generate_reports_only`
- [x] 5.2 Update unpacking in `dft_organizer/aiida/reporting.py` (and any AiiDA CLI caller)
- [x] 5.3 Update `__main__` block in `reporting.py` and any other internal callers
- [x] 5.4 Ensure no other unpacking site is missed (grep `scan_calculations` usages)

## 6. Write phonon_summary CSV

- [x] 6.1 Add `phonon_store: list[dict]` parameter to `save_reports` (default `None`/`[]`)
- [x] 6.2 When `phonon_store` is non-empty, write `phonon_summary_<ts>.csv` via polars next to `summary_<ts>.csv`
- [x] 6.3 CSV columns: `uuid`, `engine`, `chemical_formula`, `output_path`, `q_point`, `branch_index`, `frequency_thz`, `is_imaginary`, `temperature_k`, `modes_count`
- [x] 6.4 When `phonon_store` empty, do not write the file (behavior unchanged)
- [x] 6.5 Pass `phonon_store` through `generate_reports_only` → `save_reports`

## 7. Backward compatibility & serialization

- [x] 7.1 Ensure `save_reports` flat-serialization handles new phonon fields (None → "") without breaking existing `_DROP_KEYS`/`nested_keys` logic
- [x] 7.2 Verify main `summary_<ts>.csv` columns are unchanged for trees without phonon files

## 8. Documentation

- [x] 8.1 Update `README.md` "CSV Summary Fields" section with the five new phonon fields
- [x] 8.2 Document the new `phonon_summary_<ts>.csv` file and its columns
- [x] 8.3 Note the `scan_calculations` signature change (now 4-tuple) in README Python API section

## 9. Testing & verification

- [ ] 9.1 Create a unit test for `parse_phonon_output` on a sample CRYSTAL `PHONON.DAT` (or synthetic fixture)
- [ ] 9.2 Test `parse_phonon_output` returns `None` for missing files
- [ ] 9.3 Test imaginary-mode counting and threshold behavior
- [ ] 9.4 Run `dft-report` on a tree with and without phonon files; verify both CSV outputs
- [x] 9.5 Run `ruff` / lint on changed files; run typecheck if configured

## 10. AiiDA-DB summary enrichment (additional work beyond original plan)

- [x] 10.1 Replace coarse `_determine_calc_type` in `aiida/reporting.py` with `determine_calc_type_summary` from `aiida/export.py` (phonon/transport/elastic/electron/optimise/scf/struct/hform)
- [x] 10.2 Add phonon fields (`has_phonons`, `phonon_freq_min`, `phonon_freq_max`, `phonon_n_imag`, `phonon_modes_count`) to `_null_summary_keys` and `_SUMMARY_CSV_COLUMNS`
- [x] 10.3 Implement `_enrich_crystal_extras`: parse phonon frequencies from retrieved `OUTPUT` for `calc_type=='phonon'`; parse `SEEBECK.DAT` for `calc_type=='transport'`; reclassify `scf`→`transport` when `SEEBECK.DAT` is present
- [x] 10.4 Add `--calc-type` CLI flag to `dft-report-aiida` and `dft-report` with pre-filter by label (skip expensive enrichment for non-matching rows)
- [x] 10.5 Add `--engine` CLI flag to `dft-report-aiida` to query only CRYSTAL or FLEUR (much faster crystal-only reports)
- [x] 10.6 Fix `skip_errors` to also drop unfinished calculations (`exit_status is None`, e.g. `EXCEPTED`)
- [x] 10.7 Drop silent-failed transport calcs (`exit_status=0` but `SEEBECK.DAT` header-only) from the summary
- [x] 10.8 Fix formula/space_group enrichment fallbacks: read `mpds_query` Dict, `crystal_calc_uuid` Str → SCF → StructureData, and workchain labels (`Co2As/189 Seebeck direct`) for calcs without a direct StructureData link
- [x] 10.9 Fix polars schema-inference error on mixed bool/None `has_phonons` column (`infer_schema_length`)
- [x] 10.10 Verify on real AiiDA data: 75 CRYSTAL calcs → 57 after dropping silent-failed transport; 0 null formulas; phonon frequencies and Seebeck populated