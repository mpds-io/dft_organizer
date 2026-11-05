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


def test_invalid_historical_result_is_explicit(monkeypatch):
    node = SimpleNamespace(uuid=next(iter(pu.INVALID_PHONON_RESULTS)))
    monkeypatch.setattr('aiida.orm.load_node', lambda pk: node)
    with pytest.raises(ValueError, match='Invalid phonon result'):
        pu.get_phonon_workchain_summary(1)
    pu.validate_phonon_result(node, np.zeros((1, 1, 3, 3)))


@pytest.mark.parametrize('defect', [None, 'uuid', 'path', 'hash', 'duplicate', 'missing'])
def test_audited_artifact_binding(tmp_path, defect):
    import hashlib
    import json

    summary = tmp_path / 'summary'
    summary.mkdir()
    fc = summary / 'fc.npz'
    np.savez(fc, force_constants=np.zeros((2, 2, 3, 3)))
    audit = summary / 'audit.json'
    node = SimpleNamespace(uuid='source-uuid')
    row = dict(source_phonon_uuid=node.uuid, force_order_corrected=True,
               reconstructed_force_constants_file='summary/fc.npz',
               reconstructed_force_constants_sha256=hashlib.sha256(fc.read_bytes()).hexdigest())
    if defect == 'uuid': row['source_phonon_uuid'] = 'other'
    if defect == 'path': row['reconstructed_force_constants_file'] = 'summary/other.npz'
    if defect == 'hash': row['reconstructed_force_constants_sha256'] = 'incorrect'
    audit.write_text(json.dumps([row, row] if defect == 'duplicate' else [row]))
    if defect == 'missing': audit.unlink()
    if defect:
        with pytest.raises((ValueError, FileNotFoundError)):
            pu.load_audited_force_constants(node, fc, audit)
    else:
        assert pu.load_audited_force_constants(node, fc, audit).shape == (2, 2, 3, 3)


def test_scanner_preserves_invalid_result_as_error_row(monkeypatch):
    from datetime import datetime
    from aiida import orm

    node = SimpleNamespace(uuid=next(iter(pu.INVALID_PHONON_RESULTS)))
    rows = iter([[], [[42, 'YAlO3', {'exit_status': 0}, datetime.now(), datetime.now()]], []])

    class Query:
        def __init__(self):
            self.rows = next(rows)
        def append(self, *args, **kwargs):
            return self
        def iterall(self):
            return iter(self.rows)

    monkeypatch.setattr(orm, 'QueryBuilder', Query)
    monkeypatch.setattr(orm, 'load_node', lambda pk: node)
    result = pu.scan_phonon_workchains(skip_errors=True)
    assert len(result) == 1
    assert 'Invalid phonon result' in result[0]['error']
    assert 'gamma_freqs_cm1' not in result[0]
