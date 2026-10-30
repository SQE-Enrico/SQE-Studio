"""Scientific matrix-element-preserving storage compatibility (not native solves)."""
import numpy as np
from scipy import sparse
from sqe_studio.adapters.scqubits_adapter import _qobj_compatible_operator


class PhysicalOperator:
    def charge(self):
        return sparse.csc_array(np.array([[0, 1j], [-1j, 0]], dtype=complex))

    def existing_matrix(self):
        return sparse.csr_matrix([[1., 0.], [0., 2.]])


def test_sparse_array_preserves_all_operator_elements_and_owner():
    owner = PhysicalOperator()
    wrapped = _qobj_compatible_operator(owner.charge)
    assert wrapped.__self__ is owner
    actual = wrapped()
    assert isinstance(actual, sparse.csc_matrix)
    np.testing.assert_array_equal(actual.toarray(), owner.charge().toarray())


def test_existing_sparse_matrix_is_unchanged():
    owner = PhysicalOperator()
    wrapped = _qobj_compatible_operator(owner.existing_matrix)
    assert wrapped.__self__ is owner
    result = wrapped()
    assert isinstance(result, sparse.csr_matrix)
    np.testing.assert_array_equal(result.toarray(), owner.existing_matrix().toarray())


def test_internal_scqubits_sparse_boundary_preserves_matrix_and_restores():
    """Tests the representation bridge, not a synthetic native eigenproblem."""
    from types import SimpleNamespace
    from sqe_studio.adapters.scqubits_adapter import _scqubits_sparse_matrix_boundary
    seen = []
    def upstream(operator, subsystem, op_in_eigenbasis, evecs):
        assert isinstance(operator, (sparse.csc_matrix, sparse.csr_matrix, np.ndarray))
        seen.append((operator, subsystem, op_in_eigenbasis, evecs))
        return operator
    mod = SimpleNamespace(convert_operator_to_qobj=upstream, qt=SimpleNamespace(Qobj=type('NeverQobj', (), {})))
    physical = sparse.csc_array([[3.0, 1j], [-1j, -2.0]], dtype=complex)
    with _scqubits_sparse_matrix_boundary(mod):
        out = mod.convert_operator_to_qobj(physical, 'native-subsystem', True, None)
        assert isinstance(out, sparse.csc_matrix)
        np.testing.assert_array_equal(out.toarray(), physical.toarray())
        assert out.dtype == physical.dtype and out.shape == physical.shape
        assert mod.convert_operator_to_qobj is not upstream
    assert mod.convert_operator_to_qobj is upstream
    assert seen[0][1:] == ('native-subsystem', True, None)


def test_internal_scqubits_boundary_restores_after_native_error():
    from types import SimpleNamespace
    import pytest
    from sqe_studio.adapters.scqubits_adapter import _scqubits_sparse_matrix_boundary
    def fails(*args):
        raise RuntimeError('native solver failure should propagate')
    mod = SimpleNamespace(convert_operator_to_qobj=fails, qt=SimpleNamespace(Qobj=type('NeverQobj', (), {})))
    with pytest.raises(RuntimeError, match='native solver failure'):
        with _scqubits_sparse_matrix_boundary(mod):
            mod.convert_operator_to_qobj(sparse.csc_array([[1.]]), None, True, None)
    assert mod.convert_operator_to_qobj is fails


def test_internal_scqubits_qobj_conversion_does_not_reintroduce_csc_array():
    """Regression for Windows native composite: Qobj -> csc_array in 4.3.1."""
    from types import SimpleNamespace
    from sqe_studio.adapters.scqubits_adapter import _scqubits_sparse_matrix_boundary

    class NativeQobj:
        pass

    physical = sparse.csc_array(np.array([[3., 1j], [-1j, 5.]], dtype=complex))
    seen = []
    def scqubits_converter(value, subsystem, in_eigenbasis, evecs):
        # Same category check as scqubits 4.3.1, BEFORE its matrix conversion.
        assert isinstance(value, sparse.csc_matrix)
        seen.append(value)
        return value
    mod = SimpleNamespace(qt=SimpleNamespace(Qobj=NativeQobj),
        Qobj_to_scipy_csc_matrix=lambda value: physical,
        convert_operator_to_qobj=scqubits_converter)
    with _scqubits_sparse_matrix_boundary(mod):
        result = mod.convert_operator_to_qobj(NativeQobj(), object(), True, None)
    np.testing.assert_array_equal(result.toarray(), physical.toarray())
    assert result.dtype == physical.dtype and result.shape == physical.shape
    assert len(seen) == 1
    assert mod.convert_operator_to_qobj is scqubits_converter


def test_sparse_conversion_does_not_change_spectra_for_hermitian_operator():
    """Matrix/array representation has identical eigenvalues (not native solve)."""
    from types import SimpleNamespace
    from sqe_studio.adapters.scqubits_adapter import _scqubits_sparse_matrix_boundary
    physical = sparse.csc_array(np.array([[2., .125j], [-.125j, 4.]], dtype=complex))
    def native_converter(operator, *_):
        assert isinstance(operator, sparse.csc_matrix)
        return operator
    mod = SimpleNamespace(qt=SimpleNamespace(Qobj=type('NeverQobj', (), {})),
                          convert_operator_to_qobj=native_converter)
    with _scqubits_sparse_matrix_boundary(mod):
        result = mod.convert_operator_to_qobj(physical, None, True, None)
    np.testing.assert_allclose(np.linalg.eigvalsh(result.toarray()),
                               np.linalg.eigvalsh(physical.toarray()), atol=0, rtol=0)
