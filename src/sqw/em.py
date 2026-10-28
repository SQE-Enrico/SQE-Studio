"""Gmsh OCC mesh and Palace configurations share exactly the lithography metal geometry."""

import csv
import copy
import re
import shutil
import subprocess
import time
from pathlib import Path

import numpy as np

from .circuit import junction, validate_capacitance
from .geometry import NETS, Rect
from .io import read_json, sha256, write_json

TAGS = {**NETS,"air":1,"silicon":2,"junction":21,"input":31,"output":32,"outer":99}


def mesh(cfg, geometry, out):
    import gmsh

    out = Path(out)
    out.mkdir(parents=True,exist_ok=True)
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal",1)
        gmsh.model.add("al_si_transmon")
        occ = gmsh.model.occ
        em,mat = cfg["em"],cfg["materials"]
        chip = Rect(**geometry["chip"])
        margin = em["box_margin_um"]
        box = chip.expanded(margin)
        th = mat["substrate_thickness_um"]
        zbot = -th-em["bottom_air_um"]
        air = occ.addBox(box.x0,box.y0,zbot,box.x1-box.x0,box.y1-box.y0,em["air_height_um"]-zbot)
        silicon = occ.addBox(chip.x0,chip.y0,-th,chip.x1-chip.x0,chip.y1-chip.y0,th)
        sheets = []
        owners = []
        for net, rects in geometry["metal"].items():
            pieces = []
            for rd in rects:
                r = Rect(**rd)
                pieces.append((2,occ.addRectangle(r.x0,r.y0,0,r.x1-r.x0,r.y1-r.y0)))
            merged = occ.fuse(pieces[:1],pieces[1:])[0] if len(pieces)>1 else pieces
            sheets.extend(merged)
            owners.extend([net]*len(merged))
        for name,rd in geometry["ports"].items():
            r = Rect(**rd)
            sheets.append((2,occ.addRectangle(r.x0,r.y0,0,r.x1-r.x0,r.y1-r.y0)))
            owners.append(name)
        _,mapping = occ.fragment([(3,air)],[(3,silicon)]+sheets)
        occ.synchronize()
        sivols = {t for d,t in mapping[1] if d==3}
        airvols = {t for d,t in mapping[0] if d==3}-sivols
        groups = {"air":sorted(airvols),"silicon":sorted(sivols)}
        for owner,mapped in zip(owners,mapping[2:],strict=True):
            groups.setdefault(owner,[]).extend(t for d,t in mapped if d==2)
        # Only true outer-box surfaces get the enclosing PEC / zero-V wall.
        outer = []
        tol = 1e-4
        for dim,tag in gmsh.model.getEntities(2):
            b = gmsh.model.getBoundingBox(dim,tag)
            for axis,values in [(0,[box.x0,box.x1]),(1,[box.y0,box.y1]),
                                (2,[zbot,em["air_height_um"]])]:
                if any(abs(b[axis]-v)<tol and abs(b[axis+3]-v)<tol for v in values):
                    outer.append(tag)
                    break
        groups["outer"] = outer
        for name,entities in groups.items():
            if not entities:
                raise ValueError(f"Empty physical group: {name}")
            gmsh.model.addPhysicalGroup(3 if name in ("air","silicon") else 2,
                                       sorted(set(entities)),TAGS[name],name)
        edges = sorted({abs(t) for n in NETS for s in groups[n]
                        for d,t in gmsh.model.getBoundary([(2,s)],oriented=False) if d==1})
        distance = gmsh.model.mesh.field.add("Distance")
        gmsh.model.mesh.field.setNumbers(distance,"CurvesList",edges)
        gmsh.model.mesh.field.setNumber(distance,"Sampling",1000)
        threshold = gmsh.model.mesh.field.add("Threshold")
        for key,value in {"InField":distance,"SizeMin":em["mesh_min_um"],
                          "SizeMax":em["mesh_max_um"],"DistMin":4,"DistMax":120}.items():
            gmsh.model.mesh.field.setNumber(threshold,key,value)
        gmsh.model.mesh.field.setAsBackgroundMesh(threshold)
        gmsh.option.setNumber("Mesh.MeshSizeFromPoints",0)
        gmsh.option.setNumber("Mesh.MeshSizeFromCurvature",0)
        gmsh.option.setNumber("Mesh.MeshSizeExtendFromBoundary",0)
        gmsh.option.setNumber("Mesh.MeshSizeMax",em["mesh_max_um"])
        gmsh.option.setNumber("Mesh.MshFileVersion",2.2)
        gmsh.model.mesh.generate(3)
        gmsh.write(str(out/"device.msh"))
        gmsh.write(str(out/"device.brep"))
        element_types,element_tags,_ = gmsh.model.mesh.getElements(3)
        stats = {"nodes":len(gmsh.model.mesh.getNodes()[0]),
                 "volume_elements":sum(len(x) for x in element_tags),
                 "element_types":element_types.tolist(),"physical_groups":groups,
                 "geometry_sha256":geometry["geometry_sha256"],
                 "mesh_sha256":sha256(out/"device.msh"),"units":"um"}
        write_json(out/"mesh.json",stats)
        return stats
    finally:
        gmsh.finalize()


def export_configs(cfg, geometry, out):
    out = Path(out)
    out.mkdir(parents=True,exist_ok=True)
    em = cfg["em"]
    mats = [{"Attributes":[1],"Permittivity":1.0},
            {"Attributes":[2],"Permittivity":cfg["materials"]["epsilon_r"]}]
    linear = {"Type":"BoomerAMG","KSPType":"CG","Tol":em["linear_tol"],"MaxIts":500}
    base = {"Model":{"Mesh":"device.msh","L0":1e-6},
            "Domains":{"Materials":mats,"Postprocessing":{"Energy":[{"Index":2,"Attributes":[2]}]}}}
    electrostatic = {**base,"Problem":{"Type":"Electrostatic","Output":"electrostatic"},
                     "Boundaries":{"Ground":{"Attributes":[10,99]},
                                   "Terminal":[{"Index":i,"Attributes":[tag]} for i,tag in enumerate([11,12,13,14],1)]},
                     "Solver":{"Order":em["order"],"Electrostatic":{"Save":4},"Linear":linear}}
    common_ports = [{"Index":1,"Attributes":[31],"Direction":"+Y","R":50.0},
                    {"Index":2,"Attributes":[32],"Direction":"+Y","R":50.0}]
    eigen_linear = {"Type":"SuperLU","KSPType":"FGMRES","Tol":em["linear_tol"],"MaxIts":500}
    eigen = {**base,"Problem":{"Type":"Eigenmode","Output":"eigenmode"},
             "Boundaries":{"PEC":{"Attributes":[10,11,12,13,14,99]},"LumpedPort":common_ports},
             "Solver":{"Order":em["order"],"Eigenmode":{"Target":em["eigen_target_GHz"],
                        "N":em["modes"],"Save":em["modes"],"Tol":1e-7},"Linear":eigen_linear}}
    ls = em["kinetic_Ls_pH_per_square"]*1e-12
    if ls:
        eigen["Boundaries"]["PEC"]["Attributes"] = [99]
        eigen["Boundaries"]["Impedance"] = [{"Attributes":[10,11,12,13,14],"Ls":ls}]
    full = copy.deepcopy(eigen)
    full["Problem"]["Output"] = "linearized"
    jj = junction(cfg)
    full["Boundaries"]["LumpedPort"].append({"Index":3,"Attributes":[21],"Direction":"+X",
                                            "L":jj["LJ_nH"]*1e-9,"C":jj["Cj_fF"]*1e-15})
    # Driven S-parameters: open transmon gap; two distinct excitations produce both S columns.
    # Verified against the stable Palace JSON reference, not a qualified solver run.
    driven = copy.deepcopy(eigen)
    driven["Problem"] = {"Type":"Driven", "Output":"driven"}
    driven["Boundaries"]["LumpedPort"][0]["Excitation"] = 1
    driven["Boundaries"]["LumpedPort"][1]["Excitation"] = 0
    driven["Solver"].pop("Eigenmode")
    driven["Solver"]["Driven"] = {"Samples":[{"Type":"Linear", "MinFreq":max(.1,cfg["device"]["band_min_GHz"]),
        "MaxFreq":cfg["device"]["band_max_GHz"], "NSample":61, "SaveStep":0}]}
    driven_p2 = copy.deepcopy(driven)
    driven_p2['Problem']['Output'] = 'driven-p2'
    driven_p2['Boundaries']['LumpedPort'][0]['Excitation'] = 0
    driven_p2['Boundaries']['LumpedPort'][1]['Excitation'] = 1
    for name,data in [("electrostatic",electrostatic),("eigenmode",eigen),
                      ("linearized",full),("driven",driven),("driven-p2",driven_p2)]:
        write_json(out/f"{name}.json",data)
    write_json(out/"contract.json",{"geometry_sha256":geometry["geometry_sha256"],
                "terminal_order":["pad_a","pad_b","resonator","feedline"],
                "physical_tags":TAGS,"capacitance_convention":"Maxwell; JJ C excluded",
                "driven_columns":{"driven":"input","driven-p2":"output"},
                "bare_eigenmode":"Open JJ port; identify readout from fields before import",
                "linearized_eigenmode":"Includes LJ and Cj; cross-check only; do not re-quantize as bare"})


def run_palace(out, problem, executable="palace", ranks=1, timeout=14400):
    out = Path(out).resolve()
    if problem not in ("electrostatic","eigenmode","linearized","driven"):
        raise ValueError("Unknown Palace problem")
    if not (out/"device.msh").is_file():
        raise ValueError("Generate the Gmsh mesh first")
    if type(ranks) is not int or ranks < 1:
        raise ValueError("MPI ranks must be a positive integer")
    mesh_record = read_json(out/"mesh.json")
    contract = read_json(out/"contract.json")
    if (mesh_record["geometry_sha256"] != contract["geometry_sha256"] or
        mesh_record["mesh_sha256"] != sha256(out/"device.msh")):
        raise ValueError("Mesh and EM configuration do not belong to the same geometry")
    problem_output = out/read_json(out/f"{problem}.json")["Problem"]["Output"]
    if problem_output.exists() and any(problem_output.iterdir()):
        raise ValueError("Existing solver output is preserved; use a fresh run directory")
    from .palace_bridge import command as palace_command
    command, identity = palace_command(out,problem,ranks,executable)
    record = {"status":"running","command":command,
              "executable_identity":identity,
              "executable_sha256":sha256(identity) if Path(identity).is_file() else None,
              "mesh_sha256":sha256(out/"device.msh"),
              "configuration_sha256":sha256(out/f"{problem}.json"),
              "contract_sha256":sha256(out/"contract.json")}
    record_path = out/f"solve-{problem}.json"
    write_json(record_path,record)
    start = time.monotonic()
    try:
        with (out/f"{problem}.log").open("w") as log:
            subprocess.run(command,cwd=out,stdout=log,stderr=subprocess.STDOUT,
                           check=True,timeout=timeout)
        expected = {"electrostatic":"terminal-C.csv", "eigenmode":"eig.csv", "linearized":"eig.csv",
                    "driven":"port-S.csv"}[problem]
        expected_csv = problem_output/expected
        if not expected_csv.is_file() or expected_csv.stat().st_size==0:
            raise ValueError(f"Palace exited without the expected result: {expected_csv.name}")
        hashes={p.relative_to(out).as_posix():sha256(p) for p in sorted(problem_output.rglob("*.csv"))}
        if problem=='driven':
            second=out/'driven-p2'
            if second.exists() and any(second.iterdir()):
                raise ValueError('Second driven port result already exists; preserve prior outputs')
            second_command,_=palace_command(out,'driven-p2',ranks,executable)
            with (out/'driven-p2.log').open('w') as log:
                subprocess.run(second_command,cwd=out,stdout=log,stderr=subprocess.STDOUT,
                               check=True,timeout=timeout)
            if not (second/'port-S.csv').is_file() or not (second/'port-S.csv').stat().st_size:
                raise ValueError('Palace did not produce the second S-parameter column')
            hashes.update({p.relative_to(out).as_posix():sha256(p) for p in sorted(second.rglob('*.csv'))})
            record['secondary_configuration_sha256']=sha256(out/'driven-p2.json')
        record.update(status="completed",elapsed_seconds=time.monotonic()-start, raw_sha256=hashes)
        write_json(record_path,record)
    except Exception as exc:
        record.update(status="failed",error=str(exc),elapsed_seconds=time.monotonic()-start)
        write_json(record_path,record)
        raise


def read_palace_capacitance(path, terminal_count=4):
    if type(terminal_count) is not int or terminal_count<1:
        raise ValueError("Terminal count must be a positive integer")
    with Path(path).open() as f:
        reader = csv.reader(f)
        header = [x.strip() for x in next(reader,[])]
        expected = ["i"]+[f"C[i][{i}] (F)" for i in range(1,terminal_count+1)]
        if header != expected:
            raise ValueError(f"Unsupported Palace capacitance header: {header}; units must be F")
        rows = [[float(x) for x in row] for row in reader if row and any(x.strip() for x in row)]
    data = np.array(rows)
    if (data.shape != (terminal_count,terminal_count+1) or
        not np.array_equal(data[:,0],np.arange(1,terminal_count+1))):
        raise ValueError("Expected each declared terminal exactly once and in order")
    matrix = data[:,1:]*1e15
    if terminal_count==4:
        return validate_capacitance(matrix)
    if (not np.all(np.isfinite(matrix)) or not np.allclose(matrix,matrix.T,rtol=1e-7,atol=1e-8)
        or np.any(matrix-np.diag(np.diag(matrix))>1e-8) or np.any(matrix.sum(axis=1)<-1e-7)
        or np.linalg.eigvalsh(matrix).min()<=0):
        raise ValueError("Invalid Maxwell capacitance matrix")
    return matrix


def read_eigenfrequency(path, mode):
    if type(mode) is not int or mode<1:
        raise ValueError("Mode index must be a positive integer")
    with Path(path).open() as f:
        reader = csv.DictReader(f,skipinitialspace=True)
        fields = [n.strip() for n in (reader.fieldnames or [])]
        index = next((x for x in fields if x in ("i","m","Mode","Index")),None)
        realfreq = next((x for x in fields if re.fullmatch(r"(?:Re\{)?f(?:\})? \(GHz\)",x)),None)
        if index is None or realfreq is None:
            raise ValueError(f"Unsupported eigenmode headers {fields}; do not guess units or columns")
        frequencies = {}
        for raw in reader:
            row = {name.strip():value for name,value in raw.items()}
            number,value = float(row[index]),float(row[realfreq])
            if not np.isfinite(number) or not number.is_integer() or number<1:
                raise ValueError("Eigenmode index must be a positive integer")
            if not np.isfinite(value) or value<=0 or number in frequencies:
                raise ValueError("Invalid eigenfrequency or duplicate mode index")
            frequencies[int(number)] = value
        if mode in frequencies:
            return frequencies[mode]
    raise ValueError(f"Readout mode {mode} absent")


def validate_solve_record(out,name):
    out = Path(out)
    record = read_json(out/f"solve-{name}.json")
    if (record["status"] != "completed" or
        record["mesh_sha256"] != sha256(out/"device.msh") or
        record["configuration_sha256"] != sha256(out/f"{name}.json") or
        record["contract_sha256"] != sha256(out/"contract.json") or
        not record.get("raw_sha256") or
        (name=='driven' and record.get('secondary_configuration_sha256')!=sha256(out/'driven-p2.json'))):
        raise ValueError(f"Stale or unverified Palace solve: {name}")
    for path,expected in record["raw_sha256"].items():
        if not (out/path).is_file() or sha256(out/path)!=expected:
            raise ValueError(f"Palace raw output was changed: {path}")
    return record


def import_results(out, geometry, mode, eigen_file="eig.csv"):
    out = Path(out)
    contract = read_json(out/"contract.json")
    if contract["geometry_sha256"] != geometry["geometry_sha256"]:
        raise ValueError("EM contract belongs to a different geometry")
    for name in ("electrostatic","eigenmode"):
        validate_solve_record(out,name)
    cap_path = out/"electrostatic"/"terminal-C.csv"
    eigen_path = out/"eigenmode"/eigen_file
    result = {"schema_version":1,"source":"palace_fem","synthetic":False,
              "node_order":["pad_a","pad_b","resonator","feedline"],
              "matrix_fF":read_palace_capacitance(cap_path).tolist(),
              "readout_GHz":read_eigenfrequency(eigen_path,mode),"readout_mode":mode,
              "geometry_sha256":geometry["geometry_sha256"],
              "raw_sha256":{p.relative_to(out).as_posix():sha256(p) for p in (cap_path,eigen_path)},
              "assumptions":["Readout mode identified by user from fields",
                            "Passive distributed readout mapped to a two-mode lumped model",
                            "Convergence and package validation are separate acceptance steps"]}
    return result


def epr_kerr(frequencies_GHz, junction_EJ_GHz, participation):
    """First-order EPR Kerr magnitudes. Input matrix shape modes x junctions."""
    f,ej,p = map(np.asarray,(frequencies_GHz,junction_EJ_GHz,participation))
    if p.shape != (len(f),len(ej)) or np.any(p<0) or np.any(p>1) or np.any(p.sum(axis=1)>1+1e-8):
        raise ValueError("Invalid junction energy participation matrix")
    if np.any(f<=0) or np.any(ej<=0):
        raise ValueError("Frequencies and Josephson energies must be positive")
    cross = np.outer(f,f)/4 * ((p/ej)@p.T)
    # Cross-Kerr magnitude chi_mn; self-anharmonicity is half the diagonal.
    return {"cross_Kerr_MHz":cross*1000,"anharmonicity_MHz":-np.diag(cross)*500,
            "method":"first-order EPR; junction energies / total inductive energy",
            "warning":"Use with linearized modes; do not add to exact transmon anharmonicity"}
