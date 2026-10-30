"""A05 security/interop tests. Skipped native checks are NOT native evidence."""
import copy
import json
import math
import shutil
import subprocess
from pathlib import Path

import pytest

from sqe_studio.adapters import josephson_adapter as ja
from sqe_studio.adapters.base import EngineBlocked


def make_case(kind="rf_linear"):
    schematic = {
        "nodes": ["0", "n1", "n2"],
        "elements": [
            {"id": "Ccouple", "kind": "C", "nodes": ["n1", "n2"], "value": 0.1e-12, "unit": "F"},
            {"id": "Lres", "kind": "L", "nodes": ["n2", "0"], "value": 1e-9, "unit": "H"},
        ],
        "ports": [{"number": 1, "node": "n1", "reference_impedance_ohm": 50.0}],
    }
    inputs = {"schematic_sha256": ja._hash(schematic), "frequencies_hz": [4.5e9, 5e9]}
    if kind == "rf_harmonic_balance":
        schematic["elements"].append({"id": "Ljtest", "kind": "Lj", "nodes": ["n2", "0"], "value": 1e-9, "unit": "H"})
        inputs["schematic_sha256"] = ja._hash(schematic)
        inputs["pump"] = {"frequency_hz": 4.75e9, "port": 1,
                          "current_a": 1e-9, "pump_harmonics": 2, "modulation_harmonics": 1}
    return {"id": "RF1", "kind": kind, "engine": "josephson_circuits", "inputs": inputs}, {"schematic": schematic}


def matched(case):
    study, project = case
    study["inputs"]["schematic_sha256"] = ja._hash(project["schematic"])
    return case


def test_valid_revision_mapped_to_fixed_worker():
    study, project = make_case()
    valid = ja._validate(study, project)
    wire = ja._wire(valid)
    assert wire.startswith("SQE_JOSEPHSON_WIRE_V1\nKIND\trf_linear\n")
    assert "P\t1\tn1\t50" in wire
    assert "E\tCcouple\tC\tn1\tn2" in wire
    assert "PUMP" not in wire
    assert "eval(" not in ja.FIXED_JULIA_WORKER
    assert "include(" not in ja.FIXED_JULIA_WORKER
    assert "using JosephsonCircuits" in ja.FIXED_JULIA_WORKER
    assert "hblinsolve" in ja.FIXED_JULIA_WORKER
    assert "hbsolve" in ja.FIXED_JULIA_WORKER


@pytest.mark.parametrize("mutator,reason", [
    (lambda s, p: p["schematic"]["nodes"].remove("0"), "ground"),
    (lambda s, p: p["schematic"]["nodes"].append("0"), "ground"),
    (lambda s, p: p["schematic"]["ports"].append(copy.deepcopy(p["schematic"]["ports"][0])), "Duplicate"),
    (lambda s, p: p["schematic"]["ports"].append({"number": 2, "node": "n1", "reference_impedance_ohm": 50}), "Duplicate"),
    (lambda s, p: p["schematic"]["ports"][0].update(reference_impedance_ohm=0), "impedance"),
    (lambda s, p: p["schematic"]["ports"][0].update(reference_impedance_ohm=-50), "impedance"),
    (lambda s, p: p["schematic"]["ports"][0].update(reference_impedance_ohm=float('nan')), "Invalid/nonfinite"),
    (lambda s, p: p["schematic"]["ports"][0].update(reference_impedance_ohm=True), "impedance"),
    (lambda s, p: p["schematic"]["elements"][0].update(nodes=["n1", "phantom"]), "nonexistent"),
    (lambda s, p: p["schematic"]["elements"][0].update(unit="pF"), "SI unit"),
    (lambda s, p: p["schematic"]["elements"][0].update(id="LjBad();run(`cmd`)"), "identifier"),
    (lambda s, p: p["schematic"]["elements"][0].update(kind="X"), "Only R"),
    (lambda s, p: p["schematic"]["elements"].append({"id": "Rspoof", "kind": "R", "nodes": ["n1", "0"], "value": 50, "unit": "ohm"}), "conflicts"),
    (lambda s, p: p["schematic"]["nodes"].append("unused"), "Unreferenced"),
    (lambda s, p: p["schematic"]["elements"][1].update(nodes=["n1", "n2"]), "floating"),
    (lambda s, p: s["inputs"].update(frequencies_hz=[4e9, 4e9]), "increasing"),
    (lambda s, p: s["inputs"].update(frequencies_hz=list(range(1_000_000, 1_000_066))), "1-64"),
    (lambda s, p: s["inputs"].update(julia_source="println(1)"), "exactly"),
])
def test_invalid_revision_netlist_blocked(mutator, reason):
    study, project = make_case()
    mutator(study, project)
    try:
        matched((study, project))
    except EngineBlocked as exc:
        assert reason in str(exc)
        return
    with pytest.raises(EngineBlocked, match=reason):
        ja._validate(study, project)


def test_forged_or_stale_schematic_reference():
    study, project = make_case()
    study["inputs"]["schematic_sha256"] = "0" * 64
    with pytest.raises(EngineBlocked, match="SHA-256 does not match"):
        ja._validate(study, project)
    study["inputs"]["schematic_sha256"] = "file:///tmp/user_netlist"
    with pytest.raises(EngineBlocked, match="arbitrary netlist references"):
        ja._validate(study, project)


def test_linear_rejects_pump_and_junction_study_requires_junction():
    study, project = make_case()
    study["inputs"]["pump"] = {"current_a": 1e-9}
    with pytest.raises(EngineBlocked, match="exactly"):
        ja._validate(study, project)
    study, project = make_case()
    study["kind"] = "rf_harmonic_balance"
    study["inputs"]["pump"] = {"frequency_hz": 4.75e9, "port": 1, "current_a": 1e-9,
                               "pump_harmonics": 2, "modulation_harmonics": 1}
    with pytest.raises(EngineBlocked, match="requires an Lj"):
        ja._validate(study, project)


@pytest.mark.parametrize("mutator,match", [
    (lambda p: p.update(port=2), "nonexistent"),
    (lambda p: p.update(pump_harmonics=10), "harmonics"),
    (lambda p: p.update(modulation_harmonics=0), "modulation_harmonics"),
    (lambda p: p.update(current_a=-1e-9), "Pump current"),
    (lambda p: p.update(other_pump={}), "exactly"),
])
def test_unsupported_pumps_blocked(mutator, match):
    study, project = make_case("rf_harmonic_balance")
    mutator(study["inputs"]["pump"])
    with pytest.raises(EngineBlocked, match=match):
        ja._validate(study, project)


def test_absent_julia_is_closed_with_no_generated_s_parameters(tmp_path, monkeypatch):
    study, project = make_case()
    monkeypatch.setattr(ja.shutil, "which", lambda _: None)
    with pytest.raises(EngineBlocked, match="Julia executable not found"):
        ja.run(study, project, tmp_path / "empty")
    assert not (tmp_path / "empty").exists()


def test_bad_input_is_rejected_before_julia_probe(tmp_path, monkeypatch):
    study, project = make_case()
    study["inputs"]["schematic_sha256"] = "0" * 64
    monkeypatch.setattr(ja.shutil, "which", lambda _: pytest.fail("Julia should not be probed"))
    with pytest.raises(EngineBlocked, match="SHA-256"):
        ja.run(study, project, tmp_path)


def test_failed_subprocess_no_scientific_artifacts_admitted(tmp_path, monkeypatch):
    """Simulated ERROR return; intentionally no fabricated Julia S values."""
    study, project = make_case()
    monkeypatch.setattr(ja.shutil, "which", lambda _: "/not/a/real/julia")
    def failed(*args, **kwargs):
        assert kwargs["shell"] is False and kwargs["timeout"] == ja.NATIVE_TIMEOUT_SECONDS
        assert "--startup-file=no" in args[0] and "--threads=1" in args[0]
        return subprocess.CompletedProcess(args[0], 3, b"", b"native package unavailable")
    monkeypatch.setattr(ja.subprocess, "run", failed)
    with pytest.raises(EngineBlocked, match=r"exit=3"):
        ja.run(study, project, tmp_path)
    assert (tmp_path / "josephson_native_stderr.log").read_bytes() == b"native package unavailable"
    assert not (tmp_path / "josephson_ports.json").exists()
    assert not (tmp_path / "josephson_native_sparameters.tsv").exists()


def test_nonzero_julia_timeout_fail_closed(tmp_path, monkeypatch):
    study, project = make_case()
    monkeypatch.setattr(ja.shutil, "which", lambda _: "/not/a/real/julia")
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], 140, output=b"initial stdout", stderr=b"timeout stderr")
    monkeypatch.setattr(ja.subprocess, "run", timeout)
    with pytest.raises(EngineBlocked, match="exceeded 140s"):
        ja.run(study, project, tmp_path)
    assert (tmp_path / "josephson_native_stderr.log").read_bytes() == b"timeout stderr"


def test_native_linear_smoke_when_installed(tmp_path):
    if shutil.which("julia") is None:
        pytest.skip("Native Julia unavailable: NOT a native linear smoke pass")
    study, project = make_case()
    result = ja.run(study, project, tmp_path)
    ports = json.loads((tmp_path / "josephson_ports.json").read_text())
    assert ports["port_order"] == [1]
    assert result["engine_version"] == ports["native_engine_version"]
    assert ports["native_elapsed_seconds"] >= 0
    assert (tmp_path / "josephson_native_sparameters.tsv").is_file()
    print("NATIVE LINEAR version=", result["engine_version"], "elapsed=", ports["native_elapsed_seconds"])


def test_native_harmonic_balance_smoke_when_installed(tmp_path):
    if shutil.which("julia") is None:
        pytest.skip("Native Julia unavailable: NOT a native harmonic balance smoke pass")
    study, project = make_case("rf_harmonic_balance")
    result = ja.run(study, project, tmp_path)
    ports = json.loads((tmp_path / "josephson_ports.json").read_text())
    assert ports["analysis"] == "rf_harmonic_balance"
    assert ports["convergence_evidence"] == "hbsolve_returned_no_iteration_log"
    print("NATIVE HB version=", result["engine_version"], "elapsed=", ports["native_elapsed_seconds"])
