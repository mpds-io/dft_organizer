## Why

`dft_organizer` computes cloud cost for each AiiDA CalcJob, but the calling code hardcodes `provider="hetzner"` (`dft_organizer/aiida/reporting.py:447-448`, `dft_organizer/reporting.py:120`). The Vultr rate table already exists in `dft_organizer/pricing.py` (`CLOUD_PRICING["vultr_usa"]`, `_DEFAULT_RATES["vultr_usa"]`), but it is never used because the provider is never detected from the computer name. As a result, all Vultr CalcJobs are costed at the Hetzner default rate (EUR), which is wrong both in currency (Vultr bills in USD) and in price.

Additionally, the summary fields are Hetzner-specific: `hetzner_rate` and `cost_eur` (reporting.py:342, 897). These names do not reflect a multi-provider setup and prevent a clean generalisation.

## What Changes

- Added `detect_provider(computer_name: str) -> str` in `dft_organizer/pricing.py` that classifies a computer name as `"hetzner"` or `"vultr_usa"` by substring matching (case-insensitive), defaulting to `"hetzner"` when no Vultr signal is found.
- Added `get_currency(provider: str) -> str` in `dft_organizer/pricing.py` returning `"EUR"` for `"hetzner"` and `"USD"` for `"vultr_usa"`.
- Replaced the hardcoded `provider="hetzner"` calls in `dft_organizer/aiida/reporting.py` and `dft_organizer/reporting.py` with `provider=detect_provider(comp)`.
- Generalised the summary fields: `hetzner_rate` -> `cloud_rate`, `cost_eur` -> `cost`, and added a new `currency` field (`"EUR"`/`"USD"`). Updated `_null_summary_keys` and the column-order list accordingly.
- Added unit tests for `detect_provider` and `get_currency` covering Hetzner names, Vultr names, and unknown names.
- **BREAKING**: the CSV/JSON field names `hetzner_rate` and `cost_eur` are renamed to `cloud_rate` and `cost` (plus a new `currency` column). Consumers reading these column names need to update.

## Capabilities

### Modified Capabilities
- `cloud-cost-calculation`: The system now detects the cloud provider from the AiiDA computer name and reports cost in the provider's native currency, instead of always assuming Hetzner/EUR.

## Impact

- **Code**:
  - `dft_organizer/pricing.py`: new `detect_provider`, `get_currency`; docstring fix in `get_cloud_rate`.
  - `dft_organizer/aiida/reporting.py`: use `detect_provider`; rename `hetzner_rate`->`cloud_rate`, `cost_eur`->`cost`, add `currency`; update `_null_summary_keys` and column-order list.
  - `dft_organizer/reporting.py`: use `detect_provider`; rename `cost_eur`->`cost`.
  - `dft_organizer/cli/report_aiida_cli.py`: docstring wording (cost is now multi-currency).
- **API**: `detect_provider(computer_name)` and `get_currency(provider)` are new public callables in `dft_organizer.pricing`.
- **Dependencies**: no new packages.
- **Systems**: the AiiDA database is read-only; no schema changes.