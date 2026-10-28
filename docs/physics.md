# Physics, units and approximation boundaries

## Electrical targets and transmon

The transmon Hamiltonian is `H = 4 EC (n-ng)^2 - EJ cos(phi)`. All Hamiltonian inputs and eigenvalues are E/h in GHz. The core diagonalizes the tridiagonal charge-basis Hamiltonian. `--quantum-backend scqubits` obtains the scqubits spectrum and checks it against this independent calculation. `ncut` is increased by 10 for a convergence check of the retained levels; a change above 100 Hz stops the calculation.

`specification.json` solves for EJ and EC using the exact first two transitions and the requested f01/anharmonicity. It gives a target total capacitance using `EC=e²/(2 C)`. The layout is not silently rescaled to force agreement with these targets. Forward-model deviations identify what needs calibration or redesign.

## Floating pads and modal reduction

For voltage vector `V`, electrostatic energy is `Vᵀ C V / 2`. Define `Va=Vcm+Vq/2`, `Vb=Vcm-Vq/2`, retain the resonator coordinate and clamp feedline voltage to ground. Eliminate `Vcm` with a Schur complement under zero total pad charge. Invert the resulting 2×2 matrix `K=C_reduced⁻¹`.

The bare qubit charging energy is `e² Kqq / 2`. Junction capacitance is a branch between A and B and is added once before this reduction. For two identical pad-to-ground capacitances Cg and mutual capacitance Cm, the differential effective capacitance is `Cg/2+Cm+Cj`.

A static terminal on a half-wave line has uniform voltage, while the microwave mode has a cosine voltage profile. The present reduced model halves the **line-to-ground** static capacitance and retains localized mutual coupling capacitances at the voltage antinode. This assumes weak localized coupling and the intended half-wave mode. It is an approximation, including for data imported from FEM. Strong coupling, spatially extended coupling and arbitrary modes require a modal impedance/field or EPR extraction, rather than this two-mode approximation.

With `Cr=1/Krr`, readout charge fluctuation is `Qr,zpf=sqrt(h fr Cr/2)`. The coupling is `g/h = |2e n01 Qr,zpf Kqr|/h`, reported as `g_MHz = g/(2pi)` when g denotes an angular frequency. The code's Hamiltonian is in cyclic frequency units, so its numeric coupling in GHz is already g/2pi.

## Dressed spectrum and dispersive convention

The coupled model diagonalizes `Hq + h fr a†a + h g (n/n01) i(a†-a)` with six transmon levels and seven oscillator states by default. States are assigned from bare-state overlap using a one-to-one assignment. `minimum_label_overlap` exposes ambiguity; low overlap requires larger truncations and interpretation. The retained oscillator cutoff is not automatically converged; increase it in `coupled_spectrum` for difficult cases.

The exact cavity frequencies conditioned on qubit g and e give `chi=(fr,e-fr,g)/2`. `chi_exact_MHz` follows that convention: the separation of the two readout resonances is **2 chi**. The perturbative cross-check is `chi=g² alpha/[Delta(Delta+alpha)]`, with `Delta=f01-fr` and negative transmon alpha. It is marked invalid near resonance. The cavity pull in state g is not itself chi.

The EPR helper uses independently supplied junction energy participations from **linearized** modes. It computes first-order self-anharmonicities and cross-Kerr magnitudes; it does not extract participations from fields automatically. Its anharmonicity must not be added to an already nonlinear exact transmon model. Use it as an advanced validation route after checking energy conventions and field normalization.

## Aluminum / silicon at 20 mK

Al is represented as a zero-thickness PEC sheet by default. Film thickness and silicon resistivity are recorded material/process inputs, not an automatic microscopic surface-loss calculation. An optional positive `kinetic_Ls_pH_per_square` replaces metal PEC with a sheet inductance in eigenmode analysis. Calibrate it using measured sheet properties; it is not inferred from nominal thickness alone.

High-resistivity silicon uses an isotropic, real `epsilon_r=11.45` starting assumption. No nominal resistivity is converted into a microwave loss tangent: cryogenic interface/TLS losses need independent data. Silicon thickness, finite chip size, air above/below and box margin enter the 3D geometry.

From EJ, the model calculates `Ic=2e EJ/hbar` and `LJ=(hbar/2e)²/EJ`. Junction area is estimated from assumed Jc, and Cj from assumed specific capacitance. The normal resistance uses the ideal zero-temperature Ambegaokar–Baratoff relation with an assumed Al gap. These values are design intentions, not a validated oxidation recipe.

Thermal populations follow Boltzmann weights at the specified temperature. They are equilibrium estimates, not a claim that the qubit's effective temperature equals the mixing chamber reading.

## Measurement model

The linewidth `kappa/(2pi)=fr/Qloaded`, with `1/Qloaded=1/Qi+1/Qc`. A single-mode, unfiltered dispersive estimate gives `T1,Purcell=(Delta/g)²/kappa`. The effective relaxation rate combines that channel with an assumed intrinsic T1; `1/T2=1/(2T1)+1/Tphi`. Intrinsic T1, Tphi, Qi and Qc are explicit inputs, never geometry-derived predictions.

The hanger response is `S21=1-(Ql/Qc)/[1+2i Ql (f-fr)/fr]`. Conditional g/e responses use the dressed cavity frequencies. Time-domain Rabi uses a two-level Lindblad/Bloch model in the rotating frame; the QuTiP adapter cross-checks it using square-root-rate collapse operators. Ramsey assumes ideal instantaneous pi/2 pulses. T1 starts in the excited state. CW spectroscopy uses the steady-state Bloch solution for an explicitly recorded weak drive.

Seeded binomial shot noise and assignment errors affect observed probability traces. No IQ amplifier noise, leakage, pulse-line transfer function, TLS bath, quasiparticles or flux-noise spectrum is modeled. These must be added and calibrated before claiming agreement with measured coherence or gate fidelity.

## Studio process-to-circuit coupling

In Studio, a parametric junction’s drawn width and overlap determine area. The assumed process Jc gives Ic, and EJ = ℏIc/(2e); the assumed specific capacitance gives Cj. A laboratory-cell project instead supplies its declared/calibrated Ic and independent Cj. These quantities feed the same exact transmon model. The CLI retains direct EJ input; `circuit.Cj_fF_override = 0` uses the area-based Cj, while a positive value supplies an independent Cj in fF. This is a calibrated-input interface, not a claim that plan-view area alone predicts a real shadow-evaporation junction.
