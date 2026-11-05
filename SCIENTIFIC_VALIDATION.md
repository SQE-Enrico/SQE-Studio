# Scientific validation evidence

The isolated-transmon method, model dimensions, material assumptions, native
identity checks and junction convention are documented in
[SINGLE_TRANSMON.md](SQE-Studio/docs/SINGLE_TRANSMON.md).
This is the authoritative method review for the current integration delta.

| Case | Native engine / comparison | Actual result | Confidence and limitation |
|---|---|---|---|
| Palace official two-sphere electrostatics | Palace v0.16.0 GitTag 869ee5c; unmodified versioned deck/mesh; published analytic matrix | Maximum entry error 3.532%, below the predeclared 5% limit; input hashes retained | Native validated for this runtime/reference case |
| Isolated TransmonPocket EM | Quantum Metal 0.9.0, SQDMetal 0.0.1.dev1, Gmsh 4.15.2, native Palace | Maxwell matrix retained with exact CAD/ground/deck/mesh identities | Native conditional; coarse mesh, no chip convergence claim |
| Conditional transmon with additional C_J=2 fF, E_J/h=15 GHz | Existing Maxwell reducer and scqubits 4.3.1 | C_eff=86.7216161 fF; f01=4.88962637 GHz; alpha=-244.65982 MHz | Native conditional; junction/material inputs are unmeasured assumptions |
| Browser case with additional C_J=12 fF and declared L_J | Same saved-source pipeline, driven through Chromium | f01=4.64720979 GHz; alpha=-218.32491 MHz; lower EC/f01 for larger additional capacitance | Native conditional; numerical sensitivity, not device calibration |
| Charge-basis stability | Native ncut 15, 20, 25, 30 | Existing final two interval criterion PASS at 10 kHz | Finite quantum-basis stability only |
| Source/error boundaries | Genuine saved native output | Geometry change, stale revision, altered CSV, wrong units, C_J double counting and missing CSRF rejected | Functional/provenance evidence |
| Coupled transmon/readout | Native prototype in progress | No accepted result recorded yet | Untested product workflow |

Native report: `SQE-Studio/qualification-reports/SQE-RC14_12-report-0011.zip`,
SHA-256 `f086b9dd8d6d8e4c751d0987766f95a60aead41537fe58d06cc74ebf1db6e454`.
Its nested native archive SHA-256 is
`65afa5db4c48c9dbd417c2051343fe2053c740b147a3fd9cc82b479921ac2bf8`.
It includes original solver output, manifests, input models, installed upstream
source hashes and a real browser screenshot.

Physical convergence, experimental comparison, film losses/kinetic inductance,
multi-mode normalization and validated general EPR transfer remain open.
No independent reviewer or fabrication signoff is claimed.
Scientific qualification NOT_ESTABLISHED; fabrication HOLD.
