# Quality gates — required to call SQE Studio an EDA product or release candidate

**Current state:** software-oriented integration passes the available tests; **scientific release blocked**. Do not use labels such as approved, validated, or equivalent to QuantumPro without the evidence below.

| Gate | Objective evidence required | Present status |
|---|---|---|
| Model/UI | One project and workflow for all device families; authenticated GUI edits, stale revision rejection and accessibility | Software tests only; live multi-platform browser acceptance pending |
| Source/build | Clean import, independent install, wheel reproducibility with fixed build epoch, asset inspection and dependency inventory | Build verification required for each candidate |
| Security | Loopback/auth/CSRF/ACL/CAS, unsafe ZIP/symlink/path rejection, no arbitrary engine code execution, adversarial tests | Implemented tests are not a security audit |
| QDesign/GDS | Actual native QGeometry and GDS layer/ports reviewed in an external viewer | Independent native regression pending |
| EM | Genuine Gmsh mesh and Palace deck, correctly mapped ports/materials/boundaries, completed native eigenmode/capacitance/driven solve and mesh convergence | Blocked by native qualification |
| Material physics | Reproduced PEC control plus reviewed kinetic-inductance sheet model (film regime, physical surfaces) | General adapter blocked |
| Quantum | Genuine scqubits spectra with cutoff convergence and documented energy units; EPR-derived values only through a reviewed transform | Independent inputs conditional; EM→quantum blocked |
| Nonlinear/RF | Real JosephsonCircuits.jl solver, port/impedance conventions, pump/harmonic convergence and complex S-parameter comparison | Julia adapter blocked |
| Cross-engine design loop | Typed, versioned edge evidence and comparable physical identities, geometry ↔ EM ↔ circuit; no silent numeric conversions | Partially present, main bridges blocked |
| Optimization | Constraint/target units, replayable candidate revisions, actual native solver evaluations and stopping criteria | Only bounded study-input sweeps, not general optimization |
| External validation | Named published geometry/settings reproduced numerically and compared with reference results; separate independent measurements | Not available |
| Fabrication | Signed PDK, reviewed DRC/LVS/masks, operator/foundry signoff | Always HOLD |

**Laptop evidence handoff:** use the no-terminal desktop **Qualify this laptop** action; see [LAPTOP_QUALIFICATION.md](LAPTOP_QUALIFICATION.md). It produces a shareable privacy-minimized ZIP with PASS/FAIL/BLOCKED per gate. This is a release engineering operation, never a design engine or an experiment registry.

**Mandatory scientific benchmark order:** CPW eigenmode on laptop → independent scqubits spectrum with basis check → EPR and material-model bridges with real native outputs → coupled cross-engine design loop → nonlinear RF → independent measurements and fabrication review. Treat skipped native tests as missing evidence, not success.
