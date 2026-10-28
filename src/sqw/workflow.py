"""Explicit stage orchestration with input fingerprints and artifact manifests."""

import csv
import html
from pathlib import Path

import numpy as np

from . import __version__, cad, circuit, em, experiment, geometry, provenance
from .io import digest, environment, read_json, sha256, write_csv, write_json


def prepare(cfg, out):
    out = Path(out)
    out.mkdir(parents=True,exist_ok=True)
    path = out/"run.json"
    fingerprint = digest(cfg)
    if path.exists():
        state = read_json(path)
        if state["config_sha256"] != fingerprint:
            raise ValueError("Output directory belongs to a different configuration; use a new directory")
        if digest(read_json(out/"resolved_config.json")) != fingerprint:
            raise ValueError("The stored resolved configuration was changed; create a fresh run")
    else:
        state = {"schema_version":1,"software_version":__version__,"config_sha256":fingerprint,
                 "environment":environment(),"stages":{},"stage_records":{},"fabrication_status":"HOLD"}
        write_json(out/"resolved_config.json",cfg)
        write_json(path,state)
    return out,state


def _geometry(out):
    data = read_json(out/"layout"/"geometry.json")
    original = dict(data)
    original.pop("geometry_sha256")
    if digest(original) != data["geometry_sha256"]:
        raise ValueError("Geometry artifact was changed; rebuild it")
    return data


def stage(name,cfg,out,cad_backend="native",quantum_backend="scipy",dynamics_backend="scipy",
          extraction=None,readout_mode=None,palace="palace",ranks=1,problem="electrostatic",
          force_surrogate=False):
    out,state = prepare(cfg,out)
    key = name+":"+problem if name=="solve" else name
    if force_surrogate and (name != "quantize" or extraction is not None):
        raise ValueError("--force-surrogate is valid only for quantize without --extraction")
    prerequisites = {
        "em-export": ["layout"], "mesh": ["layout"],
        "solve": ["em-export", "mesh"],
        "import": ["layout", "solve:electrostatic", "solve:eigenmode"],
        "quantize": ["layout"], "experiment": ["layout", "quantize"],
        "report": ["spec", "layout", "quantize", "experiment"],
    }
    parents = list(prerequisites.get(name, []))
    for parent in parents:
        provenance.check_stage(state, parent, out)
    if name == "quantize":
        if extraction is None and not force_surrogate and (out/"extraction.json").exists():
            extraction = out/"extraction.json"
        if extraction is not None and Path(extraction).resolve() == (out/"extraction.json").resolve():
            if state["stages"].get("import") == "completed":
                provenance.check_stage(state, "import", out)
                parents.append("import")
            elif state["stages"].get("import") == "stale":
                raise ValueError("Imported extraction is stale; rerun import or choose --force-surrogate")
        elif "import" in state["stages"]:
            state["stages"]["import"] = "superseded"
    provenance.invalidate(state, key)
    inputs = [out/"resolved_config.json"]
    if name not in ("spec", "layout"):
        inputs.append(out/"layout/geometry.json")
    if name == "quantize" and extraction is not None:
        inputs.append(Path(extraction))
    if name == "experiment":
        inputs.append(out/"parameters.json")
    if name == "report":
        inputs += [out/"parameters.json", out/"experiment/model.json", out/"specification.json"]
    if name == "solve":
        inputs += [out/"em"/item for item in ("device.msh","mesh.json","contract.json",f"{problem}.json")]
    if name == "import":
        inputs += [out/"em"/"device.msh",out/"em"/"contract.json"]
        for solved in ("electrostatic","eigenmode"):
            record_path = out/"em"/f"solve-{solved}.json"
            inputs.append(record_path)
            inputs.extend(out/"em"/path for path in read_json(record_path)["raw_sha256"])
    input_hashes = provenance.hashes(inputs, out)
    state["stages"][key] = "running"
    write_json(out/"run.json",state)
    try:
        if name == "spec":
            write_json(out/"specification.json",circuit.synthesize(cfg))
        elif name == "layout":
            dest = out/"layout"
            dest.mkdir(exist_ok=True)
            geom = geometry.build(cfg)
            geometry.save(geom,dest/"geometry.json")
            cad.write_gds(geom,dest/"device.gds",cad_backend)
            geometry.preview(geom,dest/"layout.png")
            write_json(dest/"cad_validation.json",cad.inspect_gds(dest/"device.gds"))
            write_json(dest/"fabrication.json",{
                "status":"HOLD","mask_polarity":"positive metal on layer 1/0",
                "junction_layer":"91/0 is location only; no evaporation / oxide definition",
                "checks":["Shared geometry connectivity and isolation passed"],
                "missing":["Qualified junction mask and evaporation process",
                           "Lab layer map, polarity, bias, fracture and DRC sign-off",
                           "Package/bond wire/ground continuity review",
                           "Converged EM and measured reference-chip validation"]})
        elif name == "em-export":
            em.export_configs(cfg,_geometry(out),out/"em")
        elif name == "mesh":
            em.mesh(cfg,_geometry(out),out/"em")
        elif name == "solve":
            em.run_palace(out/"em",problem,palace,ranks)
        elif name == "import":
            if readout_mode is None:
                raise ValueError("Provide --readout-mode after field-based mode identification")
            result = em.import_results(out/"em",_geometry(out),readout_mode)
            write_json(out/"extraction.json",result)
        elif name == "quantize":
            geom = _geometry(out)
            result = read_json(extraction) if extraction else circuit.surrogate(cfg,geom)
            if result.get("node_order") != ["pad_a","pad_b","resonator","feedline"]:
                raise ValueError("Extraction node order mismatch")
            if result.get("source") not in ("analytic_surrogate","synthetic_fixture","palace_fem"):
                raise ValueError("Unrecognized extraction provenance")
            if result["geometry_sha256"] != geom["geometry_sha256"]:
                raise ValueError("Extraction does not belong to this geometry")
            fr = result["readout_GHz"]
            if not cfg["device"]["band_min_GHz"] <= fr <= cfg["device"]["band_max_GHz"]:
                raise ValueError("Imported readout mode is outside the operating band")
            write_json(out/"extraction.json",result)
            params = circuit.parameters(cfg,result,quantum_backend)
            write_json(out/"parameters.json",params)
            state["physics_source"] = result["source"]
        elif name == "experiment":
            params = read_json(out/"parameters.json")
            if params["geometry_sha256"] != _geometry(out)["geometry_sha256"]:
                raise ValueError("Parameters do not match geometry")
            experiment.simulate(cfg,params,out/"experiment",dynamics_backend)
        elif name == "report":
            report(cfg,out)
        else:
            raise ValueError(f"Unknown stage: {name}")
    except Exception as exc:
        state["stages"][key] = {"status":"failed","error":str(exc)}
        write_json(out/"run.json",state)
        raise
    state["stages"][key] = "completed"
    outputs = {
        "spec": [out/"specification.json"],
        "layout": list((out/"layout").glob("*")),
        "em-export": [out/"em"/f"{item}.json" for item in ("electrostatic", "eigenmode", "linearized", "driven", "contract")],
        "mesh": [out/"em"/item for item in ("device.msh", "device.brep", "mesh.json")],
        "solve": [out/"em"/f"solve-{problem}.json", out/"em"/f"{problem}.log"],
        "import": [out/"extraction.json"],
        "quantize": [out/"parameters.json", out/"extraction.json"],
        "experiment": list((out/"experiment").glob("*")) if (out/"experiment").exists() else [],
        "report": [out/"report.html"],
    }[name]
    if name == "solve":
        outputs.extend(out/"em"/path for path in read_json(out/"em"/f"solve-{problem}.json")["raw_sha256"])
    if name == "quantize" and extraction is None:
        # Record the generated surrogate as an input as well, so edits cannot be silent.
        input_hashes.update(provenance.hashes([out/"extraction.json"], out))
    state.setdefault("stage_records", {})[key] = {
        "inputs": input_hashes,
        "outputs": provenance.hashes([path for path in outputs if path.is_file()], out),
        "parents":parents,
        "backends": {"cad": cad_backend, "quantum": quantum_backend, "dynamics": dynamics_backend},
    }
    write_json(out/"run.json",state)
    manifest(out)


def manifest(out):
    files = {p.relative_to(out).as_posix():sha256(p) for p in sorted(out.rglob("*"))
             if p.is_file() and p.name != "manifest.json"}
    write_json(out/"manifest.json",{"sha256":files})


def run(cfg,out,mode="demo",cad_backend="native",quantum_backend="scipy",
        dynamics_backend="scipy",extraction=None,readout_mode=None,palace="palace",ranks=1):
    out = Path(out)
    if out.exists() and any(out.iterdir()):
        raise ValueError("run requires a new/empty output directory; use stage for existing runs")
    if mode == "fem" and readout_mode is None:
        raise ValueError("FEM run requires --readout-mode; first identify modes with individual stages")
    if mode == "imported" and extraction is None:
        raise ValueError("Imported run requires --extraction")
    opts = dict(cad_backend=cad_backend,quantum_backend=quantum_backend,
                dynamics_backend=dynamics_backend,palace=palace,ranks=ranks)
    for name in ("spec","layout","em-export"):
        stage(name,cfg,out,**opts)
    if mode == "fem":
        stage("mesh",cfg,out,**opts)
        for problem in ("electrostatic","eigenmode"):
            stage("solve",cfg,out,problem=problem,**opts)
        stage("import",cfg,out,readout_mode=readout_mode,**opts)
        extraction = out/"extraction.json"
    stage("quantize",cfg,out,extraction=extraction,force_surrogate=(mode == "demo" and extraction is None),**opts)
    stage("experiment",cfg,out,**opts)
    stage("report",cfg,out,**opts)


def report(cfg,out):
    p = read_json(out/"parameters.json")
    metrics = read_json(out/"experiment"/"model.json")
    rows = [("Source",p["source"]),("f01 (GHz)",f"{p['f01_GHz']:.6f}"),
            ("Anharmonicity (MHz)",f"{p['anharmonicity_MHz']:.3f}"),
            ("Bare readout (GHz)",f"{p['readout_bare_GHz']:.6f}"),
            ("g / 2pi (MHz)",f"{p['g_MHz']:.3f}"),
            ("chi / 2pi (MHz)",f"{p['chi_exact_MHz']:.3f}"),
            ("EJ / h (GHz)",f"{p['EJ_GHz']:.4f}"),("EC / h (GHz)",f"{p['EC_GHz']:.4f}"),
            ("Effective qubit C (fF)",f"{p['C_qubit_effective_fF']:.3f}"),
            ("Junction Ic (nA)",f"{p['junction']['Ic_nA']:.3f}"),
            ("Junction LJ (nH)",f"{p['junction']['LJ_nH']:.3f}"),
            ("Conditional T1 (us)",f"{metrics['T1_effective_us']:.3f}"),
            ("Conditional T2 (us)",f"{metrics['T2_us']:.3f}")]
    table = "".join(f"<tr><th>{html.escape(k)}</th><td>{html.escape(str(v))}</td></tr>" for k,v in rows)
    content = f'''<!doctype html><html lang="en"><meta charset="utf-8">
<title>Superconducting qubit workflow report</title><style>
body{{font:16px system-ui,sans-serif;max-width:1100px;margin:40px auto;padding:0 24px;color:#17243b}}
h1{{font-size:36px}} .status{{background:#fff4db;border-left:5px solid #e87722;padding:18px}}
table{{border-collapse:collapse;width:100%;margin:25px 0}}th,td{{text-align:left;padding:9px;border-bottom:1px solid #ddd}}
img{{width:100%}}a{{color:#1d4ed8}}small{{color:#526078}}
</style><h1>From specifications to expected measurements</h1>
<p>Aluminum on high-resistivity silicon | {cfg['device']['temperature_mK']} mK | {cfg['device']['band_min_GHz']}-{cfg['device']['band_max_GHz']} GHz target band</p>
<div class="status"><b>Fabrication HOLD.</b> This layout has no qualified Josephson junction mask.
Source: <b>{html.escape(p['source'])}</b>. Intrinsic coherence and readout loss are assumed inputs.
Synthetic examples are not validation against an experimental chip.</div>
<table>{table}</table><h2>Shared mask geometry</h2><img src="layout/layout.png" alt="Mask and qubit detail">
<h2>Conditional measurement predictions</h2><img src="experiment/measurements.png" alt="Readout and time-domain simulations">
<p><a href="parameters.json">Circuit and quantum parameters</a> · <a href="layout/device.gds">GDSII</a> ·
<a href="specification.json">Inverse electrical target</a> · <a href="run.json">Run provenance</a></p>
<small>The inverse target is separate from the forward geometry prediction. Meander end corrections,
substrate dispersion, kinetic inductance, interfaces, package and the real process require validation.</small></html>'''
    (out/"report.html").write_text(content)


def compare(parameters_path,reference_path,out):
    params = read_json(parameters_path)
    rows = []
    with Path(reference_path).open() as stream:
        for r in csv.DictReader(stream):
            name = r["parameter"]
            if name not in params:
                raise ValueError(f"Unknown benchmark parameter: {name}")
            measured,sigma = float(r["value"]),float(r["sigma"])
            if sigma <= 0 or not np.isfinite(sigma) or not np.isfinite(measured):
                raise ValueError("Benchmark requires finite values and positive uncertainty")
            # Parameter names encode units; reject a contradictory unit column.
            unit = name.rsplit("_",1)[-1]
            if r["unit"] != unit:
                raise ValueError(f"Benchmark unit mismatch for {name}")
            predicted = params[name]
            rows.append({"parameter":name,"unit":unit,"predicted":predicted,
                         "reference":measured,"sigma":sigma,"residual_sigma":(predicted-measured)/sigma})
    if not rows:
        raise ValueError("Empty benchmark")
    write_json(out,{"reference_file":str(reference_path),"reference_sha256":sha256(reference_path),
                    "reference_kind":r.get("kind","unspecified"),
                    "prediction_source":params["source"],"comparisons":rows,
                    "within_3sigma":all(abs(x["residual_sigma"])<=3 for x in rows),
                    "note":"Agreement is meaningful only for independent measured data and stated model error"})


def monte_carlo(cfg,out,samples=50,seed=123):
    import copy
    out = Path(out)
    out.mkdir(parents=True,exist_ok=True)
    rng,rows = np.random.default_rng(seed),[]
    for _ in range(samples):
        c = copy.deepcopy(cfg)
        c["circuit"]["EJ_GHz"] *= rng.normal(1,.05)
        c["layout"]["pad_width_um"] += rng.normal(0,1)
        c["layout"]["qubit_coupler_gap_um"] += rng.normal(0,.3)
        geom = geometry.build(c)
        p = circuit.parameters(c,circuit.surrogate(c,geom))
        rows.append([p["EJ_GHz"],p["f01_GHz"],p["anharmonicity_MHz"],p["g_MHz"],p["chi_exact_MHz"]])
    values = np.array(rows)
    write_csv(out/"monte_carlo.csv",dict(zip(
        ["EJ_GHz","f01_GHz","anharmonicity_MHz","g_MHz","chi_exact_MHz"],values.T)))
    write_json(out/"assumptions.json",{"source":"analytic_surrogate","samples":samples,"seed":seed,
                "independent_gaussian_sigma":{"EJ_relative":.05,"pad_width_um":1,"coupler_gap_um":.3},
                "note":"Illustrative process variability; distributions need measured calibration"})
