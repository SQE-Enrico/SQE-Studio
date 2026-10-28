"""Concept-only GDS: schematic-to-geometric placeholders, not mask/EM equivalence.

The bare native writer in sqw.cad has no proprietary dependencies. All polygons
are positive-metal rectangles; Josephson junctions are only reference markers.
"""
from pathlib import Path
from . import cad
from .geometry import Rect
from .quantumlab import validate


def candidate(design, output):
    validate(design)
    chip=design.get('chip') or {}
    width=float(chip.get('width_um',1500))
    height=float(chip.get('height_um',1500))
    if not (400<=width<=30000 and 400<=height<=30000):
        raise ValueError('Chip dimension must be 400–30000 um')
    positions=design.get('positions') or {}
    nodes=sorted({e[pin] for e in design['elements'] for pin in ('a','b') if e[pin]!='0'})
    for i,node in enumerate(nodes):
        v=positions.get(node)
        if not (isinstance(v,list) and len(v)==2 and all(isinstance(x,(int,float)) and abs(x)<1e6 for x in v)):
            positions[node]=[100+(i%8)*130,100+(i//8)*150]
    maxx=max(p[0] for p in positions.values())
    maxy=max(p[1] for p in positions.values())
    scalex=min(1.,(width-180)/max(100,maxx))
    scaley=min(1.,(height-180)/max(100,maxy))
    def at(node):
        x,y=positions[node]
        return -width/2+90+x*scalex, height/2-90-y*scaley
    rects=[]
    # Two islands separated by a drawn junction gap; never imply a qualified Josephson process.
    for qubit in design.get('qubits',[]):
        x,y=at(qubit['node'])
        rects.extend([(Rect(x-42,y-40,x-3,y+40),1,0),
                      (Rect(x+3,y-40,x+42,y+40),1,0),
                      (Rect(x-3,y-3,x+3,y+3),91,0)])
    for node in nodes:
        if node.startswith('r'):
            x,y=at(node)
            for i in range(5):
                yy=y-20+i*10
                rects.append((Rect(x-38,yy,x+38,yy+3),1,0))
                if i<4:
                    xx=x+36 if i%2==0 else x-39
                    rects.append((Rect(xx,yy,xx+3,yy+13),1,0))
    # Frame only, not a metal plane.
    for rect in (Rect(-width/2,-height/2,width/2,-height/2+2),
                 Rect(-width/2,height/2-2,width/2,height/2),
                 Rect(-width/2,-height/2,-width/2+2,height/2),
                 Rect(width/2-2,-height/2,width/2,height/2)):
        rects.append((rect,99,0))
    path=Path(output)
    path.parent.mkdir(parents=True,exist_ok=True)
    cad.write_library(path,[{'name':'QPU_CONCEPT','rectangles':rects}])
    return {'path':str(path),'polygons':cad.inspect_gds(path)['polygons'],
            'quality':'CONCEPT_ONLY_NOT_FABRICATION_READY',
            'warning':'No topological wiring, DRC, calibrated couplings, JJ fabrication or ground/CPW mesh; layout is a graphical candidate.'}
