# Full FEM workflow: Gmsh and Palace

This route is implemented but was **not executed in the delivery environment**. Treat generated mesh/configuration code as a workstation qualification candidate. The included CSV fixtures test interfaces; they are not solver results.

Start with [the independent capacitor/cavity qualification](qualification.md): `sqw qualify --out build/reference-inputs` prepares the cases and `sqw qualify --solve --out build/reference-palace` runs them on a workstation with Palace. The actual SciPy capacitor reference is separate from both the chip surrogate and the native solver.

## Shared geometry and boundary conditions

Gmsh creates a finite silicon die inside an enclosing air box with air above and below. The same positive-metal rectangles exported to GDS are fused by electrical net, then fragmented with the substrate and air volumes. The OCC fragment maps assign boundary tags; they are not guessed from mesh entity numbers. Ports are rectangular sheets with explicit field directions. Coordinates are µm and Palace's `Model.L0=1e-6` converts to metres.

| Physical tag | Entity |
|---|---|
| Volume 1 / 2 | Air / silicon |
| Surface 10 | Ground plane |
| Surface 11 / 12 | Transmon A / B pads and coarse leads |
| Surface 13 / 14 | Isolated half-wave readout / feedline |
| Surface 21 | Rectangular junction gap port, along +X |
| Surface 31 / 32 | Input/output gap ports from launch pads to ground, along +Y |
| Surface 99 | Enclosing outer box |

Electrostatic: four terminal excitations with all other terminals held at zero; ground and enclosing box at zero voltage. Junction gap is dielectric. Eigenmode: metal and box PEC, with 50-ohm terminations at launch gaps. `kinetic_Ls_pH_per_square>0` replaces metal PEC by a specified sheet inductance; this requires separate convergence validation.

`eigenmode.json` leaves the JJ port open to compute passive readout modes. `linearized.json` adds parallel LJ and Cj across the junction for an optional hybrid-mode cross-check. Its eigenfrequencies must **not** be imported as bare readout frequencies and then coupled to the same qubit again.

The box is an ideal enclosure approximation, not the laboratory sample holder. Bond wires, seams, real connectors and ground straps are absent. Large 2D ground regions separated by the feedline can support slotline modes; identify them and add the actual grounding strategy before fabrication. A 3D enclosure resonance inside 4–12 GHz is a possible result to investigate, not an automatic qubit/readout assignment.

## Run stages and inspect modes

After completing [setup](setup.md):

```bash
sqw stage spec --out build/fem-staged
sqw stage layout --cad-backend qpdk --out build/fem-staged
sqw stage em-export --out build/fem-staged
sqw stage mesh --out build/fem-staged
sqw stage solve --problem electrostatic --ranks 4 --out build/fem-staged
sqw stage solve --problem eigenmode --ranks 4 --out build/fem-staged
```

Supply `--palace /absolute/path/to/palace` if it is not on `PATH`. The Palace launcher receives `-np N` and handles MPI itself; a binary ending in `.bin` is launched through `mpiexec` when requested. Solver output is saved to a log, and a nonzero exit stops the stage. Native subprocesses have a four-hour timeout, adjustable through the Python API.

Review `em/mesh.json`, all physical groups, the silicon/air interface and the JJ/input/output patches in Gmsh. Confirm positive element Jacobians and adequate resolution of gaps. Use ParaView to inspect the saved eigenmode fields, identify the half-wave readout voltage profile and distinguish substrate, package, feedline and slotline modes.

Then import the mode that was actually identified (replace `2`):

```bash
sqw stage import --readout-mode 2 --out build/fem-staged
sqw stage quantize --quantum-backend scqubits \
  --extraction build/fem-staged/extraction.json --out build/fem-staged
sqw stage experiment --dynamics-backend qutip --out build/fem-staged
sqw stage report --out build/fem-staged
```

The import stage expects Palace `electrostatic/terminal-C.csv` with headers `i,C[i][1] (F),...,C[i][4] (F)` and `eigenmode/eig.csv` with an indexed real-frequency column in GHz. It rejects other units or unknown formats. If a Palace release changes output names/headers, update the adapter and an independently obtained fixture after inspecting its actual output; never guess scale factors.

Successful solves record the input mesh/configuration and every raw CSV checksum. Changed raw output, mismatched geometry or a successful process exit without its expected CSV is rejected. After a completed pipeline, run `sqw verify --run build/fem-staged`. If you rerun mesh/configuration/solve stages, their dependent import, quantization, experiment and report become stale and need to be regenerated.

To inspect linearized hybrid modes separately:

```bash
sqw stage solve --problem linearized --ranks 4 --out build/fem-staged
```

Keep the raw solver CSV, logs, mesh, configuration, field output, native build information and normalized extraction together. The parser records the hashes of imported raw capacitance and eigenfrequency files.

## Convergence and validation

Create separate configuration copies and output directories. Vary minimum edge size, maximum volume size, polynomial order, air height, bottom clearance and box margin. Track the **same physical mode by its fields**, not by a permanently fixed sorted index. Suggested initial acceptance targets are <1% change in effective C, <0.2% in readout frequency and <5% in g/chi between successive resolved meshes; tighten them to the experiment's uncertainty budget. These are proposed research criteria, not achieved results.

The default mesh uses a distance field on metal edges, 2 µm near gaps and up to 350 µm in the far volume. A full chip with micron-scale gaps can require a substantial workstation or cluster. Start by checking geometry and a deliberately coarse qualification mesh, then refine. Do not certify a coarse mesh simply because the linear solver converged.

The reduced half-wave capacitance mapping is approximate. Check readout modal impedance, quantum truncation and hybrid eigenmodes before attributing disagreements solely to mesh resolution. Compare against a known capacitor/cavity benchmark before interpreting a real chip. [Physics](physics.md) explains which quantities are exact within the model and which are assumptions.

## Participation ratios

Generated Palace configs save bulk Si energy integrals and fields. They do not automatically compute microscopic interface loss or extract junction EPR. To use `em.epr_kerr`, derive normalized junction inductive energies from the linearized mode fields/port voltages and total inductive energy, validate the convention with a single-mode limit, then pass the resulting mode×junction matrix. Surface participations need a qualified interface thickness/permittivity model and field convergence. This extension is documented rather than fabricated as a numerical result.
