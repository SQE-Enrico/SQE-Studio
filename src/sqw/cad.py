"""Deterministic GDSII fallback plus a QPDK/gdsfactory production authoring adapter."""

import struct
from pathlib import Path

from .geometry import Rect


def _real8(value):
    if not value:
        return b"\0"*8
    sign = 128 if value < 0 else 0
    value, exponent = abs(value), 64
    while value >= 1:
        value /= 16
        exponent += 1
    while value < 1/16:
        value *= 16
        exponent -= 1
    return bytes([sign | exponent]) + int(value*(1 << 56)).to_bytes(7,"big")


def _record(kind, dtype=0, payload=b""):
    if len(payload)%2:
        payload += b"\0"
    return struct.pack(">HBB",4+len(payload),kind,dtype)+payload


def _boundary(rect, layer, datatype=0):
    points = rect.polygon()
    points.append(points[0])
    coords = [int(round(v*1000)) for p in points for v in p]  # 1 nm database unit
    return b"".join([_record(8), _record(13,2,struct.pack(">h",layer)),
                     _record(14,2,struct.pack(">h",datatype)),
                     _record(16,3,struct.pack(">"+"i"*len(coords),*coords)), _record(17)])


def _polygon(points, layer, datatype=0):
    """GDSII BOUNDARY with general polygon vertices; 1 nm database unit."""
    if len(points)<3 or len(points)>199:
        raise ValueError('GDS polygon needs 3..199 vertices')
    coords=[(round(float(x)*1000),round(float(y)*1000)) for x,y in points]
    if coords[0]!=coords[-1]:coords.append(coords[0])
    values=[v for pair in coords for v in pair]
    if any(not -(2**31)<=v<2**31 for v in values):raise ValueError('GDS coordinate exceeds signed 32-bit units')
    return b''.join([_record(8),_record(13,2,struct.pack('>h',layer)),
                     _record(14,2,struct.pack('>h',datatype)),
                     _record(16,3,struct.pack('>'+('i'*len(values)),*values)),_record(17)])


def _extra_rectangles(data):
    c = Rect(**data["chip"])
    # Chip outline is an annotation frame, never a filled metal rectangle.
    for r in (Rect(c.x0,c.y0,c.x1,c.y0+2), Rect(c.x0,c.y1-2,c.x1,c.y1),
              Rect(c.x0,c.y0,c.x0+2,c.y1), Rect(c.x1-2,c.y0,c.x1,c.y1)):
        yield r, 99
    for x,y in [(x,y) for x in (c.x0+500,c.x1-500) for y in (c.y0+500,c.y1-500)]:
        yield Rect(x-40,y-4,x+40,y+4), 90
        yield Rect(x-4,y-40,x+4,y+40), 90
    yield Rect(**data["ports"]["junction"]), 91  # junction location / design intent only


def write_gds(data, path, backend="native"):
    if backend == "qpdk":
        return _write_qpdk(data, path)
    if backend != "native":
        raise ValueError(f"Unknown CAD backend: {backend}")
    dates = struct.pack(">12h", *([2000,1,1,0,0,0]*2))
    records = [_record(0,2,struct.pack(">h",600)), _record(1,2,dates),
               _record(2,6,b"SQW"), _record(3,5,_real8(1e-3)+_real8(1e-9)),
               _record(5,2,dates), _record(6,6,b"AL_SI_TRANSMON")]
    for rects in data["metal"].values():
        records += [_boundary(Rect(**r),1) for r in rects]
    records += [_boundary(r,layer) for r,layer in _extra_rectangles(data)]
    records += [_record(7), _record(4)]
    Path(path).write_bytes(b"".join(records))


def _subtract(rect, cut):
    x0,y0,x1,y1 = max(rect.x0,cut.x0),max(rect.y0,cut.y0),min(rect.x1,cut.x1),min(rect.y1,cut.y1)
    if x0 >= x1 or y0 >= y1:
        return [rect]
    candidates = [(rect.x0,rect.y0,rect.x1,y0), (rect.x0,y1,rect.x1,rect.y1),
                  (rect.x0,y0,x0,y1), (x1,y0,rect.x1,y1)]
    return [Rect(*r) for r in candidates if r[2]>r[0] and r[3]>r[1]]


def _write_qpdk(data, path):
    import gdsfactory as gf
    from qpdk import PDK
    from qpdk.cells.transmon import double_pad_transmon

    PDK.activate()
    pads = [Rect(**r) for r in data["pads"]]
    p = pads[0]
    # QPDK owns the two capacitor pads. The process-specific junction is intentionally
    # replaced by a location marker. No generic PDK junction is treated as qualified.
    marker = gf.Component()
    marker.add_polygon([(-1,-1),(1,-1),(1,1),(-1,1)],layer=(91,0))
    qubit = double_pad_transmon(pad_size=(p.x1-p.x0,p.y1-p.y0),
                               pad_gap=pads[1].x0-p.x1,
                               junction_spec=marker, layer_metal=(1,0))
    top = gf.Component()
    qr = top.add_ref(qubit)
    qr.dmove((0,(p.y0+p.y1)/2))
    for rects in data["metal"].values():
        for rd in rects:
            pieces = [Rect(**rd)]
            for pad in pads:
                pieces = [r2 for r in pieces for r2 in _subtract(r,pad)]
            for r in pieces:
                top.add_polygon(r.polygon(),layer=(1,0))
    for r,layer in _extra_rectangles(data):
        if layer != 91:
            top.add_polygon(r.polygon(),layer=(layer,0))
    top.write_gds(path)
    # Verify the actual exported positive-metal area against the common geometry.
    import klayout.db as kdb
    layout = kdb.Layout()
    layout.read(str(path))
    region = kdb.Region(layout.top_cell().begin_shapes_rec(layout.layer(1,0)))
    expected = kdb.Region()
    for rects in data["metal"].values():
        for rd in rects:
            r = Rect(**rd)
            expected.insert(kdb.Box(*(round(v/layout.dbu) for v in (r.x0,r.y0,r.x1,r.y1))))
    difference = region.merged() ^ expected.merged()
    if not difference.is_empty():
        raise ValueError(f"QPDK exported metal differs from shared geometry by {difference.area()*layout.dbu**2} um^2")


def inspect_gds(path):
    """Independent record validation for the flat native writer (not a general GDS reader)."""
    raw, offset, polygons, layers = Path(path).read_bytes(), 0, 0, set()
    while offset < len(raw):
        if offset+4 > len(raw):
            raise ValueError("Truncated GDS header")
        size,kind,dtype = struct.unpack(">HBB",raw[offset:offset+4])
        if size < 4 or size%2 or offset+size > len(raw):
            raise ValueError("Invalid GDS record")
        if kind == 8:
            polygons += 1
        if kind == 13:
            layers.add(struct.unpack(">h",raw[offset+4:offset+6])[0])
        offset += size
    if not raw.endswith(_record(4)) or polygons == 0:
        raise ValueError("Incomplete GDS library")
    return {"polygons": polygons,"layers": sorted(layers),"bytes": len(raw)}


def write_library(path,cells):
    """Native hierarchical GDSII for process/wafer candidates; 1 nm database unit."""
    dates = struct.pack('>12h',*([2000,1,1,0,0,0]*2))
    records = [_record(0,2,struct.pack('>h',600)),_record(1,2,dates),_record(2,6,b'SQE_STUDIO'),
               _record(3,5,_real8(1e-3)+_real8(1e-9))]
    names = {cell['name'] for cell in cells}
    if len(names)!=len(cells): raise ValueError('GDS cell names must be unique')
    for cell in cells:
        records += [_record(5,2,dates),_record(6,6,cell['name'].encode('ascii'))]
        records += [_boundary(r,layer,datatype) for r,layer,datatype in cell.get('rectangles',[])]
        records += [_polygon(points,layer,datatype) for points,layer,datatype in cell.get('polygons',[])]
        for name,x,y in cell.get('references',[]):
            if name not in names: raise ValueError('Unknown referenced GDS cell')
            records += [_record(10),_record(18,6,name.encode('ascii')),
                        _record(16,3,struct.pack('>ii',round(x*1000),round(y*1000))),_record(17)]
        records.append(_record(7))
    records.append(_record(4))
    Path(path).write_bytes(b''.join(records))
