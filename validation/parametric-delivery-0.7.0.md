# SQE 0.7 delivery verification

## Verified in this development environment

- Regressione completa eseguita in Linux: **103 test, 0 errori, 4 saltati** (opzionali); frontend `quantumlab.js` supera `node --check`.

- Physical schema v2 validation, user-defined material and dielectric stacking, topology and junction technology.
- 1, 2, 4, 9 and 16-qubit nominal layout and circuit generation.
- Positive-metal planar boolean DRC and ground clearance, interdigitated and isolated physical bus CPW couplers; custom two-island qubit library and custom electrode coupler, including disconnected/short-circuit rejection.
- Named CPW routing and deterministic GDSII polygons for Dolan and Manhattan process **intent**.
- Package export, stable SHA-256 geometry/provenance, Quantum Metal interchange using a mocked headless QDesign; smoke CLI export of `custom-2q.json` with GDS inspection.
- Web API access control, preview/export and an actually executed persistent `physical:package` job.
- The 0.6 schema v1 remains available unmodified.

## NOT verified

- Windows 10/11 first-run installer or WSL2 compilation of Palace; Linux test runner is not a substitute.
- Native Gmsh fragmentation and material/port physical groups for realistic multilayer meshes (Gmsh Python unavailable).
- Running the exported Palace files in a real solver, validating capacitance/eigenmodes/S-parameters or comparing to a trusted reference.
- Reconstructing Dolan shadow-evaporation geometry or Manhattan process angles; *HOLD* mask annotations are never foundry sign-off.
- Arbitrary multilayer metal and via stack meshing; currently preflight-rejected if >1 conductor plane.
- Automatic graph-derived Maxwell C reduction, extracted g/Kerr/EPR/Purcell and formal loss participations.

## Required acceptance on user's Windows machine

1. Run `WINDOWS-FIRST-START.cmd`. Inspect the `.venv` status and assert the new Shapely dependency, plus Python and API tests.
2. Create a v2 physical design from the Quantum Design Lab. Switch Dolan to Manhattan, then change the substrate thickness and verify that new GDS/contract hashes are generated.
3. Validate physically disconnected coupler fingers and an isolated named bus net in the imported GDS with a viewer such as KLayout.
4. Install Palace with `WINDOWS-PALACE-SETUP.cmd` and generate a small test mesh with Gmsh. Compare 3D physical tags to the Palace JSON config.
5. Run Palace electrostatics on a 1Q device; review solver log and compare terminal Cij against a converged independent result. Repeat with mesh/order refinements before trusting any values.
6. Add a real test structure, calibrated material data and process rule deck before any wafer/mask tapeout decisions.
