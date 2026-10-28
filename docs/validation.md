# Validation evidence and limits

The previous project included historical validation logs and example acceptance files from releases 0.3–0.9. Those files are historical evidence, not proof that all features in 0.10 have been qualified. The consolidated release is documented in `validation/delivery-0.10.0.md`.

## Evidence levels

1. Unit and scientific contract tests (Python) establish program behavior under fixed inputs.
2. Web and API authorization tests establish that diagnostic functions are local/admin-only and use CSRF protections.
3. A generated diagnostic ZIP verifies that allowlisted logs and checksums can be exported.
4. A native Gmsh mesh smoke test establishes 3D meshing availability on the specific runtime where it succeeds.
5. A real Palace solve with numerical convergence and an independent reference is required before FEM accuracy or physical parameter extraction can be considered validated. **This gate remains open.**

No Windows/WSL2 GUI acceptance, Palace nonlinear solver validation or fabrication sign-off is implied by successful Python tests. Old `validation/tests.txt` and `validation_summary.json` files reflect earlier versions only. The current Web diagnostic ZIP generated on the target workstation will be the primary source of operational feedback.
