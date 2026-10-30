"""Bounded JosephsonCircuits.jl bridge for revision-bound declarative netlists.

No Python RF equations, Julia expressions from project data, dynamic imports, or
substitute results. The complete Julia entrypoint below is an immutable literal.
See docs/agents/A05.md for the deliberately narrow, versioned input convention.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import time

from .base import EngineBlocked, EngineFailure, safe_output

MAX_FREQUENCIES = 64
MAX_NODES = 24
MAX_ELEMENTS = 48
MAX_PORTS = 4
NATIVE_TIMEOUT_SECONDS = 140  # Parent worker's hard deadline is 180s.
_ID = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,31}\Z", re.ASCII)
_VERSION = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9.]+)?\Z")
_UNITS = {"R": "ohm", "L": "H", "C": "F", "Lj": "H"}
_LIMITS = {"R": (1e-4, 1e9), "L": (1e-15, 1e2), "C": (1e-19, 1.0), "Lj": (1e-15, 1e2)}

# The only Julia code that may run. Data are plain tab-delimited, validated
# identifiers and bounded SI numbers. Julia never evals or includes data.
FIXED_JULIA_WORKER = r'''# SQE Studio A05 fixed JosephsonCircuits.jl entrypoint. Never run user code.
using JosephsonCircuits
using Printf

function load_request(path)
    rows = readlines(path)
    isempty(rows) && error("Missing SQE request")
    rows[1] == "SQE_JOSEPHSON_WIRE_V1" || error("Unsupported SQE request version")
    kind = ""
    frequencies = Float64[]
    elements = Tuple{String,String,String,Float64}[]
    ports = Tuple{Int,String,Float64}[]
    pump = nothing
    for line in rows[2:end]
        parts = split(line, '\t')
        if parts[1] == "KIND" && length(parts) == 2
            isempty(kind) || error("Duplicate kind")
            kind = parts[2]
        elseif parts[1] == "F" && length(parts) == 2
            push!(frequencies, parse(Float64, parts[2]))
        elseif parts[1] == "E" && length(parts) == 6
            parts[3] in ("R", "L", "C", "Lj") || error("Unexpected component type")
            push!(elements, (parts[2], parts[4], parts[5], parse(Float64, parts[6])))
        elseif parts[1] == "P" && length(parts) == 4
            push!(ports, (parse(Int, parts[2]), parts[3], parse(Float64, parts[4])))
        elseif parts[1] == "PUMP" && length(parts) == 6
            pump === nothing || error("Multiple pumps not allowed")
            pump = (parse(Float64, parts[2]), parse(Int, parts[3]),
                    parse(Float64, parts[4]), parse(Int, parts[5]), parse(Int, parts[6]))
        else
            error("Malformed fixed SQE request")
        end
    end
    kind in ("rf_linear", "rf_harmonic_balance") || error("Invalid study kind")
    length(frequencies) in 1:64 || error("Frequency budget exceeded")
    length(ports) in 1:4 || error("Port budget exceeded")
    all(isfinite, frequencies) || error("Nonfinite native frequency")
    sort!(ports, by=first)
    [p[1] for p in ports] == collect(1:length(ports)) || error("Noncontiguous ports")
    (kind == "rf_linear") == (pump === nothing) || error("Pump/kind mismatch")
    return kind, frequencies, elements, ports, pump
end

function main()
    length(ARGS) == 3 || error("Fixed worker expects input and two output filenames")
    kind, frequencies, elements, ports, pump = load_request(ARGS[1])
    ver = Base.pkgversion(JosephsonCircuits)
    ver === nothing && error("Cannot obtain JosephsonCircuits.jl version")
    @info "Native Julia engine" julia_version=string(VERSION) josephson_version=string(ver)
    circuit = Tuple{String,String,String,Union{Float64,Int}}[]
    # Each native P has exactly one reserved matching shunt R; this is how
    # JosephsonCircuits discovers real reference port impedances.
    for (number, node, z0) in ports
        push!(circuit, ("P$(number)", node, "0", number))
        push!(circuit, ("Rport$(number)", node, "0", z0))
    end
    for (name, a, b, value) in elements
        push!(circuit, (name, a, b, value))
    end
    defs = Dict{Symbol,Float64}()
    ws = 2pi .* frequencies
    t0 = time()
    if kind == "rf_linear"
        lin = JosephsonCircuits.hblinsolve(ws, circuit, defs;
            sorting=:none, nbatches=1, Nmodulationharmonics=(0,),
            returnS=true, returnSnoise=false, returnQE=false, returnCM=false)
    else
        pf, pp, current, nh, nm = pump
        @info "Native harmonic balance" pump_frequency_hz=pf pump_port=pp pump_current_a=current pump_harmonics=nh modulation_harmonics=nm iterations=80 ftol=1e-8
        sol = JosephsonCircuits.hbsolve(ws, (2pi * pf,),
            [(mode=(1,), port=pp, current=current)], (nm,), (nh,),
            circuit, defs; dc=false, threewavemixing=false,
            fourwavemixing=true, iterations=80, ftol=1e-8,
            nbatches=1, sorting=:none, returnS=true,
            returnSnoise=false, returnQE=false, returnCM=false)
        lin = sol.linearized
        # The native solver raises on iteration exhaustion. No explicit
        # residual or convergence history is claimed by this worker.
        @info "Native hbsolve returned (iteration-level convergence not available)"
    end
    elapsed = time() - t0
    numbers = collect(Int.(lin.portnumbers))
    numbers == [p[1] for p in ports] || error("Native port order does not match explicit port contract")
    length(lin.portimpedanceindices) == length(ports) || error("Native port impedances unresolved")
    # Keep untouched native complex S data, with no dB/power conversion.
    # For pumped circuits this file is ONLY (0,)->(0,) signal scattering;
    # idler-to-signal / signal-to-idler conversions are intentionally omitted.
    open(ARGS[2], "w") do io
        println(io, "frequency_hz\toutput_port\tinput_port\treal\timag")
        for (k, f) in enumerate(frequencies), po in numbers, pi in numbers
            z = lin.S((0,), po, (0,), pi, k)
            isfinite(real(z)) && isfinite(imag(z)) || error("Nonfinite native S parameter")
            @printf(io, "%.17g\t%d\t%d\t%.17g\t%.17g\n", f, po, pi, real(z), imag(z))
        end
    end
    open(ARGS[3], "w") do io
        println(io, "schema\tsqe.josephson-native.v1")
        println(io, "julia_version\t", VERSION)
        println(io, "josephson_version\t", ver)
        println(io, "native_port_order\t", join(numbers, ","))
        println(io, "native_impedance_indices\t", join(lin.portimpedanceindices, ","))
        println(io, "elapsed_seconds\t", @sprintf("%.9g", elapsed))
        println(io, "signal_mode\t0")
        println(io, "frequency_unit\tHz")
        println(io, "s_parameter_unit\tdimensionless_complex_native_power_wave")
        println(io, "convergence_evidence\t", kind == "rf_linear" ? "linear_solve_returned" : "hbsolve_returned_no_iteration_log")
    end
end

main()
'''


def _hash(obj):
    try:
        payload = json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (ValueError, TypeError) as exc:
        raise EngineBlocked("Invalid/nonfinite revision schematic") from exc
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _exact_dict(value, keys, label):
    if type(value) is not dict or set(value) != set(keys):
        raise EngineBlocked(f"{label} must have exactly {', '.join(sorted(keys))}")
    return value


def _positive(value, lo, hi, label):
    if type(value) not in (float, int) or not math.isfinite(value) or not lo <= value <= hi:
        raise EngineBlocked(f"{label} must be a finite number in [{lo}, {hi}]")
    return float(value)


def _identifier(value, label):
    if type(value) is not str or not _ID.fullmatch(value):
        raise EngineBlocked(f"{label}: expected simple ASCII identifier")
    return value


def _validate(study, project):
    if type(study) is not dict or type(project) is not dict:
        raise EngineBlocked("Missing saved revision/project snapshot")
    if study.get("engine") != "josephson_circuits":
        raise EngineBlocked("Study is not routed to JosephsonCircuits")
    kind = study.get("kind")
    if kind not in ("rf_linear", "rf_harmonic_balance"):
        raise EngineBlocked("JosephsonCircuits requires rf_linear or bounded rf_harmonic_balance study kind")
    opts = _exact_dict(study.get("inputs"),
                       {"schematic_sha256", "frequencies_hz"} | ({"pump"} if kind == "rf_harmonic_balance" else set()),
                       "Study inputs")
    sch = _exact_dict(project.get("schematic"), {"nodes", "elements", "ports"}, "Revision schematic")
    if type(opts["schematic_sha256"]) is not str or not re.fullmatch(r"[0-9a-f]{64}", opts["schematic_sha256"]):
        raise EngineBlocked("Require exact saved schematic SHA-256; arbitrary netlist references forbidden")
    if _hash(sch) != opts["schematic_sha256"]:
        raise EngineBlocked("Schematic SHA-256 does not match immutable revision; refusing stale/fake reference")
    nodes = sch["nodes"]
    if type(nodes) is not list or not 2 <= len(nodes) <= MAX_NODES or any(type(n) is not str for n in nodes):
        raise EngineBlocked("Schematic requires 2-24 named nodes including ground 0")
    if nodes.count("0") != 1:
        raise EngineBlocked("Missing or duplicated explicit ground node '0'")
    if len(set(nodes)) != len(nodes) or any(not _ID.fullmatch(n) for n in nodes if n != "0"):
        raise EngineBlocked("Duplicate or unsafe schematic node")
    elems, ports = sch["elements"], sch["ports"]
    if type(elems) is not list or not 1 <= len(elems) <= MAX_ELEMENTS:
        raise EngineBlocked("Schematic must have 1-48 supported R/L/C/Lj elements")
    if type(ports) is not list or not 1 <= len(ports) <= MAX_PORTS:
        raise EngineBlocked("Schematic must declare 1-4 ports")
    names, used = set(), {"0"}
    clean_elems = []
    for e in elems:
        _exact_dict(e, {"id", "kind", "nodes", "value", "unit"}, "Circuit element")
        kind_e = e["kind"]
        if type(kind_e) is not str or kind_e not in _UNITS:
            raise EngineBlocked("Only R, L, C and Lj elements are supported")
        name = _identifier(e["id"], "Element id")
        if not name.startswith(kind_e) or not re.fullmatch(re.escape(kind_e) + r"[A-Za-z0-9_]+", name):
            raise EngineBlocked("Element id must have native kind prefix and a nonempty suffix")
        if name in names or name.startswith("Rport") or name.startswith("P"):
            raise EngineBlocked("Duplicate element or reserved native port identifier")
        names.add(name)
        nn = e["nodes"]
        if type(nn) is not list or len(nn) != 2 or any(type(n) is not str or n not in nodes for n in nn):
            raise EngineBlocked("Element references a nonexistent schematic node")
        if nn[0] == nn[1]:
            raise EngineBlocked("Self-connected circuit element is unsupported")
        if e["unit"] != _UNITS[kind_e]:
            raise EngineBlocked(f"{name} requires SI unit {_UNITS[kind_e]}")
        value = _positive(e["value"], *_LIMITS[kind_e], f"{name} value")
        used.update(nn)
        clean_elems.append((kind_e, name, nn[0], nn[1], value))
    if set(nodes) != used:
        raise EngineBlocked("Unreferenced schematic node")
    clean_ports, port_nodes = [], set()
    numbers = set()
    for p in ports:
        _exact_dict(p, {"number", "node", "reference_impedance_ohm"}, "RF port")
        num, node = p["number"], p["node"]
        if type(num) is not int or num < 1 or num > MAX_PORTS or num in numbers:
            raise EngineBlocked("Duplicate/nonpositive/out-of-range RF port number")
        if type(node) is not str or node not in nodes or node == "0" or node in port_nodes:
            raise EngineBlocked("Duplicate/unmapped RF port node or invalid ground port")
        numbers.add(num); port_nodes.add(node)
        z0 = _positive(p["reference_impedance_ohm"], 1.0, 1e4, "RF reference impedance (ohm)")
        clean_ports.append((num, node, z0))
    clean_ports.sort()
    if [p[0] for p in clean_ports] != list(range(1, len(clean_ports) + 1)):
        raise EngineBlocked("RF ports must be consecutively numbered 1..N")
    # JosephsonCircuits locates port reference impedance by matching a shunt
    # resistor across the port's two terminals. Another R there is ambiguous.
    for kind_e, name, a, b, _ in clean_elems:
        if kind_e == "R" and ((a == "0" and b in port_nodes) or (b == "0" and a in port_nodes)):
            raise EngineBlocked(f"{name}: R across a port conflicts with native reference impedance")
    # All port nodes must be connected through real circuit elements to ground;
    # added reference shunts alone must never legitimize a floating circuit.
    reachable = {"0"}
    while True:
        next_nodes = reachable | {b for _, _, a, b, _ in clean_elems if a in reachable} | {a for _, _, a, b, _ in clean_elems if b in reachable}
        if next_nodes == reachable:
            break
        reachable = next_nodes
    if set(nodes) != reachable:
        raise EngineBlocked("Disconnected/floating circuit topology; port shunts do not establish topology")
    freqs = opts["frequencies_hz"]
    if type(freqs) is not list or not 1 <= len(freqs) <= MAX_FREQUENCIES:
        raise EngineBlocked("Frequency sweep must have 1-64 explicit points")
    clean_freqs = [_positive(f, 1e3, 1e12, "Signal frequency (Hz)") for f in freqs]
    if any(b <= a for a, b in zip(clean_freqs, clean_freqs[1:])):
        raise EngineBlocked("Frequencies must be strictly increasing (Hz)")
    pump = None
    if kind == "rf_harmonic_balance":
        if not any(e[0] == "Lj" for e in clean_elems):
            raise EngineBlocked("Native Josephson harmonic balance requires an Lj junction")
        p = _exact_dict(opts["pump"], {"frequency_hz", "port", "current_a", "pump_harmonics", "modulation_harmonics"}, "Single-tone pump")
        pf = _positive(p["frequency_hz"], 1e6, 1e11, "Pump frequency (Hz)")
        cur = _positive(p["current_a"], 1e-15, 1e-4, "Pump current (A)")
        pn, nh, nm = p["port"], p["pump_harmonics"], p["modulation_harmonics"]
        if type(pn) is not int or pn not in numbers:
            raise EngineBlocked("Pump references a nonexistent RF port")
        if type(nh) is not int or not 1 <= nh <= 4 or type(nm) is not int or not 0 <= nm <= 2:
            raise EngineBlocked("Bound single-tone pump harmonics to 1-4 and modulation harmonics to 0-2")
        if nm == 0:
            raise EngineBlocked("Pumped linearization requires modulation_harmonics >= 1")
        pump = (pf, pn, cur, nh, nm)
    return kind, clean_freqs, clean_elems, clean_ports, pump, opts["schematic_sha256"]


def _wire(valid):
    kind, freqs, elems, ports, pump, _ = valid
    rows = ["SQE_JOSEPHSON_WIRE_V1", f"KIND\t{kind}"]
    rows += [f"F\t{f:.17g}" for f in freqs]
    rows += [f"E\t{name}\t{typ}\t{a}\t{b}\t{val:.17g}" for typ, name, a, b, val in elems]
    rows += [f"P\t{n}\t{node}\t{z0:.17g}" for n, node, z0 in ports]
    if pump is not None:
        pf, pn, cur, nh, nm = pump
        rows.append(f"PUMP\t{pf:.17g}\t{pn}\t{cur:.17g}\t{nh}\t{nm}")
    return "\n".join(rows) + "\n"


def _parse_metadata(path, expected_ports):
    try:
        metadata = dict(line.split("\t", 1) for line in path.read_text(encoding="utf-8").splitlines())
        required = {"schema", "julia_version", "josephson_version", "native_port_order",
                    "native_impedance_indices", "elapsed_seconds", "signal_mode",
                    "frequency_unit", "s_parameter_unit", "convergence_evidence"}
        if set(metadata) != required or metadata["schema"] != "sqe.josephson-native.v1":
            raise ValueError("Invalid native metadata schema")
        if not _VERSION.fullmatch(metadata["josephson_version"]):
            raise ValueError("Missing native package version")
        if list(map(int, metadata["native_port_order"].split(","))) != expected_ports:
            raise ValueError("Native port order mismatch")
        inds = list(map(int, metadata["native_impedance_indices"].split(",")))
        if len(inds) != len(expected_ports) or any(i < 1 for i in inds):
            raise ValueError("Unresolved native reference impedances")
        if not math.isfinite(float(metadata["elapsed_seconds"])) or float(metadata["elapsed_seconds"]) < 0:
            raise ValueError("Invalid native runtime")
        if metadata["signal_mode"] != "0" or metadata["frequency_unit"] != "Hz" or metadata["s_parameter_unit"] != "dimensionless_complex_native_power_wave":
            raise ValueError("Unexpected native port normalization")
        if metadata["convergence_evidence"] not in ("linear_solve_returned", "hbsolve_returned_no_iteration_log"):
            raise ValueError("Unknown native solver completion status")
    except (ValueError, OSError, UnicodeError) as exc:
        raise EngineFailure(f"Native JosephsonCircuits metadata rejected: {exc}") from exc
    return metadata


def _check_s(path, freqs, ports):
    """Only verify native rows/metadata, never derive or transform S values."""
    expected = [(f, po, pi) for f in freqs for po in ports for pi in ports]
    try:
        with path.open("r", encoding="utf-8") as f:
            if f.readline().rstrip("\n") != "frequency_hz\toutput_port\tinput_port\treal\timag":
                raise ValueError("Native S header mismatch")
            count = 0
            for line in f:
                if count >= len(expected):
                    raise ValueError("Extra native S rows")
                pieces = line.rstrip("\n").split("\t")
                if len(pieces) != 5:
                    raise ValueError("Malformed native S row")
                freq, po, pi, real, imag = float(pieces[0]), int(pieces[1]), int(pieces[2]), float(pieces[3]), float(pieces[4])
                ef, ep, ei = expected[count]
                if freq != ef or (po, pi) != (ep, ei) or not all(map(math.isfinite, (real, imag))):
                    raise ValueError("Native S row ordering, frequency or finiteness mismatch")
                count += 1
            if count != len(expected):
                raise ValueError("Missing native S rows")
    except (OSError, UnicodeError, ValueError) as exc:
        raise EngineFailure(f"Native JosephsonCircuits S-parameter artifact rejected: {exc}") from exc


def run(study, project, output_dir):
    valid = _validate(study, project)  # Reject invalid input BEFORE looking for Julia.
    binary = shutil.which("julia")
    if not binary:
        raise EngineBlocked("Julia executable not found on PATH; JosephsonCircuits.jl not invoked; no RF data generated")
    output = safe_output(output_dir)
    request = output / "josephson_request.tsv"
    script = output / "josephson_fixed_worker.jl"
    native_s = output / "josephson_native_sparameters.tsv"
    native_meta = output / "josephson_native_metadata.tsv"
    stdout = output / "josephson_native_stdout.log"
    stderr = output / "josephson_native_stderr.log"
    if any(p.exists() for p in (request, script, native_s, native_meta, stdout, stderr)):
        raise EngineBlocked("Native output directory already has Josephson files; refusing overwrite/replay")
    request.write_text(_wire(valid), encoding="ascii")
    script.write_text(FIXED_JULIA_WORKER, encoding="utf-8")
    env = os.environ.copy()
    env.update(JULIA_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1", JULIA_PKG_PRECOMPILE_AUTO="0")
    started = time.monotonic()
    try:
        completed = subprocess.run(
            [binary, "--startup-file=no", "--history-file=no", "--threads=1",
             str(script), str(request), str(native_s), str(native_meta)],
            cwd=str(output), env=env, shell=False, capture_output=True,
            timeout=NATIVE_TIMEOUT_SECONDS, check=False,
        )
    except subprocess.TimeoutExpired as exc:
        stdout.write_bytes(exc.stdout or b"")
        stderr.write_bytes(exc.stderr or b"")
        raise EngineBlocked(f"Julia execution exceeded {NATIVE_TIMEOUT_SECONDS}s; no native result admitted") from exc
    except OSError as exc:
        raise EngineBlocked(f"Julia process could not start: {exc}") from exc
    stdout.write_bytes(completed.stdout)
    stderr.write_bytes(completed.stderr)
    if max(len(completed.stdout), len(completed.stderr)) > 4 * 1024 * 1024:
        raise EngineBlocked("Julia native log exceeds 4 MiB; no results admitted")
    if completed.returncode != 0:
        raise EngineBlocked(f"Julia/JosephsonCircuits failed (exit={completed.returncode}, elapsed={time.monotonic()-started:.3f}s); see native stderr/stdout; no results admitted")
    data = _parse_metadata(native_meta, [p[0] for p in valid[3]])
    _check_s(native_s, valid[1], [p[0] for p in valid[3]])
    if (valid[0] == "rf_linear") != (data["convergence_evidence"] == "linear_solve_returned"):
        raise EngineFailure("Wrong native study completion evidence")
    # This is a *port reference/evidence* sidecar, not a computed RF result.
    sidecar = {
        "schema": "sqe.josephson-port-contract.v1",
        "schematic_sha256": valid[5], "analysis": valid[0],
        "port_order": [p[0] for p in valid[3]],
        "ports": [{"number": n, "node": node, "reference_impedance_ohm": z0,
                   "positive_terminal": node, "negative_terminal": "0"} for n, node, z0 in valid[3]],
        "normalization": "JosephsonCircuits native P port with dedicated Rport shunt; Kurokawa-type native power-wave S (photon-flux amplitude convention), dimensionless complex ratio",
        "frequency_unit": "Hz", "native_frequency_input_unit": "rad/s",
        "s_parameter_order": "frequency-major, output_port-major, input_port-minor",
        "mode": "(0,)->(0,) signal-only; nonlinear idler S not exported",
        "native_settings": {
            "threads": 1, "nbatches": 1, "signal_frequencies_unit": "Hz",
            "native_angular_frequency_unit": "rad/s", "sorting": "none",
            "linear_modulation_harmonics": [0] if valid[0] == "rf_linear" else None,
            "dc": False if valid[0] != "rf_linear" else None,
            "three_wave_mixing": False if valid[0] != "rf_linear" else None,
            "four_wave_mixing": True if valid[0] != "rf_linear" else None,
            "max_iterations": 80 if valid[0] != "rf_linear" else None,
            "ftol": 1e-8 if valid[0] != "rf_linear" else None,
        },
        "pump": None if valid[4] is None else dict(zip(
            ("frequency_hz", "port", "current_a", "pump_harmonics", "modulation_harmonics"), valid[4])),
        "native_engine_version": data["josephson_version"], "native_julia_version": data["julia_version"],
        "native_elapsed_seconds": float(data["elapsed_seconds"]),
        "convergence_evidence": data["convergence_evidence"],
        "scientific_status": "review_required",
        "limitations": ["No independent scientific benchmark or Windows runtime execution verified by A05",
                        "No iteration-resolved nonlinear convergence evidence", "Pumped idler channels not exported"],
    }
    (output / "josephson_ports.json").write_text(json.dumps(sidecar, sort_keys=True, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return {"engine_version": data["josephson_version"],
            "native_files": [request.name, script.name, native_s.name, native_meta.name,
                             stdout.name, stderr.name, "josephson_ports.json"],
            "kind": "josephson.sparameters", "scientific_status": "review_required"}
