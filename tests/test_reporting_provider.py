"""Tests for the cost calculation and engine filter in AiiDA reporting.

These tests verify provider/machine_type override, auto-detection from
computer name, cross-provider mismatch handling, and engine filtering —
without needing a live AiiDA database (QueryBuilder is mocked).

No dependency on ``/etc/yascheduler/yascheduler.conf``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_rows(comp_label="yascheduler", n=1):
    """Return mock rows matching the QueryBuilder project order in scan_aiida_calculations."""
    ctime = datetime(2026, 7, 1, 0, 19, 17, tzinfo=timezone.utc)
    mtime = datetime(2026, 7, 1, 0, 29, 17, tzinfo=timezone.utc)
    rows = []
    for i in range(n):
        rows.append(
            [
                f"test-uuid-{i}",
                f"Er5Si4: Geometry optimization [{i}]",
                "aiida.calculations:crystal_dft.parallel",
                ctime,
                mtime,
                42 + i,
                {"exit_status": 0, "exit_message": ""},
                comp_label,
            ]
        )
    return rows


def _make_mixed_rows():
    """Return rows with one CRYSTAL and one FLEUR CalcJob."""
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


def _run_scan(rows, **kwargs):
    """Patch the AiiDA query and run scan_aiida_calculations.

    Returns ``(store, mock_qb)`` so tests can inspect QueryBuilder.append() calls.
    """
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

        store = scan_aiida_calculations(**kwargs)
    return store, mock_qb_inst


# ---------------------------------------------------------------------------
# Provider override
# ---------------------------------------------------------------------------


class TestProviderOverride:
    def test_provider_vultr_usa_overrides_yascheduler(self):
        """--provider vultr_usa → USD, even though computer name is 'yascheduler'."""
        rows = _make_mock_rows("yascheduler")
        store, _ = _run_scan(
            rows, provider="vultr_usa", machine_type="vbm-24c-256gb-amd"
        )
        assert len(store) == 1
        s = store[0]
        assert s["currency"] == "USD"
        assert s["cloud_rate"] == 0.993

    def test_provider_none_falls_back_to_auto_detect(self):
        """No provider → auto-detect from computer name → hetzner for 'yascheduler'."""
        rows = _make_mock_rows("yascheduler")
        store, _ = _run_scan(rows, provider=None)
        assert len(store) == 1
        s = store[0]
        # 'yascheduler' has no vultr tokens → hetzner → currency is EUR
        # but 'yascheduler' is not a known hetzner plan → rate is None → cost is None
        assert s["currency"] == "EUR"
        assert s["cloud_rate"] is None
        assert s["cost"] is None

    def test_provider_hetzner_overrides_vultr_named_computer(self):
        """--provider hetzner forces EUR even for a vultr-named computer."""
        rows = _make_mock_rows("vultr-ams-vc2-4c-8gb")
        store, _ = _run_scan(rows, provider="hetzner")
        assert len(store) == 1
        s = store[0]
        assert s["currency"] == "EUR"
        # vultr plan name under hetzner → no match → rate is None
        assert s["cloud_rate"] is None

    def test_auto_detect_vultr_from_computer_name_no_config(self):
        """No config, no flags — auto-detect from 'vultr-ams-vc2-4c-8gb' → Vultr/USD."""
        rows = _make_mock_rows("vultr-ams-vc2-4c-8gb")
        store, _ = _run_scan(rows, provider=None, machine_type=None)
        assert len(store) == 1
        s = store[0]
        assert s["currency"] == "USD"
        assert s["cloud_rate"] == 0.06
        assert s["cost"] is not None

    def test_auto_detect_hetzner_from_computer_name(self):
        """Auto-detect from 'ccx13-something' → hetzner, known plan → rate found."""
        rows = _make_mock_rows("ccx13-something")
        store, _ = _run_scan(rows, provider=None, machine_type=None)
        assert len(store) == 1
        s = store[0]
        assert s["currency"] == "EUR"
        assert s["cloud_rate"] == 0.0256


# ---------------------------------------------------------------------------
# Machine type override
# ---------------------------------------------------------------------------


class TestMachineTypeOverride:
    def test_machine_type_vbm_24c_overrides_yascheduler(self):
        rows = _make_mock_rows("yascheduler")
        store, _ = _run_scan(
            rows, provider="vultr_usa", machine_type="vbm-24c-256gb-amd"
        )
        assert len(store) == 1
        s = store[0]
        assert s["currency"] == "USD"
        assert s["cloud_rate"] == 0.993

    def test_machine_type_vbm_8c_overrides(self):
        rows = _make_mock_rows("yascheduler")
        store, _ = _run_scan(rows, provider="vultr_usa", machine_type="vbm-8c-132gb-v2")
        assert len(store) == 1
        s = store[0]
        assert s["cloud_rate"] == 0.479

    def test_machine_type_none_falls_back_to_computer_name(self):
        rows = _make_mock_rows("yascheduler")
        store, _ = _run_scan(rows, provider="vultr_usa", machine_type=None)
        assert len(store) == 1
        s = store[0]
        # 'yascheduler' is not a known vultr plan → rate is None
        assert s["cloud_rate"] is None

    def test_machine_type_ccx13_with_hetzner(self):
        rows = _make_mock_rows("yascheduler")
        store, _ = _run_scan(rows, provider="hetzner", machine_type="ccx13")
        assert len(store) == 1
        s = store[0]
        assert s["currency"] == "EUR"
        assert s["cloud_rate"] == 0.0256


# ---------------------------------------------------------------------------
# Cross-provider mismatch
# ---------------------------------------------------------------------------


class TestCrossProviderMismatch:
    """provider + machine_type from different clouds → rate must be None."""

    def test_vultr_provider_hetzner_machine_type(self):
        rows = _make_mock_rows("yascheduler")
        store, _ = _run_scan(rows, provider="vultr_usa", machine_type="ccx13")
        assert len(store) == 1
        s = store[0]
        assert s["currency"] == "USD"
        assert s["cloud_rate"] is None  # ccx13 not in vultr pricing
        assert s["cost"] is None

    def test_hetzner_provider_vultr_machine_type(self):
        rows = _make_mock_rows("yascheduler")
        store, _ = _run_scan(rows, provider="hetzner", machine_type="vbm-24c-256gb-amd")
        assert len(store) == 1
        s = store[0]
        assert s["currency"] == "EUR"
        assert s["cloud_rate"] is None  # vbm not in hetzner pricing
        assert s["cost"] is None


# ---------------------------------------------------------------------------
# Engine filter — verifies QueryBuilder.append() gets the process_type filter
# ---------------------------------------------------------------------------


class TestEngineFilter:
    """Test that scan_aiida_calculations passes the engine filter to QueryBuilder."""

    def test_engine_none_no_process_type_filter(self):
        """When engine=None, no process_type filter should be added."""
        rows = _make_mixed_rows()
        store, mock_qb = _run_scan(rows, engine=None)
        # Check that append() was called — inspect filters argument
        append_calls = mock_qb.append.call_args_list
        # Find the call with filters containing CalcJobNode
        filters_found = None
        for call in append_calls:
            f = call.kwargs.get("filters")
            if f and "process_type" in f:
                filters_found = f
                break
        assert filters_found is None, (
            "process_type filter should NOT be set when engine=None"
        )

    def test_engine_crystal_adds_process_type_filter(self):
        """When engine='crystal', QueryBuilder.append() must get process_type filter."""
        rows = _make_mixed_rows()
        store, mock_qb = _run_scan(rows, engine="crystal")
        append_calls = mock_qb.append.call_args_list
        filters_found = None
        for call in append_calls:
            f = call.kwargs.get("filters")
            if f and "process_type" in f:
                filters_found = f
                break
        assert filters_found is not None, (
            "process_type filter should be set when engine='crystal'"
        )
        assert "like" in filters_found["process_type"]
        assert "crystal" in filters_found["process_type"]["like"]

    def test_engine_fleur_adds_process_type_filter(self):
        """When engine='fleur', QueryBuilder.append() must get process_type filter."""
        rows = _make_mixed_rows()
        store, mock_qb = _run_scan(rows, engine="fleur")
        append_calls = mock_qb.append.call_args_list
        filters_found = None
        for call in append_calls:
            f = call.kwargs.get("filters")
            if f and "process_type" in f:
                filters_found = f
                break
        assert filters_found is not None, (
            "process_type filter should be set when engine='fleur'"
        )
        assert "like" in filters_found["process_type"]
        assert "fleur" in filters_found["process_type"]["like"]

    def test_engine_filter_value_in_like_clause(self):
        """The like clause must contain the engine name so removing the filter breaks the test."""
        rows = _make_mixed_rows()
        for engine in ("crystal", "fleur"):
            store, mock_qb = _run_scan(rows, engine=engine)
            append_calls = mock_qb.append.call_args_list
            for call in append_calls:
                f = call.kwargs.get("filters")
                if f and "process_type" in f:
                    like_val = f["process_type"]["like"]
                    assert engine in like_val, (
                        f"engine {engine!r} not in like clause {like_val!r}"
                    )
                    break


# ---------------------------------------------------------------------------
# No config available — auto-detect still works
# ---------------------------------------------------------------------------


class TestNoConfigAutoDetect:
    """When no config is available, cost is still attempted via computer name."""

    def test_vultr_computer_name_without_config(self):
        """Computer named 'vultr-ams-vc2-4c-8gb' → auto-detect Vultr, cost calculated."""
        rows = _make_mock_rows("vultr-ams-vc2-4c-8gb")
        store, _ = _run_scan(rows, provider=None, machine_type=None)
        assert len(store) == 1
        s = store[0]
        assert s["currency"] == "USD"
        assert s["cloud_rate"] == 0.06
        assert s["cost"] is not None

    def test_unknown_computer_name_without_config(self):
        """Computer named 'some-unknown-host' → hetzner, but no plan match → cost None."""
        rows = _make_mock_rows("some-unknown-host")
        store, _ = _run_scan(rows, provider=None, machine_type=None)
        assert len(store) == 1
        s = store[0]
        # Unknown computer → hetzner (default), currency=EUR, but no plan match → rate None
        assert s["currency"] == "EUR"
        assert s["cloud_rate"] is None
        assert s["cost"] is None
