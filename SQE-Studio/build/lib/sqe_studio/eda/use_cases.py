"""Published-method design cases for the ordinary SQE Studio project workflow.

The catalog is curated code, not executable user-supplied metadata.
Any ``starter_template`` is a normal sqe.project.v1 design; a planned case
MUST have no template until the generic path is genuinely supported.
All reference URLs are non-executable, reviewed literals.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

from ..contracts import STEP_IDS

Readiness = Literal["editable_native_conditional", "blocked_missing_edge"]


@dataclass(frozen=True)
class DesignCase:
    id: str
    title: str
    family: str
    purpose: str
    reference_title: str
    reference_url: str
    starter_template: str | None
    readiness: Readiness
    science_boundary: str
    steps: tuple[str, ...]
    acceptance: tuple[str, ...]
    next_missing_edge: str | None


_CASES = (
    DesignCase(
        id="cpw_resonator_eigenmode", title="Quarter-wave CPW resonator: EM eigenmodes",
        family="resonator",
        purpose="Tune CPW routing and compare native eigenfrequencies under mesh refinement.",
        reference_title="SQDMetal: Basic Eigenmode Simulation of Side-coupled Resonator",
        reference_url="https://sqdlab.github.io/SQDMetal/examples/Palace_Eigenmode_Res_Gmsh.html",
        starter_template="cpw_resonator_v1", readiness="editable_native_conditional",
        science_boundary="Adapted geometry only; native solver, port, material, mode identity and convergence review required.",
        steps=("intent", "layout", "em", "results"),
        acceptance=("Review actual QGeometry, chip boundary, metal layers and port mapping.",
                    "Run Palace eigenmodes with documented mesh refinements on the same saved design.",
                    "Match physical modes by fields before quoting frequency differences or convergence."),
        next_missing_edge=None,
    ),
    DesignCase(
        id="transmon_independent_spectrum", title="Transmon: independently specified quantum spectrum",
        family="transmon",
        purpose="Adjust EJ/EC and inspect the native scqubits spectrum and charge-basis convergence.",
        reference_title="Krantz et al., A quantum engineer's guide to superconducting qubits (2019)",
        reference_url="https://doi.org/10.1063/1.5089550",
        starter_template="transmon_spectrum_v1", readiness="editable_native_conditional",
        science_boundary="EJ/EC are manually declared model parameters, NOT extracted from CAD or EM.",
        steps=("intent", "quantum", "results"),
        acceptance=("Record EJ and EC as E/h in GHz and charge offset in 2e.",
                    "Check scqubits charge-basis cutoff convergence before interpreting frequencies.",
                    "Report f01 as E1-E0, not an absolute eigenenergy or a measured transmon."),
        next_missing_edge=None,
    ),
    DesignCase(
        id="fluxonium_flux_sweep", title="Fluxonium: quantum spectrum versus external flux",
        family="fluxonium",
        purpose="Study a bounded flux sweep with explicit EJ/EC/EL and native scqubits.",
        reference_title="scqubits: Fluxonium and parameter-sweep documentation",
        reference_url="https://scqubits.readthedocs.io/en/latest/guide/qubits/fluxonium.html",
        starter_template="fluxonium_spectrum_v1", readiness="editable_native_conditional",
        science_boundary="Independent Hamiltonian parameters; no fabrication or EM extraction asserted.",
        steps=("intent", "quantum", "results"),
        acceptance=("Review flux normalization to Phi0 and all energy units in GHz.",
                    "Check Hilbert-basis truncation and stability of transitions.",
                    "Treat avoided crossings as physics requiring expert mode identification."),
        next_missing_edge=None,
    ),
    DesignCase(
        id="kinetic_inductance_cpw", title="Thin-film resonator: kinetic-inductance sensitivity",
        family="resonator",
        purpose="Compare reviewed PEC and sheet-impedance EM models on the same CPW geometry.",
        reference_title="Palace: Impedance boundary conditions and Crack model",
        reference_url="https://awslabs.github.io/palace/dev/guide/boundaries/",
        starter_template=None, readiness="blocked_missing_edge",
        science_boundary="General revision-bound sheet model is NOT exposed in the GUI/native adapter.",
        steps=("layout", "em", "results"),
        acceptance=("Require film thickness, penetration depth, frequency and verified Gmsh physical surfaces.",
                    "Distinguish Crack=true versus Crack=false by documented physical regime.",
                    "Compare converged native eigenmodes; never infer validated material properties from a guessed Ls."),
        next_missing_edge="Reviewed general sheet-material -> Palace deck and result provenance edge",
    ),
    DesignCase(
        id="epr_transmon_resonator", title="Resonator-coupled transmon: EM-to-Hamiltonian",
        family="multi_qubit",
        purpose="Extract verified mode and junction participation before quantization and scqubits comparison.",
        reference_title="Minev et al., Energy-participation quantization of Josephson circuits (2021)",
        reference_url="https://doi.org/10.1038/s41534-021-00461-8",
        starter_template=None, readiness="blocked_missing_edge",
        science_boundary="Raw EM/EPR evidence is not a verified Hamiltonian or mode mapping.",
        steps=("schematic", "layout", "em", "quantum", "results"),
        acceptance=("Verify geometry, Josephson inductance, mode normalization and junction identities.",
                    "Check energy participation constraints and EPR convergence.",
                    "Carry typed quantities, unit conversions and revision hashes into scqubits; compare dressed spectra."),
        next_missing_edge="Versioned reviewed Palace EPR -> quantum Hamiltonian edge",
    ),
    DesignCase(
        id="josephson_rf_amplifier", title="Josephson parametric amplifier: nonlinear RF",
        family="amplifier",
        purpose="Design nonlinear matching, gain and noise using an explicitly mapped RF netlist.",
        reference_title="JosephsonCircuits.jl: harmonic-balance solver documentation",
        reference_url="https://josephsoncircuits.org/stable/",
        starter_template=None, readiness="blocked_missing_edge",
        science_boundary="Julia native integration, netlist mapping and port reference planes remain unqualified.",
        steps=("schematic", "quantum", "results"),
        acceptance=("Verify element topology, bias, ports, impedances and reference planes.",
                    "Demonstrate native small-signal gain and harmonic-balance convergence.",
                    "Report pump conditions, noise assumptions and comparison to circuit/measurement references."),
        next_missing_edge="Reviewed revision-bound schematic -> JosephsonCircuits.jl netlist and native output edge",
    ),
)


def list_use_cases() -> list[dict]:
    """Copy-only public metadata. Never evaluates a model or publishes test spectra."""
    cases=[]
    for case in _CASES:
        if not set(case.steps) <= set(STEP_IDS):
            raise RuntimeError(f"Invalid canonical stage in {case.id}")
        row=asdict(case)
        row["steps"]=list(case.steps)
        row["acceptance"]=list(case.acceptance)
        cases.append(row)
    return cases
