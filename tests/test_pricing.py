"""Tests for dft_organizer.pricing: provider detection, currency, cost, rate lookup.

No dependency on ``/etc/yascheduler/yascheduler.conf`` — all config-reading
tests use ``tmp_path`` fixtures.
"""

from __future__ import annotations


from dft_organizer.pricing import (
    CLOUD_PRICING,
    detect_provider,
    get_cloud_rate,
    get_cost,
    get_currency,
    read_machine_type_from_config,
    read_provider_and_machine_type_from_config,
    read_provider_from_config,
    resolve_provider_and_rate,
)


# ---------------------------------------------------------------------------
# detect_provider
# ---------------------------------------------------------------------------


class TestDetectProvider:
    def test_hetzner_ccx_name(self):
        assert detect_provider("ccx13-something") == "hetzner"

    def test_hetzner_plain(self):
        assert detect_provider("hetzner-host-1") == "hetzner"

    def test_vultr_token_vultr(self):
        assert detect_provider("vultr-ams-vc2-4c-8gb") == "vultr_usa"

    def test_vultr_token_vc2(self):
        assert detect_provider("vc2-4c-8gb") == "vultr_usa"

    def test_vultr_token_vcpu(self):
        assert detect_provider("vcpu-32gb") == "vultr_usa"

    def test_vultr_token_vbm(self):
        assert detect_provider("vbm-24c-256gb-amd") == "vultr_usa"

    def test_vultr_token_vbm_prefix(self):
        assert detect_provider("some-host-vbm-8c-132gb-v2") == "vultr_usa"

    def test_unknown_defaults_to_hetzner(self):
        assert detect_provider("some-unknown-computer") == "hetzner"

    def test_empty_string_defaults_to_hetzner(self):
        assert detect_provider("") == "hetzner"

    def test_none_defaults_to_hetzner(self):
        assert detect_provider(None) == "hetzner"

    def test_case_insensitive(self):
        assert detect_provider("VULTR-AMS") == "vultr_usa"
        assert detect_provider("VCPU-32GB") == "vultr_usa"
        assert detect_provider("VBM-24C-256GB-AMD") == "vultr_usa"


# ---------------------------------------------------------------------------
# get_currency
# ---------------------------------------------------------------------------


class TestGetCurrency:
    def test_hetzner_eur(self):
        assert get_currency("hetzner") == "EUR"

    def test_vultr_usd(self):
        assert get_currency("vultr_usa") == "USD"

    def test_upcloud_none(self):
        """UpCloud has no pricing data — currency must be None, not a guess."""
        assert get_currency("upcloud") is None

    def test_unknown_none(self):
        assert get_currency("unknown") is None

    def test_empty_none(self):
        assert get_currency("") is None


# ---------------------------------------------------------------------------
# get_cloud_rate — substring matching, amd5 fix, unknown plans
# ---------------------------------------------------------------------------


class TestGetCloudRate:
    def test_hetzner_ccx13(self):
        assert (
            get_cloud_rate("ccx13", provider="hetzner")
            == CLOUD_PRICING["hetzner"]["ccx13"]
        )

    def test_vultr_vc2_4c_8gb(self):
        assert (
            get_cloud_rate("vultr-ams-vc2-4c-8gb", provider="vultr_usa")
            == CLOUD_PRICING["vultr_usa"]["vc2-4c-8gb"]
        )

    def test_vbm_24c_256gb_amd_exact(self):
        assert get_cloud_rate("vbm-24c-256gb-amd", provider="vultr_usa") == 0.993

    def test_vbm_24c_384gb_amd_exact(self):
        """amd variant must return its own price, not amd5's."""
        assert get_cloud_rate("vbm-24c-384gb-amd", provider="vultr_usa") == 1.13

    def test_vbm_24c_384gb_amd5_exact(self):
        """amd5 variant must return its own price (0.73), not amd's (1.13)."""
        assert get_cloud_rate("vbm-24c-384gb-amd5", provider="vultr_usa") == 0.73

    def test_vbm_24c_384gb_amd5_in_hostname(self):
        """Substring match: amd5 in a hostname must still return 0.73."""
        assert (
            get_cloud_rate("my-host-vbm-24c-384gb-amd5", provider="vultr_usa") == 0.73
        )

    def test_vbm_24c_384gb_amd_in_hostname(self):
        """Substring match: amd (without 5) in a hostname must return 1.13."""
        assert get_cloud_rate("my-host-vbm-24c-384gb-amd", provider="vultr_usa") == 1.13

    def test_unknown_provider_returns_none(self):
        """Unknown provider (upcloud) must return None, not 0.0."""
        assert get_cloud_rate("whatever", provider="upcloud") is None

    def test_unknown_provider_nonexistent_returns_none(self):
        assert get_cloud_rate("whatever", provider="nonexistent") is None

    def test_unknown_vultr_plan_returns_none(self):
        """Unknown Vultr plan must return None, not a default rate."""
        assert get_cloud_rate("vbm-99c-999gb", provider="vultr_usa") is None

    def test_unknown_hetzner_plan_returns_none(self):
        """Unknown Hetzner plan must return None, not a default rate."""
        assert get_cloud_rate("ccx99", provider="hetzner") is None

    def test_empty_computer_name_returns_none(self):
        assert get_cloud_rate("", provider="vultr_usa") is None


# ---------------------------------------------------------------------------
# get_cost
# ---------------------------------------------------------------------------


class TestGetCost:
    def test_hetzner_ccx13_one_hour(self):
        assert get_cost(1.0, "ccx13", provider="hetzner") == 0.03

    def test_vultr_vc2_4c_8gb_one_hour(self):
        assert get_cost(1.0, "vultr-ams-vc2-4c-8gb", provider="vultr_usa") == 0.06

    def test_vbm_24c_cost_10h(self):
        assert get_cost(10.0, "vbm-24c-256gb-amd", provider="vultr_usa") == 9.93

    def test_none_duration_returns_none(self):
        assert get_cost(None, "ccx13", provider="hetzner") is None

    def test_nan_duration_returns_none(self):
        assert get_cost(float("nan"), "ccx13", provider="hetzner") is None

    def test_unknown_plan_returns_none(self):
        """Cost for unknown plan must be None, not 0.0 (not 'free')."""
        assert get_cost(10.0, "vbm-99c-999gb", provider="vultr_usa") is None

    def test_upcloud_returns_none(self):
        """Cost for unsupported provider must be None."""
        assert get_cost(10.0, "whatever", provider="upcloud") is None


# ---------------------------------------------------------------------------
# resolve_provider_and_rate — the shared cost-resolution helper
# ---------------------------------------------------------------------------


class TestResolveProviderAndRate:
    """Tests for the single source of truth used by both reporting modules."""

    def test_explicit_provider_and_machine_type_consistent(self):
        prov, rate, currency = resolve_provider_and_rate(
            "yascheduler", provider="vultr_usa", machine_type="vbm-24c-256gb-amd"
        )
        assert prov == "vultr_usa"
        assert rate == 0.993
        assert currency == "USD"

    def test_explicit_provider_hetzner_machine_type_consistent(self):
        prov, rate, currency = resolve_provider_and_rate(
            "yascheduler", provider="hetzner", machine_type="ccx13"
        )
        assert prov == "hetzner"
        assert rate == 0.0256
        assert currency == "EUR"

    def test_vultr_provider_hetzner_machine_type_mismatch(self):
        """Vultr + ccx13 (Hetzner plan) — rate must be None (cross-provider mismatch)."""
        prov, rate, currency = resolve_provider_and_rate(
            "yascheduler", provider="vultr_usa", machine_type="ccx13"
        )
        assert prov == "vultr_usa"
        assert rate is None
        assert currency == "USD"

    def test_hetzner_provider_vultr_machine_type_mismatch(self):
        """Hetzner + vbm-24c-256gb-amd (Vultr plan) — rate must be None."""
        prov, rate, currency = resolve_provider_and_rate(
            "yascheduler", provider="hetzner", machine_type="vbm-24c-256gb-amd"
        )
        assert prov == "hetzner"
        assert rate is None
        assert currency == "EUR"

    def test_auto_detect_from_computer_name_vultr(self):
        """No provider/machine_type — auto-detect from computer name."""
        prov, rate, currency = resolve_provider_and_rate("vultr-ams-vc2-4c-8gb")
        assert prov == "vultr_usa"
        assert rate == 0.06
        assert currency == "USD"

    def test_auto_detect_from_computer_name_hetzner(self):
        prov, rate, currency = resolve_provider_and_rate("ccx13-something")
        assert prov == "hetzner"
        assert rate == 0.0256
        assert currency == "EUR"

    def test_auto_detect_unknown_computer_name(self):
        """Unknown computer name → hetzner default → but rate is None (no match)."""
        prov, rate, currency = resolve_provider_and_rate("some-unknown-host")
        assert prov == "hetzner"
        assert rate is None
        assert currency == "EUR"

    def test_machine_type_only_infers_provider(self):
        """Only machine_type given — provider inferred from it."""
        prov, rate, currency = resolve_provider_and_rate(
            "yascheduler", machine_type="vbm-24c-256gb-amd"
        )
        assert prov == "vultr_usa"
        assert rate == 0.993
        assert currency == "USD"

    def test_provider_only_uses_computer_name_for_rate(self):
        prov, rate, currency = resolve_provider_and_rate(
            "vultr-ams-vc2-4c-8gb", provider="vultr_usa"
        )
        assert prov == "vultr_usa"
        assert rate == 0.06
        assert currency == "USD"

    def test_upcloud_provider_returns_none_rate(self):
        """UpCloud has no pricing — rate and currency must be None."""
        prov, rate, currency = resolve_provider_and_rate("whatever", provider="upcloud")
        assert prov == "upcloud"
        assert rate is None
        assert currency is None

    def test_unknown_machine_type_under_known_provider(self):
        prov, rate, currency = resolve_provider_and_rate(
            "yascheduler", provider="vultr_usa", machine_type="vbm-99c-999gb"
        )
        assert prov == "vultr_usa"
        assert rate is None


# ---------------------------------------------------------------------------
# Config reading — all tests use tmp_path, never /etc/yascheduler/
# ---------------------------------------------------------------------------


def _write_config(tmp_path, content: str):
    """Helper: write a yascheduler-style config to tmp_path."""
    cfg = tmp_path / "yascheduler.conf"
    cfg.write_text(content)
    return str(cfg)


class TestReadMachineTypeFromConfig:
    def test_vultr_server_type(self, tmp_path):
        path = _write_config(
            tmp_path, "[clouds]\nvultr_server_type = vbm-24c-256gb-amd\n"
        )
        assert read_machine_type_from_config(path) == "vbm-24c-256gb-amd"

    def test_hetzner_server_type(self, tmp_path):
        path = _write_config(tmp_path, "[clouds]\nhetzner_server_type = ccx13\n")
        assert read_machine_type_from_config(path) == "ccx13"

    def test_vultr_takes_precedence_over_hetzner(self, tmp_path):
        path = _write_config(
            tmp_path,
            "[clouds]\nhetzner_server_type = ccx13\nvultr_server_type = vbm-24c-256gb-amd\n",
        )
        assert read_machine_type_from_config(path) == "vbm-24c-256gb-amd"

    def test_empty_value_skipped(self, tmp_path):
        path = _write_config(
            tmp_path, "[clouds]\nvultr_server_type =\nhetzner_server_type = ccx23\n"
        )
        assert read_machine_type_from_config(path) == "ccx23"

    def test_nonexistent_file_returns_none(self, tmp_path):
        assert read_machine_type_from_config(str(tmp_path / "nope.conf")) is None

    def test_empty_file_returns_none(self, tmp_path):
        path = _write_config(tmp_path, "")
        assert read_machine_type_from_config(path) is None

    def test_no_clouds_section_returns_none(self, tmp_path):
        path = _write_config(tmp_path, "[db]\nuser = test\n")
        assert read_machine_type_from_config(path) is None


class TestReadProviderFromConfig:
    def test_vultr_provider_detected(self, tmp_path):
        path = _write_config(
            tmp_path, "[clouds]\nvultr_server_type = vbm-24c-256gb-amd\n"
        )
        assert read_provider_from_config(path) == "vultr_usa"

    def test_hetzner_provider_detected(self, tmp_path):
        path = _write_config(tmp_path, "[clouds]\nhetzner_server_type = ccx13\n")
        assert read_provider_from_config(path) == "hetzner"

    def test_upcloud_provider_detected(self, tmp_path):
        """UpCloud is recognised but has no pricing — provider is returned."""
        path = _write_config(tmp_path, "[clouds]\nupcloud_server_type = 1xCPU-2GB\n")
        assert read_provider_from_config(path) == "upcloud"

    def test_nonexistent_file_returns_none(self, tmp_path):
        assert read_provider_from_config(str(tmp_path / "nope.conf")) is None

    def test_no_clouds_section_returns_none(self, tmp_path):
        path = _write_config(tmp_path, "[db]\nuser = test\n")
        assert read_provider_from_config(path) is None


class TestReadProviderAndMachineTypeFromConfig:
    def test_vultr_both(self, tmp_path):
        path = _write_config(
            tmp_path, "[clouds]\nvultr_server_type = vbm-24c-256gb-amd\n"
        )
        p, mt = read_provider_and_machine_type_from_config(path)
        assert p == "vultr_usa"
        assert mt == "vbm-24c-256gb-amd"

    def test_hetzner_both(self, tmp_path):
        path = _write_config(tmp_path, "[clouds]\nhetzner_server_type = ccx13\n")
        p, mt = read_provider_and_machine_type_from_config(path)
        assert p == "hetzner"
        assert mt == "ccx13"

    def test_vultr_takes_precedence_over_hetzner(self, tmp_path):
        path = _write_config(
            tmp_path,
            "[clouds]\nhetzner_server_type = ccx13\nvultr_server_type = vbm-24c-256gb-amd\n",
        )
        p, mt = read_provider_and_machine_type_from_config(path)
        assert p == "vultr_usa"
        assert mt == "vbm-24c-256gb-amd"

    def test_nonexistent_file_returns_none_none(self, tmp_path):
        assert read_provider_and_machine_type_from_config(
            str(tmp_path / "nope.conf")
        ) == (None, None)

    def test_no_clouds_section_returns_none_none(self, tmp_path):
        path = _write_config(tmp_path, "[db]\nuser = test\n")
        assert read_provider_and_machine_type_from_config(path) == (None, None)

    def test_empty_value_skipped_both_none(self, tmp_path):
        path = _write_config(tmp_path, "[clouds]\nvultr_server_type =\n")
        p, mt = read_provider_and_machine_type_from_config(path)
        assert p is None
        assert mt is None
