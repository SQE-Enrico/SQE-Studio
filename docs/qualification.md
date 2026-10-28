# Independent numerical reference checks

Before using FEM output to redesign a quantum chip, verify that the solver installation respects units, boundary conditions and basic known solutions.

```bash
sqw qualify --out build/reference-problems
```

This works with the core NumPy/SciPy environment. It generates two small, standalone MSH 2.2 tetrahedral meshes and Palace configurations. The structured mesh generator is independent of Gmsh and does not claim to test the chip mesher. All tetrahedra have positive orientation; boundary triangles point outwards.

## Dielectric plate capacitor

The domain is 1000 × 800 × 500 µm with relative permittivity 11.45. The entire bottom face is at zero voltage, the entire top face at one volt, and side faces are insulating. These ideal boundary conditions give an exact linear potential and capacitance:

`C = epsilon_0 epsilon_r A / d`, approximately 162.209 fF.

The core code assembles a first-order tetrahedral finite-element stiffness matrix in SI units and solves for the free-node potentials using SciPy. Capacitance is extracted from twice the stored energy at one volt. It compares both the potential and C with their independent analytical limits. This linear solution belongs to the P1 approximation space, so machine-precision agreement is expected; it is not evidence of convergence for arbitrary fringing-field chip geometries.

`capacitor/reference.json` contains actual numerical results and `capacitor/potential.csv` contains the solved field samples. The source is explicitly `scipy_p1_fem_reference`, not Palace and not the teaching chip surrogate.

## Rectangular PEC cavity

The vacuum box measures 40 × 27 × 19 mm. Its analytical resonances use

`f_mnp = c/2 * sqrt((m/a)^2 + (n/b)^2 + (p/d)^2)`.

At least two mode indices are nonzero. A triple with all three nonzero has two independent polarizations. The reference list retains those multiplicities; the first modes are approximately 6.698, 8.734 and 9.327 GHz. It includes no simulated cavity field until a native eigensolve actually runs.

## Run Palace and compare

After the native installation:

```bash
sqw qualify --solve --ranks 4 --out build/reference-palace
```

The command prepares fresh meshes, runs the electrostatic and eigenmode problems, requires successful native-solve records and parses actual output. It compares the capacitor C against the analytic value (relative tolerance 1e-5) and six cavity frequencies against the known spectrum (maximum relative tolerance 2%). Failure records an error and produces a nonzero command exit; an unavailable executable cannot become a passed solve.

For a resolution comparison, use a different directory and `--refinement 2`. Values 1–4 scale each subdivision count. The default cavity is deliberately small; refine to assess how the eigensolver and element order affect frequency accuracy. The 2% initial tolerance is an installation smoke check, not an accuracy target for a quantum chip.

`qualification.json` separates the independently executed capacitor calculation from the native Palace result. The latter remains `not_run` for a preparation-only run. The included reference artifacts were prepared and the SciPy capacitor was solved during delivery; Palace itself was unavailable.

Continue with [the chip FEM workflow](fem.md) only after the known reference cases behave correctly. Ground topology, junction ports, the real package and a measured device need their own validation.
