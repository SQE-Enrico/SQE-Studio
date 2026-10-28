"""Charge-basis quantization and floating-node capacitance reduction. SI internally."""

import numpy as np
from scipy.constants import e, h, hbar, k
from scipy.linalg import eigh_tridiagonal
from scipy.optimize import least_squares, linear_sum_assignment


def junction(cfg):
    mat = cfg["materials"]
    energy = cfg["circuit"]["EJ_GHz"]*h*1e9
    ic = 2*e*energy/hbar
    area_um2 = ic/(mat["junction_Jc_A_per_cm2"]*1e4)*1e12
    override = cfg['circuit'].get('Cj_fF_override', 0.)
    return {"Ic_nA": ic*1e9, "LJ_nH": (hbar/(2*e))**2/energy*1e9,
            "area_um2": area_um2, "Cj_fF": override or area_um2*mat["junction_specific_C_fF_per_um2"],
            "Rn_ohm_AB_zero_T": np.pi*mat["al_gap_ueV"]*1e-6/(2*ic),
            "provenance": "EJ input; Jc-inferred area; "+("declared Cj" if override else "assumed specific capacitance")+"; AB ideal tunnel junction"}


def transmon(EJ_GHz, EC_GHz, ng=0.0, ncut=35, levels=6, backend="scipy"):
    n = np.arange(-ncut,ncut+1)
    vals, vecs = eigh_tridiagonal(4*EC_GHz*(n-ng)**2,
                                 np.full(2*ncut,-EJ_GHz/2),
                                 select="i",select_range=(0,levels-1))
    if backend == "scqubits":
        import scqubits as scq
        qubit = scq.Transmon(EJ=EJ_GHz,EC=EC_GHz,ng=ng,ncut=ncut,truncated_dim=levels)
        ref_vals = qubit.eigenvals(evals_count=levels)
        if not np.allclose(vals-vals[0],ref_vals-ref_vals[0],atol=1e-8):
            raise ValueError("scqubits / SciPy spectrum disagreement")
        vals = ref_vals
    elif backend != "scipy":
        raise ValueError("Unknown quantum backend")
    charges = vecs.T @ (n[:,None]*vecs)
    return vals-vals[0], charges


def validate_capacitance(matrix_fF):
    c = np.asarray(matrix_fF,dtype=float)
    if c.shape != (4,4) or not np.all(np.isfinite(c)):
        raise ValueError("Expected a finite 4x4 Maxwell capacitance matrix in fF")
    if not np.allclose(c,c.T,rtol=1e-7,atol=1e-8):
        raise ValueError("Capacitance matrix is not symmetric")
    off = c-np.diag(np.diag(c))
    if np.any(off > 1e-8) or np.any(c.sum(axis=1) < -1e-7):
        raise ValueError("Invalid Maxwell sign convention or negative capacitance to ground")
    if np.linalg.eigvalsh(c).min() <= 0:
        raise ValueError("Capacitance matrix must be positive definite")
    return c


def surrogate(cfg, geometry):
    """Deliberately low-fidelity geometric sensitivity model, NEVER an EM result."""
    p, mat = cfg["layout"], cfg["materials"]
    c = np.zeros((4,4))

    def ground(i,value):
        c[i,i] += value

    def branch(i,j,value):
        c[i,i] += value
        c[j,j] += value
        c[i,j] -= value
        c[j,i] -= value

    scale = (p["pad_width_um"]+p["pad_height_um"])/800*(24/p["moat_um"])**0.15
    pad_c = 130*scale*(mat["epsilon_r"]+1)/12.45
    ground(0,pad_c)
    ground(1,pad_c)
    branch(0,1,10*(20/p["pad_gap_um"])**0.35)
    cc = cfg["circuit"]["coupling_C_fF"]*(8/p["qubit_coupler_gap_um"])**0.7
    branch(0,2,cc)
    branch(1,2,0.1*cc)
    eps_eff = (mat["epsilon_r"]+1)/2
    fr = 299792458/(2*geometry["resonator_length_um"]*1e-6*np.sqrt(eps_eff))/1e9
    ground(2,1/(2*fr*1e9*cfg["circuit"]["resonator_Z_ohm"])*1e15)
    ground(3,1500)
    branch(2,3,2.0*p["feed_coupler_length_um"]/300)
    return {"schema_version": 1,"source": "analytic_surrogate", "synthetic": True,
            "node_order": ["pad_a","pad_b","resonator","feedline"],
            "matrix_fF": c.tolist(), "readout_GHz": fr,
            "geometry_sha256": geometry["geometry_sha256"],
            "assumptions": ["Uncalibrated pad/fringe capacitances", "Quasistatic CPW epsilon_eff",
                            "Half-wave readout at voltage antinode", "Junction capacitance excluded"]}


def reduce_floating(matrix_fF, junction_C_fF=0.0):
    c = validate_capacitance(matrix_fF)*1e-15
    # Open/open half-wave voltage profile: integral cos^2 = length/2.
    # Only the distributed line-to-ground self-C is halved; localized mutual C stays.
    # This antinode approximation is an explicit reduced model, not an exact EM reduction.
    c[2,2] -= 0.5*np.sum(c[2])
    c[:2,:2] += junction_C_fF*1e-15*np.array([[1,-1],[-1,1]])
    # Va=Vcm+Vq/2, Vb=Vcm-Vq/2; readout independent; feedline voltage clamped to 0.
    transform = np.array([[1,.5,0],[1,-.5,0],[0,0,1],[0,0,0]])
    ct = transform.T @ c @ transform
    reduced = ct[1:,1:]-np.outer(ct[1:,0],ct[0,1:])/ct[0,0]
    return reduced, np.linalg.inv(reduced)


def synthesize(cfg):
    target_f = cfg["targets"]["f01_GHz"]
    target_a = cfg["targets"]["anharmonicity_MHz"]/1000

    def residual(logvalues):
        ej,ec = np.exp(logvalues)
        vals,_ = transmon(ej,ec,ncut=cfg["circuit"]["ncut"])
        return [vals[1]-target_f, (vals[2]-2*vals[1]-target_a)*5]

    ec0 = abs(target_a)
    ej0 = (target_f+ec0)**2/(8*ec0)
    fit = least_squares(residual,np.log([ej0,ec0]),xtol=1e-12,gtol=1e-12,ftol=1e-12)
    ej,ec = np.exp(fit.x)
    if not fit.success or np.linalg.norm(fit.fun) > 1e-5:
        raise ValueError("Target synthesis failed to converge")
    return {"EJ_GHz": ej,"EC_GHz": ec,"C_total_target_fF": e**2/(2*h*ec*1e9)*1e15,
            "target_f01_GHz": target_f,"target_anharmonicity_MHz": target_a*1000,
            "note": "Electrical target only; geometry must be calibrated or FEM optimized to match"}


def coupled_spectrum(energies, charges, fr, g, photons=7):
    nlev = len(energies)
    a = np.diag(np.sqrt(np.arange(1,photons)),1)
    charge = charges/max(abs(charges[0,1]),1e-15)
    H = (np.kron(np.diag(energies),np.eye(photons))
         + np.kron(np.eye(nlev),fr*a.T@a)
         + g*np.kron(charge,1j*(a.T-a)))
    vals,vecs = np.linalg.eigh(H)
    rows, cols = linear_sum_assignment(-abs(vecs)**2)
    assign = dict(zip(rows,cols))

    def energy(q,n):
        return vals[assign[q*photons+n]]

    def overlap(q,n):
        i = q*photons+n
        return abs(vecs[i,assign[i]])**2

    frg,fre = energy(0,1)-energy(0,0),energy(1,1)-energy(1,0)
    return {"f01_dressed_GHz": energy(1,0)-energy(0,0),
            "readout_g_GHz": frg,"readout_e_GHz": fre,
            "chi_exact_MHz": (fre-frg)*500,
            "minimum_label_overlap": min(overlap(0,0),overlap(0,1),overlap(1,0),overlap(1,1))}


def parameters(cfg, extraction, backend="scipy"):
    jj = junction(cfg)
    cap,kcap = reduce_floating(extraction["matrix_fF"],jj["Cj_fF"])
    cq,cr = 1/kcap[0,0],1/kcap[1,1]
    ec = e**2/(2*cq*h)/1e9
    ej = cfg["circuit"]["EJ_GHz"]
    c = cfg["circuit"]
    energies,charges = transmon(ej,ec,c["ng"],c["ncut"],c["levels"],backend)
    larger,_ = transmon(ej,ec,c["ng"],c["ncut"]+10,c["levels"])
    fr = extraction["readout_GHz"]
    qr_zpf = np.sqrt(h*fr*1e9*cr/2)
    g = 2*e*abs(charges[0,1])*qr_zpf*abs(kcap[0,1])/h/1e9
    f01,alpha = energies[1],energies[2]-2*energies[1]
    delta = f01-fr
    dispersive = abs(delta) > 5*g and abs(delta+alpha) > 5*g
    chi = g*g*alpha/(delta*(delta+alpha)) if dispersive else None
    qloaded = 1/(1/cfg["experiment"]["readout_Qi"]+1/cfg["experiment"]["readout_Qc"])
    kappa = 2*np.pi*fr*1e9/qloaded
    purcell_us = (delta/g)**2/kappa*1e6 if g > 0 and dispersive else None
    temp = cfg["device"]["temperature_mK"]*1e-3
    boltz = np.exp(-(energies-energies[0])*h*1e9/(k*temp))
    probs = boltz/boltz.sum()
    half_charge,_ = transmon(ej,ec,0.5,c["ncut"],c["levels"])
    zero_charge,_ = transmon(ej,ec,0,c["ncut"],c["levels"])
    result = {"schema_version": 1,"source": extraction["source"],
              "synthetic":extraction.get("synthetic",True),
              "geometry_sha256": extraction["geometry_sha256"],"quantum_backend": backend,
              "EJ_GHz": ej,"EC_GHz": ec,"EJ_over_EC": ej/ec,
              "C_qubit_effective_fF": cq*1e15,"C_readout_effective_fF": cr*1e15,
              "reduced_capacitance_fF": cap*1e15,"energies_GHz": energies,
              "f01_GHz": f01,"anharmonicity_MHz": alpha*1000,
              "readout_bare_GHz": fr,"g_MHz": g*1000,
              "chi_perturbative_MHz": None if chi is None else chi*1000,
              "dispersive_approximation_valid": dispersive,
              "n_critical": (delta/g)**2/4 if g>0 else None,
              "n01": abs(charges[0,1]),"charge_dispersion_f01_kHz":
              abs(half_charge[1]-zero_charge[1])*1e6,
              "charge_basis_convergence_Hz": max(abs(energies-larger))*1e9,
              "thermal_populations": probs,"thermal_excited_probability": float(1-probs[0]),
              "readout_n_thermal": 1/np.expm1(h*fr*1e9/(k*temp)),
              "readout_Q_loaded": qloaded,"kappa_over_2pi_MHz": fr*1000/qloaded,
              "T1_Purcell_us": purcell_us,"junction": jj,
              "targets": cfg["targets"],
              "target_deviation":{"f01_MHz":(f01-cfg["targets"]["f01_GHz"])*1000,
                                  "anharmonicity_MHz":alpha*1000-cfg["targets"]["anharmonicity_MHz"],
                                  "readout_MHz":(fr-cfg["targets"]["readout_GHz"])*1000,
                                  "g_MHz":g*1000-cfg["targets"]["coupling_MHz"]},
              "coherence_provenance": "T1 intrinsic, Tphi, Qi and Qc are assumed inputs"}
    result["modal_reduction"] = "Half-wave antinode: distributed readout ground C / 2; localized coupling retained"
    result.update(coupled_spectrum(energies,charges,fr,g))
    if result["charge_basis_convergence_Hz"] > 100:
        raise ValueError("Charge basis has not converged to 100 Hz")
    return result
