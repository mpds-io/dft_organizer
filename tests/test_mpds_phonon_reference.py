"""Tests for dft_organizer.phonon_utils.get_mpds_phonon_reference.

MPDS API is mocked via monkeypatched mpds_client.MPDSDataRetrieval; no
network access is required. The module-level _MPDS_CACHE is cleared in
setup to keep tests independent.
"""

from __future__ import annotations

import pytest

from dft_organizer import phonon_utils
from dft_organizer.phonon_utils import get_mpds_phonon_reference


def _entry(prop_name: str, unit: str, value) -> list:
    """Build a 7-element MPDS entry: [phase_id, formula, sgs, sample_id, prop, unit, value]."""
    return [1, "X", 1, 1, prop_name, unit, value]


class FakeRetrieval:
    """Replace mpds_client.MPDSDataRetrieval.get_data with canned results."""

    results: list = []

    def get_data(self, query):
        return list(self.results)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    phonon_utils._MPDS_CACHE.clear()
    monkeypatch.setenv("MPDS_KEY", "test-key")
    yield
    phonon_utils._MPDS_CACHE.clear()


@pytest.fixture
def mock_retrieval(monkeypatch):
    fake = FakeRetrieval()
    monkeypatch.setattr("mpds_client.MPDSDataRetrieval", lambda: fake)
    return fake


class TestLOTOAttribution:
    def test_lo_to_split(self, mock_retrieval):
        mock_retrieval.results = [
            _entry("wavenumber of longitudinal optical phonon", "mm-1", 50.0),
            _entry("wavenumber of transverse optical phonon", "mm-1", 30.0),
        ]
        ref = get_mpds_phonon_reference("CaTiO3", 62)
        assert ref["lo_cm1"] == [500.0]
        assert ref["to_cm1"] == [300.0]
        assert ref["unmarked_cm1"] == []
        assert ref["n_entries"] == 2

    def test_transverse_kept_when_present(self, mock_retrieval):
        """Real transverse entries must win over the unmarked fallback."""
        mock_retrieval.results = [
            _entry("wavenumber of transverse optical phonon", "cm-1", 110.0),
            _entry("wavenumber of optical phonon", "mm-1", 40.42),
        ]
        ref = get_mpds_phonon_reference("Al2O3", 167)
        assert ref["to_cm1"] == [110.0]
        assert ref["unmarked_cm1"] == [pytest.approx(404.2)]


class TestUnmarkedFallback:
    def test_unmarked_fills_empty_to(self, mock_retrieval):
        mock_retrieval.results = [
            _entry("wavenumber of optical phonon", "mm-1", 40.42),
            _entry("wavenumber of optical phonon", "mm-1", 87.94),
        ]
        ref = get_mpds_phonon_reference("Al2O3", 167)
        assert ref["to_cm1"] == [pytest.approx(404.2), pytest.approx(879.4)]
        assert ref["unmarked_cm1"] == [pytest.approx(404.2), pytest.approx(879.4)]
        assert ref["lo_cm1"] == []

    def test_unmarked_also_fills_to_when_lo_present(self, mock_retrieval):
        """Fallback is per-column: LO-only + unmarked entries -> to filled."""
        mock_retrieval.results = [
            _entry("wavenumber of longitudinal optical phonon", "mm-1", 21.99),
            _entry("wavenumber of optical phonon", "mm-1", 30.0),
        ]
        ref = get_mpds_phonon_reference("Fe2O3", 167)
        assert ref["lo_cm1"] == [pytest.approx(219.9)]
        assert ref["to_cm1"] == [300.0]


class TestUnitConversion:
    def test_mm1_x10(self, mock_retrieval):
        mock_retrieval.results = [_entry("wavenumber of optical phonon", "mm-1", 9.6)]
        assert get_mpds_phonon_reference("Cu2O", 224)["to_cm1"] == [96.0]

    def test_ev_conversion(self, mock_retrieval):
        mock_retrieval.results = [
            _entry("energy of optical phonon", "eV", 0.027),
            _entry("wavenumber of optical phonon", "mm-1", 9.6),
        ]
        ref = get_mpds_phonon_reference("Cu2O", 224)
        assert ref["to_cm1"] == [96.0, pytest.approx(217.77, abs=0.01)]

    def test_mev_conversion(self, mock_retrieval):
        mock_retrieval.results = [_entry("energy of optical phonon", "meV", 27.0)]
        assert get_mpds_phonon_reference("X", 1)["to_cm1"] == [
            pytest.approx(217.77, abs=0.01)
        ]

    def test_thz_conversion(self, mock_retrieval):
        mock_retrieval.results = [_entry("frequency of optical phonon", "THz", 6.0)]
        assert get_mpds_phonon_reference("X", 1)["to_cm1"] == [
            pytest.approx(200.14, abs=0.01)
        ]

    def test_cm1_passthrough(self, mock_retrieval):
        mock_retrieval.results = [_entry("wavenumber of optical phonon", "cm-1", 123.5)]
        assert get_mpds_phonon_reference("X", 1)["to_cm1"] == [123.5]

    def test_out_of_range_discarded(self, mock_retrieval):
        """MPDS sometimes leaks electronic transitions (e.g. 2558 mm^-1 = 25580 cm^-1)
        into phonon properties; such values must not reach the reference."""
        mock_retrieval.results = [
            _entry("wavenumber of optical phonon", "mm-1", 2558.0),
            _entry("wavenumber of optical phonon", "mm-1", 57.5),
            _entry("wavenumber of optical phonon", "cm-1", -50.0),
        ]
        ref = get_mpds_phonon_reference("Fe2O3", 167)
        assert ref["to_cm1"] == [575.0]
        assert ref["n_entries"] == 3


class TestDegradedPaths:
    def test_no_api_key(self, monkeypatch):
        monkeypatch.delenv("MPDS_KEY", raising=False)
        ref = get_mpds_phonon_reference("GaP", 216)
        assert ref["lo_cm1"] == [] and ref["to_cm1"] == []
        assert ref["n_entries"] == 0

    def test_query_failure(self, monkeypatch):
        def boom():
            raise RuntimeError("HTTP error code 204: No Results")

        monkeypatch.setattr("mpds_client.MPDSDataRetrieval", boom)
        ref = get_mpds_phonon_reference("LaAlO3", 221)
        assert ref["lo_cm1"] == [] and ref["to_cm1"] == []
        assert ref["n_entries"] == 0

    def test_nonnumeric_values_skipped(self, mock_retrieval):
        mock_retrieval.results = [
            _entry("wavenumber of optical phonon", "cm-1", None),
            _entry("wavenumber of optical phonon", "cm-1", "n/a"),
            _entry("wavenumber of optical phonon", "cm-1", 50.0),
        ]
        ref = get_mpds_phonon_reference("X", 1)
        assert ref["to_cm1"] == [50.0]
        assert ref["n_entries"] == 3

    def test_short_entries_skipped(self, mock_retrieval):
        mock_retrieval.results = [
            [1, "X", 1],
            _entry("wavenumber of optical phonon", "cm-1", 50.0),
        ]
        ref = get_mpds_phonon_reference("X", 1)
        assert ref["to_cm1"] == [50.0]
        assert ref["n_entries"] == 2
