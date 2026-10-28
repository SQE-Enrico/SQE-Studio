"""Independent reference problems: a plate capacitor and a rectangular PEC cavity."""

from collections import Counter
from itertools import permutations, product
from pathlib import Path

import numpy as np
from scipy.constants import c, epsilon_0
from scipy.sparse import coo_matrix
from scipy.sparse.linalg import spsolve

from . import em
from .io import digest, read_json, sha256, write_csv, write_json


def box_mesh(lengths_um, divisions):
    lengths = np.asarray(lengths_um, dtype=float)
    div = np.asarray(divisions)
    if (lengths.shape != (3,) or div.shape != (3,) or not np.all(np.isfinite(lengths))
        or np.any(lengths <= 0) or np.any(div < 1) or not np.all(div == div.astype(int))):
        raise ValueError("Specify three positive lengths and integer subdivisions")
    nx, ny, nz = map(int, div)
    nodes = np.array(list(product(np.linspace(0,lengths[0],nx+1),
                                 np.linspace(0,lengths[1],ny+1),
                                 np.linspace(0,lengths[2],nz+1))))

    def index(i,j,k):
        return (i*(ny+1)+j)*(nz+1)+k

    tets = []
    for i,j,k in product(range(nx),range(ny),range(nz)):
        for order in permutations(range(3)):
            corner = [i,j,k]
            vertices = [index(*corner)]
            for axis in order:
                corner[axis] += 1
                vertices.append(index(*corner))
            p = nodes[vertices]
            if np.linalg.det(p[1:]-p[0]) < 0:
                vertices[1],vertices[2] = vertices[2],vertices[1]
            tets.append(vertices)
    tets = np.asarray(tets,dtype=int)
    count = Counter(tuple(sorted(face)) for tet in tets for face in
                    [(tet[0],tet[1],tet[2]),(tet[0],tet[1],tet[3]),
                     (tet[0],tet[2],tet[3]),(tet[1],tet[2],tet[3])])
    if any(n not in (1,2) for n in count.values()):
        raise ValueError("Nonmanifold reference mesh")
    triangles = np.array([face for face,n in count.items() if n==1],dtype=int)
    center = lengths/2
    for face in triangles:
        p = nodes[face]
        if np.dot(np.cross(p[1]-p[0],p[2]-p[0]),p.mean(axis=0)-center)<0:
            face[1],face[2] = face[2],face[1]
    return nodes,tets,triangles


def write_msh(path,nodes,tets,triangles,plate=False):
    zmax = nodes[:,2].max()
    names = [(3,1,"dielectric"),(2,2,"ground"),(2,3,"terminal"),(2,4,"insulating_sides")] if plate else [(3,1,"vacuum"),(2,2,"pec_wall")]
    lines = ["$MeshFormat","2.2 0 8","$EndMeshFormat","$PhysicalNames",str(len(names))]
    lines += [f'{dim} {tag} "{name}"' for dim,tag,name in names]
    lines += ["$EndPhysicalNames","$Nodes",str(len(nodes))]
    lines += [f"{i} {x:.12g} {y:.12g} {z:.12g}" for i,(x,y,z) in enumerate(nodes,1)]
    lines += ["$EndNodes","$Elements",str(len(triangles)+len(tets))]
    for i,face in enumerate(triangles,1):
        zs = nodes[face,2]
        tag = (2 if np.all(zs==0) else 3 if np.all(zs==zmax) else 4) if plate else 2
        lines.append(f"{i} 2 2 {tag} {tag} "+" ".join(str(n+1) for n in face))
    for i,tet in enumerate(tets,len(triangles)+1):
        lines.append(f"{i} 4 2 1 1 "+" ".join(str(n+1) for n in tet))
    lines.append("$EndElements")
    Path(path).write_text("\n".join(lines)+"\n",encoding="ascii")


def capacitor_reference(nodes_um,tets,epsilon_r):
    if not np.isfinite(epsilon_r) or epsilon_r <= 0:
        raise ValueError("Permittivity must be positive and finite")
    nodes = nodes_um*1e-6
    rows,cols,values = [],[],[]
    for tet in tets:
        p = nodes[tet]
        volume = np.linalg.det(p[1:]-p[0])/6
        if volume <= 0:
            raise ValueError("Nonpositive tetrahedron Jacobian")
        grad = np.linalg.inv(np.column_stack((np.ones(4),p)))[1:]
        stiffness = epsilon_0*epsilon_r*volume*grad.T@grad
        rows.extend(np.repeat(tet,4))
        cols.extend(np.tile(tet,4))
        values.extend(stiffness.ravel())
    matrix = coo_matrix((values,(rows,cols)),shape=(len(nodes),len(nodes))).tocsr()
    bottom,top = nodes[:,2]==0,nodes[:,2]==nodes[:,2].max()
    free = ~(bottom|top)
    voltage = top.astype(float)
    if np.any(free):
        voltage[free] = spsolve(matrix[free][:,free],-(matrix@voltage)[free])
    cap = float(voltage @ (matrix@voltage))  # 2*stored energy / (one volt)^2
    lengths = nodes.max(axis=0)-nodes.min(axis=0)
    exact = epsilon_0*epsilon_r*lengths[0]*lengths[1]/lengths[2]
    error = abs(cap/exact-1)
    return {"source":"scipy_p1_fem_reference","capacitance_F":cap,
            "analytic_capacitance_F":exact,"relative_error":error,
            "maximum_potential_error_V":float(np.max(abs(voltage-nodes[:,2]/lengths[2]))),
            "pass":bool(error<1e-8),"potential_V":voltage,
            "boundary_model":"Insulated sides; full bottom/top plates; exact linear potential; no fringing"}


def cavity_frequencies(lengths_um,count=6):
    lengths = np.asarray(lengths_um,dtype=float)*1e-6
    if lengths.shape != (3,) or np.any(lengths<=0) or not np.all(np.isfinite(lengths)) or count<1:
        raise ValueError("Invalid cavity dimensions or mode count")
    # PEC box: at least two indices are nonzero; all-positive triples have two polarizations.
    limit = 2
    while True:
        modes = []
        for indices in product(range(limit+1),repeat=3):
            nonzero = np.count_nonzero(indices)
            if nonzero < 2:
                continue
            frequency = c/2*np.linalg.norm(np.array(indices)/lengths)/1e9
            modes.extend([float(frequency)]*(2 if nonzero==3 else 1))
        modes.sort()
        if len(modes)>=count and modes[count-1] < c/2*(limit+1)/max(lengths)/1e9:
            return modes[:count]
        limit *= 2
        if limit>64:
            raise ValueError("Requested cavity mode enumeration is too large")


def prepare(out,refinement=1):
    out = Path(out)
    if out.exists() and any(out.iterdir()):
        raise ValueError("Qualification needs a new output directory")
    if type(refinement) is not int or not 1<=refinement<=4:
        raise ValueError("Reference mesh refinement must be an integer 1..4")
    out.mkdir(parents=True,exist_ok=True)
    cases = {"capacitor": ((1000.,800.,500.),(4,4,2),True),
             "cavity": ((40000.,27000.,19000.),(8,6,4),False)}
    for name,(lengths,div,plate) in cases.items():
        folder = out/name
        folder.mkdir()
        nodes,tets,triangles = box_mesh(lengths,tuple(x*refinement for x in div))
        write_msh(folder/"device.msh",nodes,tets,triangles,plate)
        contract = {"case":name,"lengths_um":lengths,"refinement":refinement,
                    "mesh_generator":"native structured conformal tetrahedra; not Gmsh",
                    "physical_groups":{"volume":1,"ground_or_pec":2,"terminal":3,"sides":4} if plate else {"vacuum":1,"pec":2}}
        contract["geometry_sha256"] = digest(contract)
        write_json(folder/"contract.json",contract)
        write_json(folder/"mesh.json",{"geometry_sha256":contract["geometry_sha256"],
                    "mesh_sha256":sha256(folder/"device.msh"),"nodes":len(nodes),"tetrahedra":len(tets)})
        common = {"Model":{"Mesh":"device.msh","L0":1e-6},
                  "Domains":{"Materials":[{"Attributes":[1],"Permittivity":11.45 if plate else 1.0}]}}
        if plate:
            cfg = {**common,"Problem":{"Type":"Electrostatic","Output":"electrostatic"},
                   "Boundaries":{"Ground":{"Attributes":[2]},"ZeroCharge":{"Attributes":[4]},
                                 "Terminal":[{"Index":1,"Attributes":[3]}]},
                   "Solver":{"Order":1,"Electrostatic":{"Save":1},
                             "Linear":{"Type":"BoomerAMG","KSPType":"CG","Tol":1e-10,"MaxIts":500}}}
            write_json(folder/"electrostatic.json",cfg)
            reference = capacitor_reference(nodes,tets,11.45)
            potentials = reference.pop("potential_V")
            write_json(folder/"reference.json",reference)
            write_csv(folder/"potential.csv",{"x_um":nodes[:,0],"y_um":nodes[:,1],
                                               "z_um":nodes[:,2],"potential_V":potentials})
        else:
            exact = cavity_frequencies(lengths,6)
            cfg = {**common,"Problem":{"Type":"Eigenmode","Output":"eigenmode"},
                   "Boundaries":{"PEC":{"Attributes":[2]}},
                   "Solver":{"Order":2,"Eigenmode":{"Target":exact[0]*.8,"N":6,"Save":6,"Tol":1e-8},
                             "Linear":{"Type":"SuperLU","KSPType":"FGMRES","Tol":1e-10,"MaxIts":500}}}
            write_json(folder/"eigenmode.json",cfg)
            write_json(folder/"reference.json",{"source":"analytic_pec_box_spectrum",
                        "frequencies_GHz":exact,"includes_polarization_multiplicity":True})
    result = {"independent_capacitor_fem":"passed" if read_json(out/"capacitor/reference.json")["pass"] else "failed",
              "palace":"not_run","refinement":refinement,
              "scope":"Reference solver checks; these meshes are not the chip or its fabrication masks"}
    write_json(out/"qualification.json",result)
    return result


def qualify(out,refinement=1,solve=False,palace="palace",ranks=1):
    out = Path(out)
    result = prepare(out,refinement)
    if not solve:
        return result
    try:
        em.run_palace(out/"capacitor","electrostatic",palace,ranks)
        em.run_palace(out/"cavity","eigenmode",palace,ranks)
        observed = em.read_palace_capacitance(out/"capacitor/electrostatic/terminal-C.csv",terminal_count=1)[0,0]*1e-15
        expected = read_json(out/"capacitor/reference.json")["analytic_capacitance_F"]
        cap_error = abs(observed/expected-1)
        frequencies = [em.read_eigenfrequency(out/"cavity/eigenmode/eig.csv",i) for i in range(1,7)]
        exact = read_json(out/"cavity/reference.json")["frequencies_GHz"]
        cavity_error = max(abs(np.array(frequencies)/exact-1))
        result.update(palace="passed" if cap_error<1e-5 and cavity_error<.02 else "failed",
                      capacitor_relative_error=cap_error,cavity_max_relative_error=float(cavity_error),
                      tolerances={"capacitor":1e-5,"cavity":.02},observed_cavity_GHz=frequencies)
        write_json(out/"qualification.json",result)
        if result["palace"] != "passed":
            raise ValueError("Palace reference problem exceeded its numerical tolerances")
    except Exception as exc:
        result.update(palace="failed",error=str(exc))
        write_json(out/"qualification.json",result)
        raise
    return result
