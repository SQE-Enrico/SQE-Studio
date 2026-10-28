"""Expected measurements at configured temperature; explicit input coherence/noise model."""

from pathlib import Path

import numpy as np
from scipy.constants import h, k
from scipy.sparse.linalg import expm_multiply

from .io import write_csv, write_json


def bloch(times_us, rabi_MHz, detuning_MHz, gamma1, gamma2, p_eq):
    times_us = np.asarray(times_us,dtype=float)
    if (len(times_us)<2 or times_us[0]<0 or np.any(np.diff(times_us)<=0) or
        not np.allclose(np.diff(times_us),np.diff(times_us)[0])):
        raise ValueError("Bloch times must be increasing, nonnegative and uniformly spaced")
    omega, delta = 2*np.pi*rabi_MHz,2*np.pi*detuning_MHz
    generator = np.array([[-gamma2,-delta,0,0], [delta,-gamma2,-omega,0],
                          [0,omega,-gamma1,gamma1*(1-2*p_eq)], [0,0,0,0]],float)
    result = expm_multiply(generator,np.array([0.,0.,1.,1.]),start=times_us[0],stop=times_us[-1],
                           num=len(times_us),endpoint=True)
    return np.clip((1-result[:,2])/2,0,1)


def simulate(cfg, params, out, backend="scipy"):
    out = Path(out)
    out.mkdir(parents=True,exist_ok=True)
    e = cfg["experiment"]
    intrinsic = e["T1_intrinsic_us"]
    purcell = params["T1_Purcell_us"]
    gamma1 = 1/intrinsic+(1/purcell if purcell is not None else 0)
    gamma2 = gamma1/2+1/e["Tphi_us"]
    temp = cfg["device"]["temperature_mK"]*1e-3
    peq = 1/(1+np.exp(h*params["f01_GHz"]*1e9/(k*temp)))
    rng = np.random.default_rng(e["seed"])

    def sample(p):
        measured = e["assignment_p0_as_1"]*(1-p)+(1-e["assignment_p1_as_0"])*p
        return rng.binomial(e["shots"],np.clip(measured,0,1))/e["shots"]

    t = np.linspace(0,1.2,481)
    rabi = bloch(t,e["rabi_MHz"],0,gamma1,gamma2,peq)
    if backend == "qutip":
        import qutip as qt
        lowering = qt.basis(2,0)*qt.basis(2,1).dag()
        cops = [np.sqrt(gamma1*(1-peq))*lowering,
                np.sqrt(gamma1*peq)*lowering.dag(), np.sqrt(1/(2*e["Tphi_us"]))*qt.sigmaz()]
        result = qt.mesolve(np.pi*e["rabi_MHz"]*qt.sigmax(),qt.basis(2,0),t,cops,
                            e_ops=[qt.basis(2,1).proj()],options={"atol":1e-10,"rtol":1e-9})
        qt_prob = np.array(result.expect[0])
        if np.max(abs(qt_prob-rabi)) > 2e-6:
            raise ValueError("QuTiP / Bloch Rabi disagreement")
        rabi = qt_prob
    elif backend != "scipy":
        raise ValueError("Unknown dynamics backend")
    traces = {"rabi": (t,rabi)}
    long_t = np.linspace(0,5/gamma1,501)
    traces["t1"] = (long_t,peq+(1-peq)*np.exp(-gamma1*long_t))
    ramsey_t = np.linspace(0,4/gamma2,1001)
    ramsey = .5*(1-np.exp(-gamma2*ramsey_t)*np.cos(2*np.pi*e["ramsey_detuning_MHz"]*ramsey_t))
    traces["ramsey"] = (ramsey_t,ramsey)
    for name,(time,p) in traces.items():
        write_csv(out/f"{name}.csv",{"time_us":time,"p1_ideal":p,"p1_observed":sample(p)})
    frg,fre = params["readout_g_GHz"],params["readout_e_GHz"]
    width = max(.005,4*abs(frg-fre))
    freq = np.linspace(min(frg,fre)-width,max(frg,fre)+width,1601)
    ql,qc = params["readout_Q_loaded"],e["readout_Qc"]

    def s21(f0):
        return 1-(ql/qc)/(1+2j*ql*(freq-f0)/f0)

    sg,se = s21(frg),s21(fre)
    write_csv(out/"readout_s21.csv",{"frequency_GHz":freq,"g_real":sg.real,"g_imag":sg.imag,
                                         "e_real":se.real,"e_imag":se.imag})
    fqubit = np.linspace(params["f01_GHz"]-.015,params["f01_GHz"]+.015,1201)
    # A specified weak CW drive; saturation and linewidth use the same Bloch rates.
    spec_omega = 2*np.pi*.03
    saturation = spec_omega**2/(gamma1*gamma2)
    excitation = peq+(.5-peq)*saturation/(1+saturation+(2*np.pi*(fqubit-params["f01_GHz"])*1000/gamma2)**2)
    write_csv(out/"spectroscopy.csv",{"frequency_GHz":fqubit,"p1_ideal":excitation,
                                      "p1_observed":sample(excitation)})
    metrics = {"source":params["source"],"dynamics_backend":backend,
               "T1_effective_us":1/gamma1,"T2_us":1/gamma2,"Tphi_assumed_us":e["Tphi_us"],
               "thermal_p1_two_level":peq,"rabi_MHz":e["rabi_MHz"],
               "spectroscopy_drive_MHz":.03,"seed":e["seed"],"shots":e["shots"],
               "limitations":["Markovian two-level dynamics with ideal Ramsey pulses",
                              "Intrinsic T1/Tphi and readout Qi/Qc are assumptions, not geometry predictions",
                              "No TLS, quasiparticles, leakage, attenuation chain or amplifier model",
                              "Purcell estimate is single-mode dispersive and unfiltered"]}
    write_json(out/"model.json",metrics)
    _plot(out,traces,freq,sg,se,fqubit,excitation,params)
    return metrics


def _plot(out,traces,freq,sg,se,fqubit,excitation,params):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    with plt.rc_context({"axes.spines.top":False,"axes.spines.right":False,"font.size":10}):
        fig,axs = plt.subplots(2,3,figsize=(13,7),layout="constrained")
        ax = axs[0,0]
        ax.plot(freq,20*np.log10(abs(sg)),label="qubit g",color="#1d4ed8")
        ax.plot(freq,20*np.log10(abs(se)),label="qubit e",color="#e87722")
        ax.set(xlabel="Readout (GHz)",ylabel="S21 (dB)",title="Conditional readout")
        ax.legend()
        axs[0,1].plot(sg.real,sg.imag,color="#1d4ed8")
        axs[0,1].plot(se.real,se.imag,color="#e87722")
        axs[0,1].set(xlabel="Re S21",ylabel="Im S21",title="Readout IQ")
        axs[0,2].plot(fqubit,excitation,color="#17a398")
        axs[0,2].set(xlabel="Drive (GHz)",ylabel="P(1)",title="CW qubit spectroscopy")
        for ax,(name,(t,p)) in zip(axs[1],traces.items()):
            observed = np.genfromtxt(out/f"{name}.csv",delimiter=",",names=True)
            ax.plot(t,observed["p1_observed"],".",markersize=2,alpha=.35,color="#64748b")
            ax.plot(t,p,color="#1d4ed8",linewidth=1.5)
            ax.set(xlabel="Time (us)",ylabel="P(1)",title=name.upper())
        fig.suptitle(f"Expected measurements | {params['source']} | coherence inputs assumed",fontsize=14)
        fig.savefig(out/"measurements.png",dpi=170)
        plt.close(fig)
