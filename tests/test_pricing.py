"""Tests for dft_organizer.pricing: provider detection, currency, cost."""

from dft_organizer.pricing import (
    CLOUD_PRICING,
    _DEFAULT_RATES,
    detect_provider,
    get_cloud_rate,
    get_cost,
    get_currency,
    read_machine_type_from_config,
    read_provider_and_machine_type_from_config,
    read_provider_from_config,
)


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


class TestGetCurrency:
    def test_hetzner_eur(self):
        assert get_currency("hetzner") == "EUR"

    def test_vultr_usd(self):
        assert get_currency("vultr_usa") == "USD"

    def test_unknown_defaults_eur(self):
        assert get_currency("unknown") == "EUR"

    def test_empty_defaults_eur(self):
        assert get_currency("") == "EUR"


class TestGetCost:
    def test_hetzner_ccx13_one_hour(self):
        # ccx13 rate is 0.0256 EUR/h
        assert get_cost(1.0, "ccx13", provider="hetzner") == 0.03

    def test_vultr_vc2_4c_8gb_one_hour(self):
        # vc2-4c-8gb rate is 0.060 USD/h
        assert get_cost(1.0, "vultr-ams-vc2-4c-8gb", provider="vultr_usa") == 0.06

    def test_none_duration_returns_none(self):
        assert get_cost(None, "ccx13", provider="hetzner") is None

    def test_nan_duration_returns_none(self):
        assert get_cost(float("nan"), "ccx13", provider="hetzner") is None


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

    def test_unknown_provider_returns_zero(self):
        assert get_cloud_rate("whatever", provider="nonexistent") == 0.0


class TestBareMetalRates:
    """Tests for Vultr bare-metal (vbm-*) plan rates."""

    def test_vbm_24c_256gb_amd_rate(self):
        assert get_cloud_rate("vbm-24c-256gb-amd", provider="vultr_usa") == 0.993

    def test_vbm_8c_132gb_v2_rate(self):
        assert get_cloud_rate("vbm-8c-132gb-v2", provider="vultr_usa") == 0.479

    def test_vbm_24c_cost_10h(self):
        assert get_cost(10.0, "vbm-24c-256gb-amd", provider="vultr_usa") == 9.93

    def test_vbm_8c_cost_1h(self):
        assert get_cost(1.0, "vbm-8c-132gb-v2", provider="vultr_usa") == 0.48

    def test_vbm_in_pricing_table(self):
        assert "vbm-24c-256gb-amd" in CLOUD_PRICING["vultr_usa"]

    def test_default_rate_vultr_is_baremetal(self):
        assert _DEFAULT_RATES["vultr_usa"] == 0.993

    def test_unknown_computer_uses_vultr_default(self):
        assert (
            get_cloud_rate("yascheduler", provider="vultr_usa")
            == _DEFAULT_RATES["vultr_usa"]
        )


class TestReadMachineTypeFromConfig:
    """Tests for read_machine_type_from_config()."""

    def test_reads_real_config(self):
        mt = read_machine_type_from_config()
        assert mt is not None
        assert isinstance(mt, str)
        assert mt == "vbm-24c-256gb-amd"

    def test_nonexistent_file_returns_none(self):
        assert read_machine_type_from_config("/nonexistent/path/file.conf") is None

    def test_empty_file_returns_none(self, tmp_path):
        cfg = tmp_path / "empty.conf"
        cfg.write_text("")
        assert read_machine_type_from_config(str(cfg)) is None

    def test_no_clouds_section_returns_none(self, tmp_path):
        cfg = tmp_path / "no_clouds.conf"
        cfg.write_text("[db]\nuser = test\n")
        assert read_machine_type_from_config(str(cfg)) is None

    def test_vultr_server_type(self, tmp_path):
        cfg = tmp_path / "test.conf"
        cfg.write_text("[clouds]\nvultr_server_type = vbm-24c-256gb-amd\n")
        assert read_machine_type_from_config(str(cfg)) == "vbm-24c-256gb-amd"

    def test_hetzner_server_type(self, tmp_path):
        cfg = tmp_path / "test.conf"
        cfg.write_text("[clouds]\nhetzner_server_type = ccx13\n")
        assert read_machine_type_from_config(str(cfg)) == "ccx13"

    def test_vultr_takes_precedence_over_hetzner(self, tmp_path):
        cfg = tmp_path / "test.conf"
        cfg.write_text(
            "[clouds]\nhetzner_server_type = ccx13\nvultr_server_type = vbm-24c-256gb-amd\n"
        )
        assert read_machine_type_from_config(str(cfg)) == "vbm-24c-256gb-amd"

    def test_empty_value_skipped(self, tmp_path):
        cfg = tmp_path / "test.conf"
        cfg.write_text("[clouds]\nvultr_server_type =\nhetzner_server_type = ccx23\n")
        assert read_machine_type_from_config(str(cfg)) == "ccx23"


class TestReadProviderFromConfig:
    """Tests for read_provider_from_config() and read_provider_and_machine_type_from_config()."""

    def test_reads_real_config_provider(self):
        p = read_provider_from_config()
        assert p == "vultr_usa"

    def test_reads_real_config_both(self):
        p, mt = read_provider_and_machine_type_from_config()
        assert p == "vultr_usa"
        assert mt == "vbm-24c-256gb-amd"

    def test_nonexistent_file_returns_none_none(self):
        assert read_provider_and_machine_type_from_config("/nonexistent/file") == (
            None,
            None,
        )

    def test_no_clouds_section_returns_none_none(self, tmp_path):
        cfg = tmp_path / "no_clouds.conf"
        cfg.write_text("[db]\nuser = test\n")
        assert read_provider_and_machine_type_from_config(str(cfg)) == (None, None)

    def test_vultr_provider_detected(self, tmp_path):
        cfg = tmp_path / "test.conf"
        cfg.write_text("[clouds]\nvultr_server_type = vbm-24c-256gb-amd\n")
        p, mt = read_provider_and_machine_type_from_config(str(cfg))
        assert p == "vultr_usa"
        assert mt == "vbm-24c-256gb-amd"

    def test_hetzner_provider_detected(self, tmp_path):
        cfg = tmp_path / "test.conf"
        cfg.write_text("[clouds]\nhetzner_server_type = ccx13\n")
        p, mt = read_provider_and_machine_type_from_config(str(cfg))
        assert p == "hetzner"
        assert mt == "ccx13"

    def test_vultr_takes_precedence_over_hetzner(self, tmp_path):
        cfg = tmp_path / "test.conf"
        cfg.write_text(
            "[clouds]\nhetzner_server_type = ccx13\nvultr_server_type = vbm-24c-256gb-amd\n"
        )
        p, mt = read_provider_and_machine_type_from_config(str(cfg))
        assert p == "vultr_usa"
        assert mt == "vbm-24c-256gb-amd"

    def test_empty_value_skipped_both_none(self, tmp_path):
        cfg = tmp_path / "test.conf"
        cfg.write_text("[clouds]\nvultr_server_type =\n")
        p, mt = read_provider_and_machine_type_from_config(str(cfg))
        assert p is None
        assert mt is None
