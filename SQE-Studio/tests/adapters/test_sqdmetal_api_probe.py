"""Native API compatibility tests use doubles ONLY for gate mechanics, not physics."""
from __future__ import annotations
import sys
from types import ModuleType
import pytest
from sqe_studio.adapters import sqdmetal_palace_adapter as em
from sqe_studio.adapters.base import EngineBlocked


def test_real_api_probe_rejects_missing_import(monkeypatch):
    import builtins
    original = builtins.__import__
    def blocked(name, *args, **kwargs):
        if name.startswith('SQDMetal'):
            raise ModuleNotFoundError('SQDMetal not available')
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, '__import__', blocked)
    with pytest.raises(ModuleNotFoundError, match='SQDMetal'):
        em.probe_sqdmetal_toolchain()


def test_api_probe_inspects_real_method_names_without_solver(monkeypatch):
    classes = [('PALACE_Capacitance_Simulation', 'Capacitance_Simulation'),
               ('PALACE_Eigenmode_Simulation', 'Eigenmode_Simulation'),
               ('PALACE_Driven_Simulation', 'Frequency_Driven_Simulation')]
    required = ('add_metallic', 'add_ground_plane', 'enforce_full_3D_simulation',
                'set_xBoundary_as_absolute', 'set_yBoundary_as_absolute',
                'set_zBoundary_as_absolute', 'fine_mesh_components', 'prepare_simulation',
                'create_port_JosephsonJunction', 'create_port_CPW_on_Launcher',
                'create_port_CPW_on_Route', 'set_farfield')
    for cls_name, mod_name in classes:
        module = ModuleType('SQDMetal.PALACE.'+mod_name)
        def init(self, name, sim_parent_directory, mode, meshing, user_options): pass
        cls = type(cls_name, (), {'__init__': init, **{name: lambda self: None for name in required}})
        setattr(module, cls_name, cls)
        monkeypatch.setitem(sys.modules, module.__name__, module)
    monkeypatch.setitem(sys.modules, 'SQDMetal', ModuleType('SQDMetal'))
    monkeypatch.setitem(sys.modules, 'SQDMetal.PALACE', ModuleType('SQDMetal.PALACE'))
    monkeypatch.setitem(sys.modules, 'gmsh', ModuleType('gmsh'))
    monkeypatch.setitem(sys.modules, 'qiskit_metal', ModuleType('qiskit_metal'))
    result = em.probe_sqdmetal_toolchain()
    assert result['state'] == 'NATIVE_API_IMPORTS_VERIFIED_NO_SIMULATION'
    assert result['kinds'] == ['capacitance', 'eigenmode', 'sparameters']
    # Missing native API must block; never substitute an SQE implementation.
    delattr(sys.modules['SQDMetal.PALACE.Eigenmode_Simulation'].PALACE_Eigenmode_Simulation,
            'create_port_CPW_on_Route')
    with pytest.raises(EngineBlocked, match='SQDMetal RF API missing'):
        em.probe_sqdmetal_toolchain()
