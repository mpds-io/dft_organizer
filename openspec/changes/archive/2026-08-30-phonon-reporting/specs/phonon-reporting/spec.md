# phonon-reporting

## Overview

Detect phonon calculations in AiiDA (CRYSTAL CalcJobs + FLEUR PhonopyFleurWorkChains), extract/enrich phonon data, and compute thermodynamic properties.

## Behaviour

### CRYSTAL phonon (CalcJob-based)

- `determine_calc_type_summary(label)` classifies labels containing "phonon" as `calc_type="phonon"`.
- `_enrich_crystal_extras()` parses the retrieved `OUTPUT` file for MODES blocks via `parse_phonon_from_output()`.
- Columns filled: `has_phonons`, `phonon_freq_min`, `phonon_freq_max`, `phonon_freq_mean`, `phonon_freq_std`, `phonon_n_imag`, `phonon_modes_count`.

### FLEUR phonon (WorkChain-based)

- `_enrich_phonon_data()` walks provenance from phonon CalcJobs to parent `PhonopyFleurWorkChain`.
- `extract_frequencies_from_workchain(pk)` loads force constants from AiiDA outputs, runs phonopy mesh, returns frequencies in cm⁻¹.
- `integrate_frequencies(freqs_cm1, method, t_eval)` computes ZPE, F, S, Cv via `ab_initio_calculations.phonon_thermo`.
- Columns filled: `n_imaginary`, `zpe_kjmol`, `f_at_t_kjmol`, `s_at_t_jkmol`, `cv_at_t_jkmol`, `phonon_n_qpoints`, `phonon_n_bands`, `t_eval`.

### Standalone phonon report

- `dft-report-phonons` CLI queries `WorkChainNode` with `process_type ~ "%phonopy.fleur%"`.
- Output: CSV + JSON with pk, label, formula, SG, Pearson, cell params, exit_status, cost, n_imaginary, ZPE, F/S/Cv at t_eval.

### Pearson symbol

- `_pearson_from_attrs()` computes Pearson symbol (crystal system letter + centering + natoms) via spglib.
- Filled alongside `space_group` in `_apply_struct_attrs_to_summary()`.

### Integration methods

- `custom`: our `ThermalProperties` fork from `ab_initio_calculations`
- `phonopy`: phonopy's `ThermalProperties` via `_MockMesh`
- `ase`: ASE `HarmonicThermo` (no q-weights, equal-weight average)

## Constraints

- phonopy required for FLEUR frequency extraction (lazy import)
- `ab_initio_calculations` required for thermodynamic integration (lazy import)
- CRYSTAL phonon parsing works from retrieved `OUTPUT` file only (no PHONON.DAT/FREQ.DAT needed)
- FLEUR phonon enrichment only works for `PhonopyFleurWorkChain` nodes with `output_force_constants`