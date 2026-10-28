"""Trusted example for the optional quantum-metal + SQDMetal environment.

Not fabricated, no ground continuity or junction boundary verification.
"""
def build_design():
    from qiskit_metal.designs import DesignPlanar
    from qiskit_metal.qlibrary.qubits.transmon_pocket import TransmonPocket

    design = DesignPlanar(enable_renderers=False)
    design.chips.main.size.size_x = '4mm'
    design.chips.main.size.size_y = '4mm'
    design.chips.main.size.size_z = '-500um'
    TransmonPocket(design, name='Q1', options=dict(pos_x='0mm',pos_y='0mm'))
    return design
