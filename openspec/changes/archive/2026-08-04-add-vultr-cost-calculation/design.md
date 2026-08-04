## Context

`dft_organizer/pricing.py` already holds rate tables for both Hetzner and Vultr (`CLOUD_PRICING["hetzner"]`, `CLOUD_PRICING["vultr_usa"]`) and exposes generic `get_cloud_rate(computer_name, provider)` / `get_cost(duration_h, computer_name, provider)`. However:

- The calling code hardcodes `provider="hetzner"` in two places (`dft_organizer/aiida/reporting.py:447-448`, `dft_organizer/reporting.py:120`), so Vultr CalcJobs are never costed correctly.
- The summary fields are Hetzner-specific: `hetzner_rate` and `cost_eur` (reporting.py:342, 897). Hetzner bills in EUR, Vultr in USD — a single `cost_eur` field cannot represent a USD cost truthfully.
- There is no way to know which provider a CalcJob ran on from the summary alone.

The AiiDA `Computer.label` is the only signal available at reporting time. Hetzner computer names tend to contain `ccx`/`hetzner`; Vultr names tend to contain `vultr`/`vc2`/`vcpu` (see `scripts/check_vultr_balance.py` plan names and the `vultr_usa` rate keys).

## Goals / Non-Goals

**Goals:**
- Detect the cloud provider from the AiiDA computer name (case-insensitive substring match) with a sensible default.
- Report cost in the provider's native currency via a new `currency` field, and rename `cost_eur` -> `cost` so the field is currency-agnostic.
- Rename `hetzner_rate` -> `cloud_rate` so the field is provider-agnostic.
- Keep `pricing.py` backward compatible: existing `get_cloud_rate`/`get_cost` signatures unchanged.

**Non-Goals:**
- Real-time price fetching from provider APIs (prices are static in `CLOUD_PRICING`).
- Currency conversion (no EUR<->USD conversion; each CalcJob keeps its native currency).
- Touching the `scripts/check_vultr_balance.py` helper (separate concern, uses Vultr API directly).

## Decisions

### 1. Provider detection: substring match on computer name
**Decision:** `detect_provider(computer_name: str) -> str` returns `"vultr_usa"` when the lowercased computer name contains any of `vultr`, `vc2`, `vcpu`; otherwise returns `"hetzner"` (the historical default).
**Why:** Hetzner has been the only provider so far, so defaulting to Hetzner preserves current behaviour for existing computer names. The Vultr signals (`vultr`/`vc2`/`vcpu`) cover the plan names in `CLOUD_PRICING["vultr_usa"]` and the `fleur-test-node`-style labels. Alternative — a configurable map — rejected as over-engineering for two providers.

### 2. Currency: new `currency` field, rename `cost_eur` -> `cost`
**Decision:** Add a `currency` field (`"EUR"`/`"USD"`) to each summary dict, populated via `get_currency(provider)`. Rename `cost_eur` -> `cost` so the field name does not lie about its unit.
**Why:** A single `cost` + `currency` pair is cleaner than `cost_eur`/`cost_usd` duplication and scales to a third provider without another field. Breaking the `cost_eur` column name is acceptable since the only known consumer is the internal CSV report.

### 3. Rename `hetzner_rate` -> `cloud_rate`
**Decision:** Rename the per-CalcJob rate field from `hetzner_rate` to `cloud_rate` and add it to `_null_summary_keys` and the column-order list alongside `currency`.
**Why:** The field already holds a provider-specific rate; the name should not imply Hetzner. Same breaking-tradeoff as `cost_eur` -> `cost`.

### 4. `get_currency` as a small lookup, not a dict
**Decision:** `get_currency(provider: str) -> str` is a small function with an explicit `if provider == "vultr_usa": return "USD"; return "EUR"` body, raising nothing on unknown providers (defaults to EUR).
**Why:** Mirrors the `_DEFAULT_RATES` fallback philosophy in `pricing.py` (never raise, return a default). A dict would be equally simple but less discoverable in IDE goto.

### 5. Operator `--provider` CLI override
**Decision:** Add a `--provider {hetzner,vultr_usa}` CLI flag (default `None`) to both `dft-report-aiida` and `dft-report`. When set, it overrides `detect_provider(comp)` for all CalcJobs in the report. When `None`, the existing auto-detection via `detect_provider` is used (backward compatible).
**Why:** In the current AiiDA database all computers are named `yascheduler` (a logical AiiDA computer label), without any `vultr`/`vc2`/`vcpu`/`ccx` tokens. Auto-detection by computer name therefore always falls back to `hetzner`. Renaming AiiDA computers or changing `yascheduler`'s node-registration naming is a larger cross-repo change. The `--provider` flag is a pragmatic, low-risk override that lets operators produce a Vultr-costed report today, without waiting for naming changes. It is opt-in and does not change the default behaviour.

## Risks / Trade-offs

- **[Breaking CSV column names]** `hetzner_rate`/`cost_eur` -> `cloud_rate`/`cost` (+ new `currency`). Mitigation: the only known consumer is the internal report CSV; no external pipeline reads these names. Document in the PR.
- **[Provider misclassification]** A Hetzner computer whose name accidentally contains `vcpu` would be detected as Vultr. Mitigation: Hetzner plan names are `ccx*` (no `vcpu`/`vc2` tokens); the risk is low. If it happens, the `currency` field makes the misclassification visible.
- **[No currency conversion]** A mixed-provider report has rows in both EUR and USD with no FX rate. Mitigation: the `currency` column lets the consumer split or convert; out of scope here.
- **[--provider applies to all rows]** The override is global per report run, not per-row. A mixed-provider report requires two separate runs. Mitigation: acceptable for the current single-provider usage; per-row detection remains available when `--provider` is omitted.

## Migration Plan

1. Add `detect_provider` + `get_currency` to `pricing.py` (additive, no breakage).
2. Update the two call sites in `reporting.py` (aiida + non-aiida) to use `detect_provider`; rename fields.
3. Update `_null_summary_keys` and the column-order list in `aiida/reporting.py`.
4. Add `--provider` CLI flag to `dft-report-aiida` and `dft-report`; thread it through `generate_aiida_reports`/`scan_aiida_calculations` and `scan_calculations`/`_enrich_aiida`.
5. Add unit tests for `detect_provider`/`get_currency` and for the `--provider` override path.
6. Run `ruff check` + `ruff format` on touched files.
7. Verify via `dft-report-aiida --provider vultr_usa --label "..." --output-dir /tmp/vultr-check`: confirm `cloud_rate`, `cost`, `currency` columns appear with `USD` and Vultr rates.
8. Rollback: revert the branch; the old `hetzner_rate`/`cost_eur` columns return.