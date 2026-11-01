"""Reconstructed force constants must drive spectra without changing stored data."""

from types import SimpleNamespace

import numpy as np
import pytest
from ase import Atoms

from dft_organizer import phonon_utils as pu


@pytest.fixture
def force_constants(monkeypatch):
    positive = np.zeros((2, 2, 3, 3))
    positive[0, 0] = positive[1, 1] = np.eye(3)
    positive[0, 1] = positive[1, 0] = -np.eye(3)
    stored = -positive.copy()
    atoms = Atoms(
        "Si2",
        cell=np.eye(3) * 5.43,
        scaled_positions=[[0, 0, 0], [0.25, 0.25, 0.25]],
        pbc=True,
    )
    wc = SimpleNamespace(
        inputs=SimpleNamespace(
            structure=SimpleNamespace(get_ase=lambda: atoms),
            supercell_matrix=SimpleNamespace(
                get_list=lambda: np.eye(3, dtype=int).tolist()
            ),
        ),
        outputs=SimpleNamespace(
            output_phonopy=SimpleNamespace(
                output_force_constants=SimpleNamespace(get_array=lambda name: stored),
                output_parameters=SimpleNamespace(get_dict=lambda: {}),
            )
        ),
    )
    monkeypatch.setattr("aiida.orm.load_node", lambda pk: wc)
    return positive, stored


def test_reconstructed_constants_replace_spurious_imaginary_modes(force_constants):
    positive, stored = force_constants
    original = stored.copy()
    before = pu.extract_frequencies_from_workchain(1, mesh=[2, 2, 2])
    after = pu.extract_frequencies_from_workchain(
        1, mesh=[2, 2, 2], force_constants_override=positive
    )
    assert before["n_imaginary"] > 0
    assert after["n_imaginary"] == 0
    assert np.max(after["gamma_freqs_cm1"]) > 0
    np.testing.assert_array_equal(stored, original)


@pytest.mark.parametrize(
    "replacement", [np.zeros((1, 1, 3, 3)), np.full((2, 2, 3, 3), np.nan)]
)
def test_invalid_reconstructed_constants_are_rejected(force_constants, replacement):
    with pytest.raises(ValueError, match="finite and match"):
        pu.extract_frequencies_from_workchain(1, force_constants_override=replacement)
