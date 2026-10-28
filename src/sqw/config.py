"""Strict unit-bearing configuration. Unknown keys are errors, including nested keys."""

import copy
import math
import tomllib
from pathlib import Path

DEFAULTS = {
    "schema_version": 1,
    "device": {"name": "al_si_transmon", "temperature_mK": 20.0,
               "band_min_GHz": 4.0, "band_max_GHz": 12.0},
    "materials": {"substrate": "high_resistivity_silicon", "epsilon_r": 11.45,
                  "substrate_thickness_um": 500.0, "aluminum_thickness_nm": 100.0,
                  "silicon_resistivity_ohm_cm": 10000.0, "al_gap_ueV": 180.0,
                  "junction_Jc_A_per_cm2": 50.0, "junction_specific_C_fF_per_um2": 45.0},
    "targets": {"f01_GHz": 5.0, "anharmonicity_MHz": -250.0,
                "readout_GHz": 7.2, "coupling_MHz": 80.0},
    "circuit": {"EJ_GHz": 14.5, "Cj_fF_override": 0.0, "ng": 0.0, "ncut": 35, "levels": 6,
                "resonator_Z_ohm": 50.0, "coupling_C_fF": 14.0},
    "layout": {"chip_size_um": 7000.0, "pad_width_um": 300.0,
               "chip_height_um": 7000.0,
               "die_edge_clearance_um": 100.0,
               "pad_height_um": 500.0, "pad_gap_um": 20.0, "pad_y_um": -400.0,
               "moat_um": 24.0, "cpw_width_um": 10.0, "cpw_gap_um": 6.0,
               "qubit_coupler_gap_um": 8.0, "feed_y_um": 1030.0,
               "readout_length_um": 8300.0, "feed_coupler_length_um": 300.0,
               "junction_lead_width_um": 4.0, "junction_em_gap_um": 2.0,
               "launcher_width_um": 180.0, "launcher_length_um": 300.0,
               "junction_mask_qualified": False},
    "em": {"air_height_um": 2000.0, "bottom_air_um": 1000.0,
           "box_margin_um": 500.0, "mesh_max_um": 350.0, "mesh_min_um": 2.0,
           "order": 2, "modes": 8, "eigen_target_GHz": 3.8, "linear_tol": 1e-8,
           "kinetic_Ls_pH_per_square": 0.0},
    "experiment": {"T1_intrinsic_us": 50.0, "Tphi_us": 80.0,
                   "readout_Qi": 200000.0, "readout_Qc": 12000.0,
                   "rabi_MHz": 5.0, "ramsey_detuning_MHz": 0.5,
                   "shots": 2048, "seed": 17, "assignment_p0_as_1": 0.02,
                   "assignment_p1_as_0": 0.04},
}


def validate(data):
    cfg = copy.deepcopy(DEFAULTS)
    for section, values in data.items():
        if section not in cfg:
            raise ValueError(f"Unknown section: {section}")
        if isinstance(cfg[section], dict):
            if not isinstance(values, dict):
                raise ValueError(f"{section} must be a table")
            for key, value in values.items():
                if key not in cfg[section]:
                    raise ValueError(f"Unknown key: {section}.{key}")
                cfg[section][key] = value
        else:
            cfg[section] = values
    if type(cfg["schema_version"]) is not int or cfg["schema_version"] != 1:
        raise ValueError("Unsupported schema_version")
    nonpositive = {"ng", "pad_y_um", "anharmonicity_MHz", "kinetic_Ls_pH_per_square", "Cj_fF_override",
                   "assignment_p0_as_1", "assignment_p1_as_0", "seed"}
    for section, values in cfg.items():
        if not isinstance(values, dict):
            continue
        for key, value in values.items():
            expected = DEFAULTS[section][key]
            if isinstance(expected, bool):
                if type(value) is not bool:
                    raise ValueError(f"{section}.{key} must be boolean")
            elif isinstance(expected, str):
                if not isinstance(value, str) or not value.strip():
                    raise ValueError(f"{section}.{key} must be nonempty text")
            else:
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise ValueError(f"{section}.{key} must be numeric")
                if not math.isfinite(value) or (key not in nonpositive and value <= 0):
                    raise ValueError(f"Invalid value for {section}.{key}")
                if isinstance(expected, int) and type(value) is not int:
                    raise ValueError(f"{section}.{key} must be an integer")
    d, c, e, l = (cfg[s] for s in ("device", "circuit", "experiment", "layout"))
    if d["band_min_GHz"] >= d["band_max_GHz"]:
        raise ValueError("Empty operating band")
    for key in ("f01_GHz", "readout_GHz"):
        if not d["band_min_GHz"] <= cfg["targets"][key] <= d["band_max_GHz"]:
            raise ValueError(f"Target {key} outside operating band")
    if cfg["targets"]["anharmonicity_MHz"] >= 0:
        raise ValueError("The transmon target requires negative anharmonicity")
    if c["ncut"] < 10 or not 3 <= c["levels"] < 2*c["ncut"]:
        raise ValueError("Insufficient charge basis or invalid level count")
    if c["Cj_fF_override"] < 0:
        raise ValueError("Junction capacitance override must be zero (automatic) or positive")
    if e["seed"] < 0 or any(not 0 <= e[k] < 0.5 for k in
                            ("assignment_p0_as_1", "assignment_p1_as_0")):
        raise ValueError("Invalid random seed or assignment probabilities")
    if cfg["em"]["kinetic_Ls_pH_per_square"] < 0:
        raise ValueError("Surface inductance cannot be negative")
    if l["junction_em_gap_um"] >= l["pad_gap_um"]:
        raise ValueError("JJ EM gap must be smaller than pad gap")
    return cfg


def load(path):
    with Path(path).open("rb") as stream:
        return validate(tomllib.load(stream))
