## 1. pricing.py: provider detection + currency

- [ ] 1.1 Add `detect_provider(computer_name: str) -> str`:
  - [ ] 1.1.1 Lowercase `computer_name`; return `"vultr_usa"` if it contains any of `"vultr"`, `"vc2"`, `"vcpu"`; otherwise return `"hetzner"`
  - [ ] 1.1.2 Treat `None`/empty input as `"hetzner"` (historical default)
- [ ] 1.2 Add `get_currency(provider: str) -> str`:
  - [ ] 1.2.1 Return `"USD"` for `"vultr_usa"`, `"EUR"` otherwise (default EUR for hetzner/unknown)
- [ ] 1.3 Fix the `get_cloud_rate` docstring (currently says "EUR/hertzner or USD/vultr" — keep but clarify provider detection is the caller's job)

## 2. aiida/reporting.py: use detected provider + renamed fields

- [ ] 2.1 Import `detect_provider`, `get_currency` from `dft_organizer.pricing`
- [ ] 2.2 Replace lines 447-448:
  - [ ] 2.2.1 `provider = detect_provider(comp)`
  - [ ] 2.2.2 `summary["cloud_rate"] = get_cloud_rate(comp, provider=provider)`
  - [ ] 2.2.3 `summary["currency"] = get_currency(provider)`
  - [ ] 2.2.4 `cost = get_cost(duration, comp, provider=provider)`; `if cost is not None: summary["cost"] = cost`
- [ ] 2.3 In `_null_summary_keys` (line 342): replace `"hetzner_rate"` with `"cloud_rate", "currency"`; replace `"cost_eur"` with `"cost"`
- [ ] 2.4 In the column-order list (line 897): replace `"hetzner_rate"` with `"cloud_rate", "currency"`; replace `"cost_eur"` with `"cost"`

## 3. reporting.py (non-aiida): use detected provider + renamed field

- [ ] 3.1 Import `detect_provider` from `dft_organizer.pricing`
- [ ] 3.2 Replace line 120: `provider=detect_provider(calc.computer.label if calc.computer else "")`
- [ ] 3.3 Rename `summary["cost_eur"]` -> `summary["cost"]` (lines 86, 122)

## 4. CLI docstring

- [ ] 4.1 `dft_organizer/cli/report_aiida_cli.py`: update the docstring wording "cost" to mention multi-currency (EUR/USD) — no code change, just text

## 5. Tests

- [ ] 5.1 Create `tests/test_pricing.py` (or extend existing if present):
  - [ ] 5.1.1 `detect_provider("ccx13")` -> `"hetzner"`
  - [ ] 5.1.2 `detect_provider("vultr-ams-vc2-4c-8gb")` -> `"vultr_usa"`
  - [ ] 5.1.3 `detect_provider("vcpu-32gb")` -> `"vultr_usa"`
  - [ ] 5.1.4 `detect_provider("")` / `detect_provider(None)` -> `"hetzner"`
  - [ ] 5.1.5 `detect_provider("some-unknown-computer")` -> `"hetzner"`
  - [ ] 5.1.6 `get_currency("hetzner")` -> `"EUR"`
  - [ ] 5.1.7 `get_currency("vultr_usa")` -> `"USD"`
  - [ ] 5.1.8 `get_currency("unknown")` -> `"EUR"` (default)
  - [ ] 5.1.9 `get_cost(1.0, "vultr-ams-vc2-4c-8gb", provider="vultr_usa")` -> 0.06 (USD)
  - [ ] 5.1.10 `get_cost(1.0, "ccx13", provider="hetzner")` -> 0.03 (EUR)
- [ ] 5.2 Add `tests/test_reporting_provider.py` for the `--provider` override path:
  - [ ] 5.2.1 `scan_aiida_calculations(provider="vultr_usa", ...)` with a mocked computer name `yascheduler` produces `currency="USD"` and `cloud_rate` from `CLOUD_PRICING["vultr_usa"]`
  - [ ] 5.2.2 `scan_aiida_calculations(provider=None, ...)` falls back to `detect_provider("yascheduler")` -> `currency="EUR"`

## 7. CLI `--provider` override

- [ ] 7.1 Add `--provider` click option to `dft_organizer/cli/report_aiida_cli.py` (`click.Choice(["hetzner", "vultr_usa"], case_sensitive=False)`, default `None`)
- [ ] 7.2 Thread `provider` through `generate_aiida_reports` -> `scan_aiida_calculations`; in the cost block use `prov = provider or detect_provider(comp)`
- [ ] 7.3 Add the same `--provider` option to the non-AiiDA report CLI (`dft_organizer/cli/report_cli.py`); thread `provider` through `scan_calculations` -> `_enrich_aiida`

## 8. Verification

- [ ] 8.1 `ruff check dft_organizer/pricing.py dft_organizer/aiida/reporting.py dft_organizer/reporting.py dft_organizer/cli/report_aiida_cli.py dft_organizer/cli/report_cli.py tests/test_pricing.py tests/test_reporting_provider.py`
- [ ] 8.2 `ruff format` on the same files
- [ ] 8.3 `pytest tests/test_pricing.py tests/test_reporting_provider.py -v`
- [ ] 8.4 Run `dft-report-aiida --provider vultr_usa --label "Er5Si4: Geometry optimization [1]" --output-dir /tmp/vultr-check` and confirm `cloud_rate`, `cost`, `currency` columns appear with `USD` and Vultr rates
- [ ] 8.5 Run `dft-report-aiida --label "Er5Si4: Geometry optimization [1]" --output-dir /tmp/default-check` (no `--provider`) and confirm `currency="EUR"` (fallback to `detect_provider("yascheduler")`)