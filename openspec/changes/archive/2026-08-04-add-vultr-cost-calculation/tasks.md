## 1. pricing.py: provider detection + currency

- [x] 1.1 Add `detect_provider(computer_name: str) -> str`:
  - [x] 1.1.1 Lowercase `computer_name`; return `"vultr_usa"` if it contains any of `"vultr"`, `"vc2"`, `"vcpu"`, `"vbm"`; otherwise return `"hetzner"`
  - [x] 1.1.2 Treat `None`/empty input as `"hetzner"` (historical default)
- [x] 1.2 Add `get_currency(provider: str) -> str`:
  - [x] 1.2.1 Return `"USD"` for `"vultr_usa"`, `"EUR"` otherwise (default EUR for hetzner/unknown)
- [x] 1.3 Fix the `get_cloud_rate` docstring (clarify provider detection is the caller's job)
- [x] 1.4 Add bare-metal plans (vbm-*) to `CLOUD_PRICING["vultr_usa"]` from Vultr API
- [x] 1.5 Add `read_provider_and_machine_type_from_config()` to read `/etc/yascheduler/yascheduler.conf`
- [x] 1.6 Remove dead code (duplicate lines after return in `get_cloud_rate`)

## 2. aiida/reporting.py: use detected provider + renamed fields

- [x] 2.1 Import `detect_provider`, `get_currency`, `read_provider_and_machine_type_from_config` from `dft_organizer.pricing`
- [x] 2.2 Replace cost block: `prov = provider or detect_provider(comp)`, `rate_name = machine_type or comp`
- [x] 2.3 In `_null_summary_keys`: replace `"hetzner_rate"` with `"cloud_rate", "currency"`; replace `"cost_eur"` with `"cost"`
- [x] 2.4 In the column-order list: replace `"hetzner_rate"` with `"cloud_rate", "currency"`; replace `"cost_eur"` with `"cost"`
- [x] 2.5 Add `engine` filter parameter (QueryBuilder `process_type like %engine%`)
- [x] 2.6 Add `machine_type` and `skip_cost` parameters to `scan_aiida_calculations` and `generate_aiida_reports`

## 3. reporting.py (non-aiida): use detected provider + renamed field

- [x] 3.1 Import `detect_provider`, `read_provider_and_machine_type_from_config` from `dft_organizer.pricing`
- [x] 3.2 Replace cost block: `prov = provider or detect_provider(comp_name)`, `rate_name = machine_type or comp_name`
- [x] 3.3 Rename `summary["cost_eur"]` -> `summary["cost"]`
- [x] 3.4 Add `machine_type` and `skip_cost` parameters to `enrich_with_aiida_data`, `scan_calculations`, `generate_reports_only`

## 4. CLI

- [x] 4.1 `report_aiida_cli.py`: update docstring to mention multi-currency (EUR/USD)
- [x] 4.2 Add `--provider [hetzner|vultr_usa]` flag to both CLI
- [x] 4.3 Add `--engine [crystal|fleur]` flag to `report_aiida_cli.py`
- [x] 4.4 Add `--machine-type TEXT` flag to both CLI

## 5. Tests

- [x] 5.1 `tests/test_pricing.py`: detect_provider, get_currency, get_cost, get_cloud_rate, bare-metal rates, read_machine_type_from_config, read_provider_from_config (35 tests)
- [x] 5.2 `tests/test_reporting_provider.py`: provider override, engine filter, machine_type override, skip_cost (27 tests)

## 7. CLI `--provider` / `--engine` / `--machine-type` override

- [x] 7.1 Add `--provider` click option to both CLI
- [x] 7.2 Thread `provider` through `generate_aiida_reports` -> `scan_aiida_calculations`
- [x] 7.3 Add `--provider` option to non-AiiDA report CLI; thread through `scan_calculations` -> `enrich_with_aiida_data`
- [x] 7.4 Add `--engine` filter to `report_aiida_cli.py`
- [x] 7.5 Add `--machine-type` to both CLI with config fallback

## 8. skip_cost (no config available)

- [x] 8.1 When no provider/machine_type from CLI or config, set `skip_cost=True`
- [x] 8.2 `skip_cost=True` leaves cost/cloud_rate/currency as None
- [x] 8.3 CSV auto-drops all-None columns (existing logic in `save_aiida_reports`)

## 9. Verification

- [x] 9.1 `ruff check` — clean (1 pre-existing E402)
- [x] 9.2 `ruff format` — applied
- [x] 9.3 `pytest tests/test_pricing.py tests/test_reporting_provider.py -v` — 62 passed
- [x] 9.4 `dft-report-aiida --engine crystal --provider vultr_usa --machine-type vbm-24c-256gb-amd --from-date 2026-06-01` — 92 calcs, cloud_rate=0.993, USD, total=$996.34
- [x] 9.5 `dft-report-aiida --engine crystal --from-date 2026-06-01` (no flags) — reads config, same result (USD, 0.993)
- [x] 9.6 No config (mocked) — cost/cloud_rate/currency columns absent from CSV