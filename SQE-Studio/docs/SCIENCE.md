# Current scientific scope

The native isolated-transmon chain is implemented: Quantum Metal layout,
SQDMetal/Gmsh mesh, Palace electrostatic matrix, existing Maxwell reduction,
explicit junction assumptions and genuine scqubits quantization. The saved
HTTP and real Chromium paths passed on the configured Windows/WSL workstation.
See [the model, native identity method and reference results](SINGLE_TRANSMON.md).

Each pad declares its QGeometry name, conductor label, original native terminal
index and physical groups. The integration checks those declared pairs with
upstream Shapely predicates and verifies the native ground conductor before
placing it at zero voltage. It retains original and final decks and their hashes.
No new solver, diagonalizer, Hamiltonian or geometry search is introduced.

The conditional extraction path requires a completed saved Palace capacitance
run. The manifest, native bytes, immutable revision and physical context are
checked before and after quantization. Layout/process/circuit/selection/source
study changes block reuse. Study-only revisions may reuse an unchanged source.

C_J is explicitly additional to the electrostatic matrix. E_J/h in GHz or L_J
in nH is declared with separate provenance, never inferred from PEC geometry.
C_total=C_matrix+C_J and E_C/h=e²/(2hC_total). Native scqubits performs the
Hamiltonian calculation. Four cutoffs check finite-basis stability at 10 kHz on
the final two intervals. The Koch asymptote applies for E_J/E_C >= 40 with the
existing 5% frequency and 20% anharmonicity limits. These comparisons do not
establish device accuracy or replace electrostatic convergence.

The Single transmon profile uses a fresh native EM solve and an official,
hash-pinned Palace v0.16.0 sphere benchmark. The separate Extraction profile
retains an explicitly constructed EM fixture and native scqubits. Software,
fixture, native execution and physical qualification remain distinct.

Next scientific work is mesh/domain/material sensitivity for this same chip,
followed by a published transmon/readout benchmark with complete geometry and
material inputs. Reuse SQDMetal's native EPR and Hamiltonian helpers once
junction, mode, port and normalization provenance is available.

Prior CPW evidence has unresolved physical mode identity and convergence.
Preserve its original 2% criterion and separate 3% sensitivity; this new
electrostatic case does not resolve those multimode findings.

The original dev78 core map remains immutable. Current integration changes
have a separate exact source review in config/core_changes.json. The Maxwell
reducer, physical constants, scqubits implementation and compatibility pin
remain unchanged. No independent reviewer or physical approval is asserted.
Scientific qualification NOT_ESTABLISHED; fabrication HOLD.
