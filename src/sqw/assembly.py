"""Attach a lab-supplied process junction to the shared chip without rescaling it."""

from pathlib import Path

import numpy as np

from .io import read_json, sha256, write_json
from .provenance import check_stage


def assemble(run_directory, process_manifest, output_directory):
    import klayout.db as kdb

    run, manifest_path, out = map(Path,(run_directory,process_manifest,output_directory))
    state = read_json(run/"run.json")
    check_stage(state,"layout",run)
    check_stage(state,"quantize",run)
    process = read_json(manifest_path)
    required = {"schema_version","process_name","process_version","junction_gds","junction_cell",
                "junction_gds_sha256","contact_layers","left_anchor_um","right_anchor_um",
                "Ic_nA","Cj_fF","electrical_tolerance_relative"}
    if set(process) != required or process["schema_version"] != 1:
        raise ValueError("Process manifest must match configs/process.example.json exactly")
    src_path = manifest_path.parent/process["junction_gds"]
    if sha256(src_path) != process["junction_gds_sha256"]:
        raise ValueError("Process cell checksum mismatch")
    parameters = read_json(run/"parameters.json")
    cfg = read_json(run/"resolved_config.json")
    geometry = read_json(run/"layout/geometry.json")
    if parameters["geometry_sha256"] != geometry["geometry_sha256"]:
        raise ValueError("Run geometry / parameter mismatch")
    tolerance = float(process["electrical_tolerance_relative"])
    if not 0<tolerance<=.2:
        raise ValueError("Electrical matching tolerance must be >0 and <=20%")
    for key in ("Ic_nA","Cj_fF"):
        if not np.isclose(process[key],parameters["junction"][key],rtol=tolerance,atol=0):
            raise ValueError(f"Process {key} differs from electrical model; update configuration and rerun")
    base,source = kdb.Layout(),kdb.Layout()
    base.read(str(run/"layout/device.gds"))
    source.read(str(src_path))
    if abs(base.dbu-source.dbu)>1e-12:
        raise ValueError("Process and base GDS database units must match; no implicit rescaling")
    if len(base.top_cells()) != 1:
        raise ValueError("Expected a single top cell in the base layout")
    top = base.top_cells()[0]
    cell = source.cell(process["junction_cell"])
    if cell is None:
        raise ValueError("Declared junction cell is absent")
    layers = process["contact_layers"]
    if len(layers) != 2 or any(len(pair)!=2 for pair in layers):
        raise ValueError("Declare one contact layer/datatype for each junction electrode")
    p = cfg["layout"]
    for index,key in enumerate(("left_anchor_um","right_anchor_um")):
        x,y = process[key]
        # Cell origin is JJ center; no rotation or scaling is hidden in this adapter.
        left = -p["pad_gap_um"]/2 < x < -p["junction_em_gap_um"]/2
        right = p["junction_em_gap_um"]/2 < x < p["pad_gap_um"]/2
        if not (left if index==0 else right) or abs(y)>=p["junction_lead_width_um"]/2:
            raise ValueError(f"{key} does not land inside its coarse Al lead")
        layer_index = source.find_layer(*layers[index])
        if layer_index is None:
            raise ValueError("Declared electrode contact layer is absent")
        region = kdb.Region(cell.begin_shapes_rec(layer_index)).merged()
        point = kdb.Point(round(x/source.dbu),round(y/source.dbu))
        if not any(poly.inside(point) for poly in region.each()):
            raise ValueError(f"{key} does not lie in an electrode polygon")
    if out.exists() and any(out.iterdir()):
        raise ValueError("Mask assembly requires a fresh output directory")
    out.mkdir(parents=True,exist_ok=True)
    copied = base.create_cell("LAB_PROCESS_JUNCTION")
    copied.copy_tree(cell)
    cy = p["pad_y_um"]
    top.insert(kdb.CellInstArray(copied.cell_index(),kdb.Trans(0,round(cy/base.dbu))))
    # All source layers are preserved. Annotations must be filtered by the lab job deck.
    base.write(str(out/"process_candidate.gds"))
    write_json(out/"assembly.json",{"status":"PROCESS_REVIEW_REQUIRED",
                "process_name":process["process_name"],"process_version":process["process_version"],
                "process_manifest_sha256":sha256(manifest_path),"process_cell_sha256":sha256(src_path),
                "base_gds_sha256":sha256(run/"layout/device.gds"),
                "output_sha256":sha256(out/"process_candidate.gds"),
                "checks":["same database unit","electrical targets match within declared tolerance",
                          "electrode anchors fall in coarse leads and source electrode polygons"],
                "remaining":["Process DRC and final connectivity","Tone/bias/fracture review",
                             "Barrier/evaporation and bandage verification","Laboratory sign-off"]})
