## MODIFIED Requirements

### Requirement: Per-CalcJob cloud cost calculation
The system SHALL compute a cloud cost for each AiiDA CalcJob by detecting the cloud provider from the computer name and applying that provider's hourly rate, instead of always assuming Hetzner.

The system SHALL provide `detect_provider(computer_name: str) -> str` that returns `"vultr_usa"` when the lowercased computer name contains any of `vultr`, `vc2`, `vcpu`, and `"hetzner"` otherwise (including for `None`/empty input).

The system SHALL provide `get_currency(provider: str) -> str` that returns `"USD"` for `"vultr_usa"` and `"EUR"` otherwise (default for hetzner/unknown).

Each CalcJob summary dict SHALL carry:
- `cloud_rate` (float): the hourly rate in the provider's currency
- `cost` (float or None): `duration * cloud_rate`, rounded to 2 decimals, or `None` when duration is `None`/NaN
- `currency` (str): `"EUR"` or `"USD"` depending on the detected provider

The fields `hetzner_rate` and `cost_eur` (previously present) SHALL be removed and replaced by `cloud_rate`, `cost`, and `currency`.

#### Scenario: Hetzner computer
- **WHEN** a CalcJob runs on a computer named `ccx13-something`
- **THEN** `detect_provider("ccx13-something")` returns `"hetzner"`, `get_currency` returns `"EUR"`, and the summary has `cloud_rate` from the Hetzner table, `currency="EUR"`, and `cost` in EUR

#### Scenario: Vultr computer
- **WHEN** a CalcJob runs on a computer named `vultr-ams-vc2-4c-8gb`
- **THEN** `detect_provider("vultr-ams-vc2-4c-8gb")` returns `"vultr_usa"`, `get_currency` returns `"USD"`, and the summary has `cloud_rate` from the Vultr table, `currency="USD"`, and `cost` in USD

#### Scenario: Unknown computer defaults to Hetzner
- **WHEN** a CalcJob runs on a computer named `some-unknown-host`
- **THEN** `detect_provider("some-unknown-host")` returns `"hetzner"` and `currency="EUR"` (backward-compatible default)

#### Scenario: Empty computer name
- **WHEN** `detect_provider("")` or `detect_provider(None)` is called
- **THEN** it returns `"hetzner"` without raising

#### Scenario: Vultr plan tokens
- **WHEN** `detect_provider("vcpu-32gb")` is called
- **THEN** it returns `"vultr_usa"` (the `vcpu` token matches)

### Requirement: Operator provider override via CLI
The system SHALL accept an optional `--provider {hetzner,vultr_usa}` CLI flag on `dft-report-aiida` and `dft-report` (default `None`). When set, the reported provider, currency, and rate SHALL be computed from the override for every CalcJob in the report, regardless of the AiiDA computer name. When `None`, the system SHALL fall back to `detect_provider(computer_name)`.

The override SHALL be threaded through `generate_aiida_reports` / `scan_aiida_calculations` (AiiDA path) and `scan_calculations` / `_enrich_aiida` (non-AiiDA path) as a `provider: str | None` parameter.

#### Scenario: Operator overrides to Vultr
- **WHEN** `dft-report-aiida --provider vultr_usa --label "Er5Si4: Geometry optimization [1]"` is run against CalcJobs on computer `yascheduler`
- **THEN** every summary dict has `currency="USD"`, `cloud_rate` from `CLOUD_PRICING["vultr_usa"]`, and `cost` in USD

#### Scenario: No override falls back to auto-detection
- **WHEN** `dft-report-aiida --label "Er5Si4: Geometry optimization [1]"` is run (no `--provider`) against CalcJobs on computer `yascheduler`
- **THEN** `detect_provider("yascheduler")` returns `"hetzner"`, and summaries have `currency="EUR"` (backward-compatible default)