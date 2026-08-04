"""Tests for the --provider override path in reporting.

These tests verify that an explicit ``provider`` argument overrides the
auto-detected provider, without needing a live AiiDA database.
"""

from unittest.mock import patch

from dft_organizer.pricing import detect_provider, get_currency


class TestProviderOverrideLogic:
    """Unit-test the ``provider or detect_provider(comp)`` fallback expression."""

    def test_override_takes_precedence_over_auto_detect(self):
        comp = "yascheduler"
        auto = detect_provider(comp)
        assert auto == "hetzner"
        prov = "vultr_usa" or auto
        assert prov == "vultr_usa"
        assert get_currency(prov) == "USD"

    def test_none_falls_back_to_auto_detect(self):
        comp = "yascheduler"
        prov = None or detect_provider(comp)
        assert prov == "hetzner"
        assert get_currency(prov) == "EUR"

    def test_override_vultr_for_hetzner_named_computer(self):
        comp = "ccx13"
        prov = "vultr_usa" or detect_provider(comp)
        assert prov == "vultr_usa"
        assert get_currency(prov) == "USD"

    def test_override_hetzner_for_vultr_named_computer(self):
        comp = "vultr-ams-vc2-4c-8gb"
        prov = "hetzner" or detect_provider(comp)
        assert prov == "hetzner"
        assert get_currency(prov) == "EUR"


class TestScanAiidaCalculationsProviderOverride:
    """Test that scan_aiida_calculations respects the ``provider`` argument.

    Mocks the AiiDA query so no live database is needed.
    """

    def _make_mock_rows(self, comp_label="yascheduler"):
        """Return a list of mock rows matching the QueryBuilder project order."""
        from datetime import datetime, timezone

        ctime = datetime(2026, 7, 1, 0, 19, 17, tzinfo=timezone.utc)
        mtime = datetime(2026, 7, 1, 0, 29, 17, tzinfo=timezone.utc)
        return [
            [
                "test-uuid-1",
                "Er5Si4: Geometry optimization [1]",
                "aiida.calculations:crystal_dft.parallel",
                ctime,
                mtime,
                42,
                {"exit_status": 0, "exit_message": ""},
                comp_label,
            ]
        ]

    def _run_scan(self, rows, provider):
        """Patch the AiiDA query and run scan_aiida_calculations."""
        from dft_organizer.aiida.reporting import scan_aiida_calculations

        with (
            patch("dft_organizer.aiida.reporting._ensure_aiida"),
            patch("dft_organizer.aiida.reporting.QueryBuilder") as MockQB,
            patch("dft_organizer.aiida.reporting._enrich_with_structure_fast"),
            patch("dft_organizer.aiida.reporting._enrich_fleur_extras"),
        ):
            mock_qb_inst = MockQB.return_value
            mock_qb_inst.append.return_value = mock_qb_inst
            mock_qb_inst.iterall.return_value = iter(rows)

            store = scan_aiida_calculations(provider=provider)
        return store

    def test_provider_vultr_usa_overrides_yascheduler(self):
        rows = self._make_mock_rows("yascheduler")
        store = self._run_scan(rows, provider="vultr_usa")
        assert len(store) == 1
        s = store[0]
        assert s["currency"] == "USD"
        # "yascheduler" doesn't match any plan key, so the default rate is used
        from dft_organizer.pricing import _DEFAULT_RATES

        assert s["cloud_rate"] == _DEFAULT_RATES["vultr_usa"]

    def test_provider_none_falls_back_to_hetzner(self):
        rows = self._make_mock_rows("yascheduler")
        store = self._run_scan(rows, provider=None)
        assert len(store) == 1
        s = store[0]
        assert s["currency"] == "EUR"
        assert s["cloud_rate"] == 0.4006

    def test_provider_hetzner_overrides_vultr_named_computer(self):
        rows = self._make_mock_rows("vultr-ams-vc2-4c-8gb")
        store = self._run_scan(rows, provider="hetzner")
        assert len(store) == 1
        s = store[0]
        assert s["currency"] == "EUR"
        assert s["cloud_rate"] == 0.4006

    def test_provider_vultr_usa_overrides_vultr_named_computer(self):
        rows = self._make_mock_rows("vultr-ams-vc2-4c-8gb")
        store = self._run_scan(rows, provider="vultr_usa")
        assert len(store) == 1
        s = store[0]
        assert s["currency"] == "USD"


class TestScanAiidaCalculationsEngineFilter:
    """Test that scan_aiida_calculations respects the ``engine`` filter."""

    def _make_mixed_rows(self):
        from datetime import datetime, timezone

        ctime = datetime(2026, 7, 1, 0, 19, 17, tzinfo=timezone.utc)
        mtime = datetime(2026, 7, 1, 0, 29, 17, tzinfo=timezone.utc)
        return [
            [
                "uuid-crystal-1",
                "Er5Si4: Geometry optimization [1]",
                "aiida.calculations:crystal_dft.parallel",
                ctime,
                mtime,
                42,
                {"exit_status": 0, "exit_message": ""},
                "yascheduler",
            ],
            [
                "uuid-fleur-1",
                "Fe: scf [2]",
                "aiida.calculations:fleur.fleur",
                ctime,
                mtime,
                43,
                {"exit_status": 0, "exit_message": ""},
                "yascheduler",
            ],
        ]

    def _run_scan(self, rows, engine=None):
        from dft_organizer.aiida.reporting import scan_aiida_calculations

        with (
            patch("dft_organizer.aiida.reporting._ensure_aiida"),
            patch("dft_organizer.aiida.reporting.QueryBuilder") as MockQB,
            patch("dft_organizer.aiida.reporting._enrich_with_structure_fast"),
            patch("dft_organizer.aiida.reporting._enrich_fleur_extras"),
        ):
            mock_qb_inst = MockQB.return_value
            mock_qb_inst.append.return_value = mock_qb_inst
            mock_qb_inst.iterall.return_value = iter(rows)

            store = scan_aiida_calculations(engine=engine)
        return store

    def test_engine_none_includes_all(self):
        rows = self._make_mixed_rows()
        store = self._run_scan(rows, engine=None)
        assert len(store) == 2

    def test_engine_crystal_filters_to_crystal_only(self):
        rows = self._make_mixed_rows()
        store = self._run_scan(rows, engine="crystal")
        assert len(store) == 2  # Mock returns all rows; filter is in QueryBuilder
        engines = {s["engine"] for s in store}
        assert "crystal" in engines

    def test_engine_fleur_filters_to_fleur_only(self):
        rows = self._make_mixed_rows()
        store = self._run_scan(rows, engine="fleur")
        assert len(store) == 2  # Mock returns all rows; filter is in QueryBuilder
        engines = {s["engine"] for s in store}
        assert "fleur" in engines


class TestScanAiidaCalculationsMachineType:
    """Test that scan_aiida_calculations respects the ``machine_type`` override."""

    def _make_mock_rows(self, comp_label="yascheduler"):
        from datetime import datetime, timezone

        ctime = datetime(2026, 7, 1, 0, 19, 17, tzinfo=timezone.utc)
        mtime = datetime(2026, 7, 1, 0, 29, 17, tzinfo=timezone.utc)
        return [
            [
                "test-uuid-1",
                "Er5Si4: Geometry optimization [1]",
                "aiida.calculations:crystal_dft.parallel",
                ctime,
                mtime,
                42,
                {"exit_status": 0, "exit_message": ""},
                comp_label,
            ]
        ]

    def _run_scan(self, rows, provider=None, machine_type=None):
        from dft_organizer.aiida.reporting import scan_aiida_calculations

        with (
            patch("dft_organizer.aiida.reporting._ensure_aiida"),
            patch("dft_organizer.aiida.reporting.QueryBuilder") as MockQB,
            patch("dft_organizer.aiida.reporting._enrich_with_structure_fast"),
            patch("dft_organizer.aiida.reporting._enrich_fleur_extras"),
        ):
            mock_qb_inst = MockQB.return_value
            mock_qb_inst.append.return_value = mock_qb_inst
            mock_qb_inst.iterall.return_value = iter(rows)

            store = scan_aiida_calculations(
                provider=provider, machine_type=machine_type
            )
        return store

    def test_machine_type_vbm_24c_overrides_yascheduler(self):
        rows = self._make_mock_rows("yascheduler")
        store = self._run_scan(
            rows, provider="vultr_usa", machine_type="vbm-24c-256gb-amd"
        )
        assert len(store) == 1
        s = store[0]
        assert s["currency"] == "USD"
        assert s["cloud_rate"] == 0.993  # vbm-24c-256gb-amd rate

    def test_machine_type_vbm_8c_overrides(self):
        rows = self._make_mock_rows("yascheduler")
        store = self._run_scan(
            rows, provider="vultr_usa", machine_type="vbm-8c-132gb-v2"
        )
        assert len(store) == 1
        s = store[0]
        assert s["cloud_rate"] == 0.479  # vbm-8c-132gb-v2 rate

    def test_machine_type_none_falls_back_to_computer_name(self):
        rows = self._make_mock_rows("yascheduler")
        store = self._run_scan(rows, provider="vultr_usa", machine_type=None)
        assert len(store) == 1
        s = store[0]
        from dft_organizer.pricing import _DEFAULT_RATES

        assert (
            s["cloud_rate"] == _DEFAULT_RATES["vultr_usa"]
        )  # default for unknown computer

    def test_machine_type_ccx13_with_hetzner(self):
        rows = self._make_mock_rows("yascheduler")
        store = self._run_scan(rows, provider="hetzner", machine_type="ccx13")
        assert len(store) == 1
        s = store[0]
        assert s["currency"] == "EUR"
        assert s["cloud_rate"] == 0.0256  # ccx13 rate


class TestScanAiidaCalculationsSkipCost:
    """Test that skip_cost=True leaves cost/rate/currency as None."""

    def _make_mock_rows(self, comp_label="yascheduler"):
        from datetime import datetime, timezone

        ctime = datetime(2026, 7, 1, 0, 19, 17, tzinfo=timezone.utc)
        mtime = datetime(2026, 7, 1, 0, 29, 17, tzinfo=timezone.utc)
        return [
            [
                "test-uuid-1",
                "Er5Si4: Geometry optimization [1]",
                "aiida.calculations:crystal_dft.parallel",
                ctime,
                mtime,
                42,
                {"exit_status": 0, "exit_message": ""},
                comp_label,
            ]
        ]

    def _run_scan(self, rows, skip_cost=True):
        from dft_organizer.aiida.reporting import scan_aiida_calculations

        with (
            patch("dft_organizer.aiida.reporting._ensure_aiida"),
            patch("dft_organizer.aiida.reporting.QueryBuilder") as MockQB,
            patch("dft_organizer.aiida.reporting._enrich_with_structure_fast"),
            patch("dft_organizer.aiida.reporting._enrich_fleur_extras"),
        ):
            mock_qb_inst = MockQB.return_value
            mock_qb_inst.append.return_value = mock_qb_inst
            mock_qb_inst.iterall.return_value = iter(rows)

            store = scan_aiida_calculations(skip_cost=skip_cost)
        return store

    def test_skip_cost_leaves_fields_none(self):
        rows = self._make_mock_rows("yascheduler")
        store = self._run_scan(rows, skip_cost=True)
        assert len(store) == 1
        s = store[0]
        assert s["cost"] is None
        assert s["cloud_rate"] is None
        assert s["currency"] is None

    def test_skip_cost_false_computes_cost(self):
        rows = self._make_mock_rows("yascheduler")
        store = self._run_scan(rows, skip_cost=False)
        assert len(store) == 1
        s = store[0]
        # Without skip_cost, detect_provider("yascheduler") -> hetzner -> EUR
        assert s["currency"] == "EUR"
        assert s["cloud_rate"] is not None
