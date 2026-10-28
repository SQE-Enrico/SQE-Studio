# Getting started — Web-first local workstation

1. Extract the release into a writable folder and double-click `WINDOWS-FIRST-START.cmd`.
2. Complete the first administrator setup in the automatically opened browser. Use the one-time link printed by the launcher if the browser does not open.
3. Open **System & Diagnostics** in the Studio navigation. Choose **Standard** to check Python and the core application, or **Extended** for Gmsh 3D, WSL/Ubuntu and optional Julia checks.
4. Check the report on screen, download the ZIP, and review its contents before sharing. Nothing is uploaded automatically.
5. Open **Quantum Design Lab** to create and edit a QPU design, save a revision, submit a job, and inspect numerical results and saved files.

**Optional native tools:** Palace runs through Ubuntu/WSL2 or Linux; Quantum Metal and JosephsonCircuits.jl use their own environments. Installers remain explicit OS-level operations. The Web app reports the observed environment but does not request administrator privileges or compile solvers without your action.

**If startup fails:** double-click `WINDOWS-DIAGNOSTICS.cmd` to produce a minimal support bundle without opening the Web UI. See `docs/windows.md` and `docs/diagnostics-windows.md`.

**Upgrade safety:** do not overwrite or distribute an existing `studio-data` folder. Back up data and run the new release from a separate folder first. It is expected that the ZIP contains no `.venv` and no `studio-data`.

## FEM numerical reference checks (v0.13)

Once the app is open and Palace is available, use **System & Diagnostics → Palace scientific diagnostics → Numerical**. This launches two small reference capacitor meshes and a PEC cavity eigenmode solve in isolated temporary workspaces. View numeric results in the browser, then download the allowlisted diagnostic ZIP. For interpretation and limitations see `docs/WORKFLOW-VALIDATION-0.13.0.md`. Do not start this profile in parallel with another FEM run.
