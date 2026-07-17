## 1. CRYSTAL phonon parser

- [x] 1.1 Investigate sample CRYSTAL `PHONON.DAT` / `FREQ.DAT` files in `data_old/` or `reports/` to confirm exact format and units (cm⁻¹ vs THz)
- [x] 1.2 Create `dft_organizer/crystal_parser/properties/phonon.py` with `parse_phonon_output(path: Path, engine: str = "crystal") -> dict | None`
- [x] 1.3 Parse summary fields: `has_phonons`, `phonon_freq_min`, `phonon_freq_max`, `phonon_n_imag`, `phonon_modes_count`
- [x] 1.4 Build `details` list of per-mode records: `q_point`, `branch_index`, `frequency_thz`, `is_imaginary`, `temperature_k`
- [x] 1.5 Normalize frequencies to THz (1 cm⁻¹ ≈ 0.02998 THz) and set `frequency_unit="THz"`
- [x] 1.6 Apply `IMAG_THRESHOLD_THZ = 1e-3` constant for imaginary-mode classification
- [x] 1.7 Handle `FREQ.DAT` as fallback when `PHONON.DAT` is absent
- [x] 1.8 Return `None` when neither file is present; never raise on missing/unsupported

## 2. FLEUR phonon parser

- [x] 2.1 Inspect `data_old/`/`reports/` for any FLEUR phonon output files (glob `phonon*`/`phono*`)
- [x] 2.2 Create `dft_organizer/fleur_parser/phonon.py` with `parse_phonon_output(path: Path, engine: str = "fleur") -> dict | None`
- [x] 2.3 If a recognized FLEUR phonon format exists, implement parsing reusing the CRYSTAL summary shape
- [x] 2.4 Otherwise implement graceful no-op returning `None` (with `has_phonons=False`); document as TODO

## 3. Package exports

- [x] 3.1 Export `parse_phonon_output` from `dft_organizer/crystal_parser/__init__.py`
- [x] 3.2 Export `parse_phonon_output` from `dft_organizer/fleur_parser/__init__.py`

## 4. Integrate into scan_calculations

- [ ] 4.1 In `reporting.scan_calculations`, detect CRYSTAL phonon files (`PHONON.DAT` / `FREQ.DAT`) inside the existing `os.walk` loop
- [ ] 4.2 Detect FLEUR phonon files (per `fleur_parser/phonon.py`) in the FLEUR branch
- [ ] 4.3 Call `parse_phonon_output` and add compact fields (`has_phonons`, `phonon_freq_min`, `phonon_freq_max`, `phonon_n_imag`, `phonon_modes_count`) to the main `summary` dict
- [ ] 4.4 Append detailed records to a new `phonon_store: list[dict]`
- [ ] 4.5 Return 4-tuple `(summary_store, error_dict_crystal, error_dict_fleur, phonon_store)`

## 5. Update callers of scan_calculations

- [ ] 5.1 Update unpacking in `reporting.generate_reports_only`
- [ ] 5.2 Update unpacking in `dft_organizer/aiida/reporting.py` (and any AiiDA CLI caller)
- [ ] 5.3 Update `__main__` block in `reporting.py` and any other internal callers
- [ ] 5.4 Ensure no other unpacking site is missed (grep `scan_calculations` usages)

## 6. Write phonon_summary CSV

- [ ] 6.1 Add `phonon_store: list[dict]` parameter to `save_reports` (default `None`/`[]`)
- [ ] 6.2 When `phonon_store` is non-empty, write `phonon_summary_<ts>.csv` via polars next to `summary_<ts>.csv`
- [ ] 6.3 CSV columns: `uuid`, `engine`, `chemical_formula`, `output_path`, `q_point`, `branch_index`, `frequency_thz`, `is_imaginary`, `temperature_k`, `modes_count`
- [ ] 6.4 When `phonon_store` empty, do not write the file (behavior unchanged)
- [ ] 6.5 Pass `phonon_store` through `generate_reports_only` → `save_reports`

## 7. Backward compatibility & serialization

- [ ] 7.1 Ensure `save_reports` flat-serialization handles new phonon fields (None → "") without breaking existing `_DROP_KEYS`/`nested_keys` logic
- [ ] 7.2 Verify main `summary_<ts>.csv` columns are unchanged for trees without phonon files

## 8. Documentation

- [ ] 8.1 Update `README.md` "CSV Summary Fields" section with the five new phonon fields
- [ ] 8.2 Document the new `phonon_summary_<ts>.csv` file and its columns
- [ ] 8.3 Note the `scan_calculations` signature change (now 4-tuple) in README Python API section

## 9. Testing & verification

- [ ] 9.1 Create a unit test for `parse_phonon_output` on a sample CRYSTAL `PHONON.DAT` (or synthetic fixture)
- [ ] 9.2 Test `parse_phonon_output` returns `None` for missing files
- [ ] 9.3 Test imaginary-mode counting and threshold behavior
- [ ] 9.4 Run `dft-report` on a tree with and without phonon files; verify both CSV outputs
- [ ] 9.5 Run `ruff` / lint on changed files; run typecheck if configured