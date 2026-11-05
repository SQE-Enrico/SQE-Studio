# Native single-transmon workflow

This development connects an isolated Quantum Metal TransmonPocket to a native
SQDMetal/Gmsh/Palace electrostatic solve and the existing conditional scqubits
path. It reuses the existing Maxwell reduction and scqubits Hamiltonian. It does
not introduce a solver, diagonalizer, or geometry search algorithm.

## Model and conductor identity

The reference chip is 1.2 mm square with a 500 um silicon substrate. The two pads
are 300 by 150 um with a 30 um gap, inside a 700 by 500 um ground cutout.
Silicon eps_r=11.45 and tan_delta=2.7e-6 are explicit SQDMetal catalogue inputs,
not measured material properties. Templates remain unverified until acknowledged.

Each terminal explicitly declares its CAD component, native QGeometry name,
conductor label, upstream terminal index and mesh physical groups. This first
case supports one isolated pocket with pad_bot and pad_top. Unsupported
connections, missing identities and changed native ordering fail closed.

The declared pairs are checked directly with Shapely normalize and
equals_exact, at 1e-12 mm coordinate tolerance. There is no nearest-shape search
or inference from a component name. Ground is obtained from SQDMetal's own
geometry processor and checked against its declared native conductor.

SQDMetal initially exports the chip ground as a third electrostatic terminal.
The integration retains that original deck, places the verified reference
conductor at zero voltage, and retains the two explicitly selected pads as the
matrix terminals. Physical-group names are checked with the Gmsh API. Original
and final decks, mesh, selector metadata and hashes are retained with the run.

Readback checks the exact saved layout, process, original deck, final deck,
mesh and conductor labels. Changing a layout or process requires another solve.
The existing immutable-revision, artifact, authentication and CSRF rules apply.

## Current technical verification

The installed Palace runtime reported Git changeset 869ee5c, matching the
official v0.16.0 release. Its unmodified two-sphere example completed locally.
Against the published analytic coefficients, the relative errors were 0.563%,
1.928% and 3.532%. The per-entry acceptance limit was fixed at 5% before solving.
This verifies that runtime/example combination, not a fabricated chip.

The native reference transmon produced the following coarse-mesh Maxwell matrix
in farads, in Q1_pad_bot, Q1_pad_top order:

    [[ 1.242717983728e-13, -4.877343445420e-14],
     [-4.877343445420e-14,  1.250720155860e-13]]

The direct native solve, saved HTTP job chain and real Chromium workflow passed.
With additional C_J=2 fF and declared E_J/h=15 GHz, the native chain gives
C_effective=86.7216161 fF, E_C/h=0.21832593 GHz, f01=4.88962637 GHz and
anharmonicity=-0.24465982 GHz. Four scqubits cutoffs (15, 20, 25, 30) passed
the existing 10 kHz basis criterion.

The browser repeats the source-selection and quantization workflow with
additional C_J=12 fF and declared L_J=10.897434187118746 nH. It gives
f01=4.64720979 GHz and anharmonicity=-0.21832491 GHz, with stable basis results.
These are outputs of the stated reference model, not measured device properties.

Run the complete automated case from the repository root:

    ./dev.ps1 -Profile single_transmon

The profile runs the pinned official benchmark, real saved Palace/scqubits jobs,
browser actions and provenance rejection checks. It retains the original native
files, manifests, input snapshots and a browser screenshot in its numbered local
report. It does not use the EM-fixture source of the separate extraction profile.

## Junction and scientific scope

Junction capacitance is additional to the electrostatic matrix. E_J/h in GHz
or L_J in nH must have separate explicit provenance; neither is inferred from
the PEC geometry. The existing reduction computes C_effective, and the existing
conditional extraction supplies E_C/h and the declared E_J/h to scqubits.

Basis convergence is separate from electrostatic convergence. Mesh, domain,
material sensitivity, multimode coupling, losses and experimental comparison
remain required for a physical design qualification. No independent technical
or scientific reviewer is asserted. Scientific qualification NOT_ESTABLISHED;
fabrication HOLD.

## Current source review

The original dev78 core hash map remains unchanged. Active changes are recorded
separately in config/core_changes.json and checked by the development gate.
The integration changes native terminal binding and label provenance; it does
not replace the Maxwell reducer, physical constants or scqubits calculations.
The adapter returns the registered SQDMetal distribution version to the frozen
worker contract; complete dependency versions remain in the verified native
sidecar. Palace and scqubits cache fingerprints include the identity checker.
Current unit tests and native benchmarks must accompany changes to these files.
The source review is an implementation review, not independent physics approval.
The authenticated design-case catalogue also exposes this implemented starter;
its conditional status and remaining physical convergence requirements are explicit.

Primary references:

- [Palace v0.16.0 two-sphere example and analytic coefficients](https://github.com/awslabs/palace/blob/v0.16.0/docs/src/examples/spheres.md)
- [SQDMetal Palace capacitance integration](https://github.com/sqdlab/SQDMetal/blob/main/SQDMetal/PALACE/Capacitance_Simulation.py)
- [SQDMetal native geometry processing](https://github.com/sqdlab/SQDMetal/blob/main/SQDMetal/Utilities/GeometryProcessors/GeomQiskitMetal.py)
- [Shapely exact geometry equality](https://shapely.readthedocs.io/en/stable/reference/shapely.equals_exact.html)
- [scqubits Transmon model and basis cutoff](https://scqubits.readthedocs.io/en/latest/guide/qubits/transmon.html)
- [Koch et al., transmon theory](https://arxiv.org/abs/cond-mat/0703002)
