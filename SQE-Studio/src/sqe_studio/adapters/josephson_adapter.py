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
using TOML
using SHA

# Require the installed package to be resolved from a concrete Julia manifest.
# A present Julia executable or a package merely on LOAD_PATH is not a pin.
# Do not log personal project paths: only the manifest digest and locked tree.
function native_lock_identity(ver)
    project_file = Base.active_project()
    project_file === nothing && error("Julia has no active Project.toml")
    manifest_file = joinpath(dirname(project_file), "Manifest.toml")
    isfile(manifest_file) || error("Julia active project has no Manifest.toml pin")
    document = TOML.parsefile(manifest_file)
    packages = get(document, "deps", nothing)
    packages isa AbstractDict || error("Unrecognized Julia manifest format")
    entries = get(packages, "JosephsonCircuits", nothing)
    entries isa Vector && length(entries) == 1 || error("Missing/ambiguous locked JosephsonCircuits")
    entry = only(entries)
    locked_version = get(entry, "version", "")
    tree = get(entry, "git-tree-sha1", "")
    locked_version == string(ver) || error("Resolved JosephsonCircuits version differs from manifest pin")
    occursin(r"^[0-9a-f]{40}$", tree) || error("Missing pinned JosephsonCircuits git tree")
    return bytes2hex(sha256(read(manifest_file))), tree
end

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
    manifest_sha256, josephson_tree_sha1 = native_lock_identity(ver)
    @info "Native Julia engine" julia_version=string(VERSION) josephson_version=string(ver) manifest_sha256=manifest_sha256
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
        println(io, "manifest_sha256\t", manifest_sha256)
        println(io, "josephson_tree_sha1\t", josephson_tree_sha1)
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
    # math.isfinite(huge_int) can itself overflow during implicit conversion.
    # All invalid user-supplied SI magnitudes must fail as a *blocked* model,
    # never as an uncaught Python exception or native execution attempt.
    if type(value) not in (float, int):
        raise EngineBlocked(f"{label} must be a finite number in [{lo}, {hi}]")
    try:
        finite_and_bounded = math.isfinite(value) and lo <= value <= hi
    except (OverflowError, ValueError):
        finite_and_bounded = False
    if not finite_and_bounded:
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
        # A native TSV is evidence, not a loose config file. In particular a
        # duplicate key must not silently replace a conflicting native version
        # or completion status (dict() otherwise keeps the last value).
        metadata = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            fields = line.split("\t")
            if len(fields) != 2 or not fields[0] or not fields[1] or fields[0] in metadata:
                raise ValueError("Malformed/duplicate native metadata field")
            metadata[fields[0]] = fields[1]
        required = {"schema", "julia_version", "josephson_version", "native_port_order",
                    "native_impedance_indices", "elapsed_seconds", "signal_mode",
                    "manifest_sha256", "josephson_tree_sha1",
                    "frequency_unit", "s_parameter_unit", "convergence_evidence"}
        if set(metadata) != required or metadata["schema"] != "sqe.josephson-native.v1":
            raise ValueError("Invalid native metadata schema")
        if not _VERSION.fullmatch(metadata["josephson_version"]) or not _VERSION.fullmatch(metadata["julia_version"]):
            raise ValueError("Missing or malformed Julia/native package version")
        if not re.fullmatch(r"[0-9a-f]{64}", metadata["manifest_sha256"]):
            raise ValueError("Missing/malformed Julia manifest SHA-256 pin")
        if not re.fullmatch(r"[0-9a-f]{40}", metadata["josephson_tree_sha1"]):
            raise ValueError("Missing/malformed JosephsonCircuits locked git tree")
        if list(map(int, metadata["native_port_order"].split(","))) != expected_ports:
            raise ValueError("Native port order mismatch")
        inds = list(map(int, metadata["native_impedance_indices"].split(",")))
        if len(inds) != len(expected_ports) or any(i < 1 for i in inds) or len(set(inds)) != len(inds):
            raise ValueError("Unresolved or aliased native reference impedances")
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


def _screen_passive_linear_s(path, freqs, ports):
    """Bounded *native* linear-port screen; not EM calibration or HB proof.

    No synthetic scattering is calculated: S is read from the already validated
    native TSV. Singular values check all simultaneous port excitations (unlike
    individual column-power checks), while reciprocity tests native power waves.
    """
    try:
        import numpy as np
        rows = path.read_text(encoding="utf-8").splitlines()[1:]
        n = len(ports)
        worst_singular, worst_reciprocity = 0.0, 0.0
        for k in range(len(freqs)):
            matrix = np.array([[complex(float(row[3]), float(row[4]))
                                for row in (rows[(k*n*n)+(i*n)+j].split("\t") for j in range(n))]
                               for i in range(n)], dtype=np.complex128)
            singular = float(np.linalg.svd(matrix, compute_uv=False)[0])
            reciprocity = float(np.max(np.abs(matrix - matrix.T)))
            if not math.isfinite(singular) or not math.isfinite(reciprocity):
                raise ValueError("Nonfinite native linear S diagnostics")
            worst_singular = max(worst_singular, singular)
            worst_reciprocity = max(worst_reciprocity, reciprocity)
        # Native positive R,L,C,Lj small-signal ports must be reciprocal and
        # passive under the declared real positive power-wave impedances.
        if worst_singular > 1.0001 or worst_reciprocity > 1e-4:
            raise ValueError("Native linear S violates passive/reciprocal port screen")
        return {"status": "bounded_linear_port_screen_passed",
                "max_singular_value": worst_singular,
                "max_reciprocity_difference": worst_reciprocity,
                "singular_value_limit": 1.0001,
                "reciprocity_absolute_limit": 1e-4,
                "scope": "native signal-band real-Z power waves; not EM calibration or independently converged physics"}
    except ImportError as exc:
        raise EngineBlocked("NumPy unavailable for required native RF passivity/reciprocity admission; "
                            "no native S admitted") from exc
    except (OSError, UnicodeError, ValueError, TypeError, IndexError,
            ArithmeticError) as exc:
        raise EngineFailure(f"Native linear RF physical screen rejected: {exc}") from exc


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
    # exists() is false for dangling symlinks: write_text would otherwise
    # follow them, potentially writing outside the native job directory.
    if any(p.exists() or p.is_symlink() for p in
           (request, script, native_s, native_meta, stdout, stderr,
            output / "josephson_ports.json")):
        raise EngineBlocked("Native output directory already has Josephson files; refusing overwrite/replay")
    # Atomic exclusive creation also closes the check-to-write symlink race for
    # these *Python-owned* artifacts (the native Julia outputs remain gated by
    # the job worker's result manifest and are never themselves admission).
    with request.open("x", encoding="ascii") as stream:
        stream.write(_wire(valid))
    with script.open("x", encoding="utf-8") as stream:
        stream.write(FIXED_JULIA_WORKER)
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
    if max(len(completed.stdout), len(completed.stderr)) > 4 * 1024 * 1024:
        # Avoid persisting unbounded logs into the EDA job workspace. The
        # complete subprocess output is never used as accepted numerical proof.
        raise EngineBlocked("Julia native log exceeds 4 MiB; no results admitted")
    with stdout.open("xb") as stream:
        stream.write(completed.stdout)
    with stderr.open("xb") as stream:
        stream.write(completed.stderr)
    if completed.returncode != 0:
        raise EngineBlocked(f"Julia/JosephsonCircuits failed (exit={completed.returncode}, elapsed={time.monotonic()-started:.3f}s); see native stderr/stdout; no results admitted")
    data = _parse_metadata(native_meta, [p[0] for p in valid[3]])
    _check_s(native_s, valid[1], [p[0] for p in valid[3]])
    if (valid[0] == "rf_linear") != (data["convergence_evidence"] == "linear_solve_returned"):
        raise EngineFailure("Wrong native study completion evidence")
    linear_screen = (_screen_passive_linear_s(native_s, valid[1], [p[0] for p in valid[3]])
                     if valid[0] == "rf_linear" else
                     {"status": "not_applicable_pumped_signal_only",
                      "scope": "HB returned no iteration residuals or idler channels; no nonlinear gain/passivity claim"})
    # This is a *port reference/evidence* sidecar, not a computed RF result.
    sidecar = {
        "schema": "sqe.josephson-port-contract.v1",
        "schematic_sha256": valid[5], "analysis": valid[0],
        "study_sha256": _hash(study), "project_sha256": _hash(project),
        "artifact_sha256": {
            name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in (
                ("josephson_request.tsv", request),
                ("josephson_fixed_worker.jl", script),
                ("josephson_native_sparameters.tsv", native_s),
                ("josephson_native_metadata.tsv", native_meta),
                ("josephson_native_stdout.log", stdout),
                ("josephson_native_stderr.log", stderr),
            )
        },
        "port_order": [p[0] for p in valid[3]],
        "ports": [{"number": n, "node": node, "reference_impedance_ohm": z0,
                   "positive_terminal": node, "negative_terminal": "0"} for n, node, z0 in valid[3]],
        "normalization": "JosephsonCircuits native P port with dedicated Rport shunt; Kurokawa-type native power-wave S (photon-flux amplitude convention), dimensionless complex ratio",
        "frequency_unit": "Hz", "native_frequency_input_unit": "rad/s",
        "frequency_points_hz": valid[1],
        "observable": {"quantity": "complex_scattering_amplitude", "unit": "1",
                       "representation": "real_and_imaginary", "wave_convention": "native_power_wave",
                       "port_reference_plane": "explicit_schematic_node_to_ground_0"},
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
        "native_version_pin": {"method": "active_julia_manifest_git_tree_sha1",
                               "manifest_sha256": data["manifest_sha256"],
                               "josephson_tree_sha1": data["josephson_tree_sha1"]},
        "native_linear_port_screen": linear_screen,
        "native_elapsed_seconds": float(data["elapsed_seconds"]),
        # This is the observed OS process completion, not an inferred HB
        # iteration convergence certificate. Logs are hashed above as native
        # provenance even when they are empty.
        "native_process_exit_code": completed.returncode,
        "native_process_wall_seconds": time.monotonic() - started,
        "convergence_evidence": data["convergence_evidence"],
        "scientific_status": "review_required",
        "cross_engine_mapping": {"status": "blocked", "reason":
            "No reviewed revision-bound EM-to-schematic port/geometry/junction mapping; "
            "native circuit outputs do not verify EM mode identity or EPR."},
        "limitations": ["Native return is not an independent RF benchmark or device qualification",
                        "No iteration-resolved nonlinear convergence evidence", "Pumped idler channels not exported",
                        "No EM mode/port or quantum Hamiltonian physical mapping certified"],
    }
    with (output / "josephson_ports.json").open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(sidecar, sort_keys=True, indent=2, allow_nan=False) + "\n")
    return {"engine_version": data["josephson_version"],
            "native_files": [request.name, script.name, native_s.name, native_meta.name,
                             stdout.name, stderr.name, "josephson_ports.json"],
            "kind": "josephson.sparameters", "scientific_status": "review_required"}


# RC14.10: production-native B05/B09 benchmark entrypoints. These create
# independent exploratory circuits, not simulated CPW EM or measured devices.
def _b05_b09_native_studies(case_id):
    if case_id not in ('B05', 'B09'):
        raise EngineBlocked('Only A16 B05/B09 native RF benchmarks are allowlisted')
    schematic = {
        'nodes': ['0', 'in', 'tank', 'out'],
        'elements': [
            {'id': 'Cin', 'kind': 'C', 'nodes': ['in', 'tank'], 'value': 1e-13, 'unit': 'F'},
            {'id': 'Cout', 'kind': 'C', 'nodes': ['tank', 'out'], 'value': 1e-13, 'unit': 'F'},
            {'id': 'Ltank', 'kind': 'L', 'nodes': ['tank', '0'], 'value': 1e-8, 'unit': 'H'},
            {'id': 'Rdamp', 'kind': 'R', 'nodes': ['tank', '0'], 'value': 500., 'unit': 'ohm'},
        ],
        'ports': [
            {'number': 1, 'node': 'in', 'reference_impedance_ohm': 50.},
            {'number': 2, 'node': 'out', 'reference_impedance_ohm': 75.},
        ],
    }
    if case_id == 'B09':
        schematic['elements'].append({'id': 'LjJPA', 'kind': 'Lj',
                                      'nodes': ['tank', '0'], 'value': 1e-9, 'unit': 'H'})
    points = [4.5e9, 4.75e9, 5e9, 5.25e9, 5.5e9]
    variants = [('pump_off', None)] if case_id == 'B05' else [
        ('pump_off', None), ('pump_harmonics_2', 2), ('pump_harmonics_3', 3)]
    for label, harmonic in variants:
        kind = 'rf_linear' if harmonic is None else 'rf_harmonic_balance'
        opts = {'schematic_sha256': _hash(schematic), 'frequencies_hz': points[:]}
        if harmonic is not None:
            opts['pump'] = {'frequency_hz': 4.75e9, 'port': 1, 'current_a': 1e-9,
                            'pump_harmonics': harmonic, 'modulation_harmonics': 1}
        yield label, {'id': 'A16-' + case_id + '-' + label,
                      'engine': 'josephson_circuits', 'kind': kind, 'inputs': opts}, {
                          'schematic': schematic}


def _benchmark_native_s21(path, frequencies):
    """Extract actual complex S21, after the native shape/order validator."""
    _check_s(path, frequencies, [1, 2])
    try:
        rows = path.read_text(encoding='utf-8').splitlines()[1:]
        values = [complex(float(rows[4 * idx + 2].split('\t')[3]),
                          float(rows[4 * idx + 2].split('\t')[4]))
                  for idx in range(len(frequencies))]
        if len(values) != len(frequencies) or not all(
                math.isfinite(v.real) and math.isfinite(v.imag) for v in values):
            raise ValueError('Nonfinite or absent native S21')
        return values
    except (ValueError, OSError, IndexError) as exc:
        raise EngineFailure('B05/B09 native S21 evidence rejected: ' + str(exc)) from exc



def _benchmark_rf_cross_job_identity(observed, case_id):
    """Require one actual native engine + pinned manifest for a cross-job case.

    A present version string alone is insufficient: all native subprocesses
    must report the same active Julia Manifest SHA and package tree identity.
    """
    if set(observed) != ({'pump_off'} if case_id == 'B05' else
                         {'pump_off', 'pump_harmonics_2', 'pump_harmonics_3'}):
        raise EngineFailure(case_id + ': required native subjobs missing')
    try:
        identities = {(item['engine_version'], item['julia_version'],
                       item['native_version_pin']['manifest_sha256'],
                       item['native_version_pin']['josephson_tree_sha1'],
                       item['schematic_sha256'], tuple(item['frequency_hz']))
                      for item in observed.values()}
    except (KeyError, TypeError) as exc:
        raise EngineFailure(case_id + ': native provenance incomplete') from exc
    if len(identities) != 1:
        raise EngineFailure(case_id + ': cross-job Julia/Manifest/circuit identity changed; comparison blocked')


def _benchmark_native_rf(case_id, output_dir):
    if not shutil.which('julia'):
        raise EngineBlocked(case_id + ': native Julia unavailable; no RF benchmark executed')
    output = Path(output_dir)
    if output.exists() or output.is_symlink():
        raise EngineBlocked(case_id + ': case directory already exists; refusing replay')
    output.mkdir(parents=True, exist_ok=False)
    observed = {}
    benchmark_started = time.monotonic()
    for label, study, project in _b05_b09_native_studies(case_id):
        job_started = time.monotonic()
        dest = output / label
        native = run(study, project, dest)
        side = json.loads((dest / 'josephson_ports.json').read_text(encoding='utf-8'))
        if (native['scientific_status'] != 'review_required' or
                side['cross_engine_mapping']['status'] != 'blocked' or
                side['native_process_exit_code'] != 0 or
                side['study_sha256'] != _hash(study) or
                side['schematic_sha256'] != _hash(project['schematic']) or
                side['analysis'] != study['kind'] or
                side['frequency_unit'] != 'Hz' or
                side['frequency_points_hz'] != study['inputs']['frequencies_hz'] or
                side['convergence_evidence'] != ('linear_solve_returned' if label == 'pump_off'
                                                 else 'hbsolve_returned_no_iteration_log') or
                not math.isfinite(side['native_elapsed_seconds']) or
                side['native_elapsed_seconds'] < 0 or
                not math.isfinite(side['native_process_wall_seconds']) or
                side['native_process_wall_seconds'] < 0 or
                side['port_order'] != [1, 2] or
                [p['reference_impedance_ohm'] for p in side['ports']] != [50., 75.]):
            raise EngineFailure(case_id + ': missing native port or process evidence')
        s21 = _benchmark_native_s21(dest / 'josephson_native_sparameters.tsv',
                                    study['inputs']['frequencies_hz'])
        observed[label] = {
            'study_wall_seconds': time.monotonic() - job_started,
            'native_solver_elapsed_seconds': side['native_elapsed_seconds'],
            'native_settings': side['native_settings'],
            'input_sha256': side['study_sha256'],
            'schematic_sha256': side['schematic_sha256'],
            'engine_version': side['native_engine_version'],
            'julia_version': side['native_julia_version'],
            'native_version_pin': side['native_version_pin'],
            'native_process_exit_code': side['native_process_exit_code'],
            'native_process_wall_seconds': side['native_process_wall_seconds'],
            'frequency_hz': study['inputs']['frequencies_hz'],
            's21_real_imag': [[z.real, z.imag] for z in s21],
            'port_normalization': side['normalization'],
            'linear_passivity_screen': side['native_linear_port_screen'],
            'native_completion_evidence': side['convergence_evidence'],
            'raw_artifact_sha256': side['artifact_sha256'],
            'native_sidecar_sha256': hashlib.sha256((dest / 'josephson_ports.json').read_bytes()).hexdigest(),
            'pump': side['pump'],
        }
    _benchmark_rf_cross_job_identity(observed, case_id)
    if case_id == 'B09':
        # A signal-only amplitude ratio is an *observation*, not pump gain,
        # noise, idler stability, or HB iteration convergence. Avoid division
        # by zero, and never silently skip a missing reference frequency.
        baseline = [complex(*z) for z in observed['pump_off']['s21_real_imag']]
        for label in ('pump_harmonics_2', 'pump_harmonics_3'):
            signal = [complex(*z) for z in observed[label]['s21_real_imag']]
            observed[label]['signal_only_amplitude_ratio_to_pump_off'] = [
                (abs(a)/abs(b) if abs(b) > 1e-12 else None)
                for a, b in zip(signal, baseline)]
            observed[label]['hb_residual_status'] = 'BLOCKED_NOT_EXPORTED_BY_NATIVE_WORKER'
        # A difference between finite signal-only native S21 amplitudes is
        # recorded, NEVER treated as a complete harmonic-balance residual.
        harmonic_2 = [complex(*z) for z in observed['pump_harmonics_2']['s21_real_imag']]
        harmonic_3 = [complex(*z) for z in observed['pump_harmonics_3']['s21_real_imag']]
        signal_only_harmonic_delta = max(abs(x - y) for x, y in zip(harmonic_2, harmonic_3))
        stage_status = 'BLOCKED_NO_HB_RESIDUAL_OR_IDLER_REFERENCE'
    else:
        stage_status = 'BLOCKED_NO_PALACE_EM_DRIVEN_COMPARISON'
    report = {
        'schema': 'sqe.A16.native-benchmark.v1', 'case_id': case_id,
        'execution_kind': 'NATIVE_JOSEPHSON_CIRCUIT', 'stage_status': stage_status,
        'studies': observed, 'signal_and_frequency_units': {'S': '1', 'frequency': 'Hz'},
        'harmonic_2_vs_3_signal_only_complex_S21_max_delta': (
            signal_only_harmonic_delta if case_id == 'B09' else None),
        'harmonic_delta_qualification': 'BLOCKED_NOT_AN_HB_RESIDUAL_OR_IDLER_CONVERGENCE',
        'execution_resources': {
            'native_jobs_completed': len(observed), 'native_jobs_sequential': True,
            'total_wall_seconds': time.monotonic() - benchmark_started,
            'per_julia_process_timeout_seconds': NATIVE_TIMEOUT_SECONDS,
            'julia_threads': 1, 'blas_threads': 1, 'native_nbatches': 1,
            'native_frequency_points_per_study': 5,
            'max_native_hb_iterations': 80 if case_id == 'B09' else None,
            'peak_memory_bytes': None, 'peak_memory_status': 'NOT_MEASURED',
        },
        'limitations': ['independent lumped circuit, not Palace CPW, EM port calibrated, or measured device',
                        'no idler/noise or native HB iteration residual exported',
                        'no independent JPA model convergence or fabrication approval', 'fabrication HOLD'],
    }
    with (output / ('benchmark_' + case_id + '.json')).open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + '\n')
    return report


def benchmark_b05(output_dir):
    """Run native reference-impedance RF screen; B05 Palace/EM gate stays BLOCKED."""
    return _benchmark_native_rf('B05', output_dir)


def benchmark_b09(output_dir):
    """Run native pump-off and two-harmonic HB sweep; residual gate BLOCKED."""
    return _benchmark_native_rf('B09', output_dir)
