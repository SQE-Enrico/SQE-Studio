"""Interoperable positive-metal QGeometry exchange for Quantum Metal.

Transport is independent of qiskit_metal. Optional sidecar converts the manifest
into a real QDesign using public QComponent APIs without introducing Qt/Ansys.
"""
from __future__ import annotations

from .geometry import NETS, build
from .io import digest


def manifest(cfg):
    geom = build(cfg)
    chip = geom['chip']
    result = {
        'schema_version': 1,
        'format': 'sqe-quantum-metal-positive-mask-v1',
        'geometry_sha256': geom['geometry_sha256'],
        'coordinates': 'millimeters',
        'gds_layer': 1,
        'chip': {'width_mm': (chip['x1']-chip['x0'])/1000,
                 'height_mm': (chip['y1']-chip['y0'])/1000},
        'components': [
            {'name': name, 'attribute': NETS[name], 'layer': 1,
             'subtract': False, 'rectangles_mm': [[r[k]/1000 for k in ('x0','y0','x1','y1')]
                                                      for r in geom['metal'][name]]}
            for name in NETS],
        'ports': [{'name': name, 'rectangle_mm': [r[k]/1000 for k in ('x0','y0','x1','y1')]}
                  for name,r in geom['ports'].items()],
        'notes': ['Positive metal only; junction and port patches are separately annotated',
                  'SQE Gmsh and GDS remain authoritative; this is an import bridge',
                  'Quantum Metal components created from exact positive-metal rectangles, not a redraw',
                  'No automatic QMetal pin/route reconstruction, process mask qualification or EPR'],
    }
    result['manifest_sha256'] = digest(result)
    return result


def to_qdesign(data):
    """Optional Quantum Metal sidecar: source geometry -> named QComponents/QGeometry.

    Intended for quantum-metal >=0.8 headless installations. Raise if unavailable.
    """
    from qiskit_metal.designs import DesignPlanar
    from qiskit_metal.qlibrary.core import QComponent
    from shapely.geometry import box
    if data.get('format') not in ('sqe-quantum-metal-positive-mask-v1','sqe-positive-mask-orthogonal'):
        raise ValueError('Unsupported SQE/Quantum Metal manifest format')
    verification = dict(data); provided=verification.pop('manifest_sha256',None)
    if digest(verification) != provided:
        raise ValueError('Quantum Metal manifest checksum mismatch')
    # Explicitly disable desktop Qt renderers for the headless bridge.
    design = DesignPlanar(enable_renderers=False)
    class PhysicalNet(QComponent):
        def make(self):
            name = self.name
            rects = next(c for c in data['components'] if c['name'] == name)
            shapes = {f'{name}_{i}': box(*coords) for i,coords in enumerate(rects['rectangles_mm'])}
            self.add_qgeometry('poly',shapes,layer=rects['layer'],subtract=False)
    for component in data['components']:
        PhysicalNet(design,name=component['name'])
    return design
