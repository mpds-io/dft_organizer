# Design: phonon-reporting

## Architecture

Two parallel phonon pipelines merged into a single reporting system:

### CRYSTAL pipeline (from PR #18)

```
CalcJobNode (label contains "phonon")
  → determine_calc_type_summary() → calc_type="phonon"
  → _enrich_crystal_extras() → parse_phonon_from_output(OUTPUT)
  → columns: has_phonons, phonon_freq_min/max/mean/std, phonon_n_imag, phonon_modes_count
```

### FLEUR pipeline (new)

```
CalcJobNode (label contains "phonon")
  → determine_calc_type_summary() → calc_type="phonon"
  → _enrich_phonon_data() → walk provenance to PhonopyFleurWorkChain
    → extract_frequencies_from_workchain(pk) → phonopy mesh → freqs_cm1
    → integrate_frequencies(freqs_cm1, method, t_eval) → ZPE, F, S, Cv
  → columns: n_imaginary, zpe_kjmol, f_at_t_kjmol, s_at_t_jkmol, cv_at_t_jkmol, ...
```

### Standalone phonon report

```
QueryBuilder(WorkChainNode, process_type ~ "%phonopy.fleur%")
  → get_phonon_workchain_summary(pk) per node
  → save_aiida_phonon_reports() → CSV + JSON
```

## Key decisions

1. **PR18 as base for `reporting.py`**: PR18 already had CRYSTAL phonon enrichment, `determine_calc_type_summary`, `--calc-type`/`--max-duration`/`--skip-displacement`. Built our additions on top.

2. **`resolve_provider_and_rate` replaces `get_cloud_rate`/`get_cost`**: PR18 used simplified hetzner-only pricing. Replaced with our Vultr+Hetzner `resolve_provider_and_rate` from `feature/vultr-cost`.

3. **`_MockMesh` for phonopy ThermalProperties**: Allows calling phonopy's integration with raw frequency arrays without building a full `Phonopy`/`Mesh` object.

4. **Lazy imports**: `phonopy`, `ase.thermochemistry`, `ab_initio_calculations` imported inside functions so core reporting works without them.

5. **Pearson via spglib**: `_pearson_from_attrs()` uses `spglib.get_symmetry_dataset` → crystal system letter + centering char + natoms.