# Process and mask candidates

The process form is versioned with each project revision. It includes chip width/height, wafer diameter, edge exclusion, dicing streets, write-field size, minimum base-metal dimensions, minimum junction dimensions, overlay tolerance, electrode layers, Jc and specific junction capacitance. Device layout and material inputs remain available in the device form.

The current scientific geometry provider supports rectangular dies around the existing floating-transmon/readout template. Changing die dimensions does not automatically invent a new routing topology; a template that no longer fits is rejected before launch. Arbitrary reference GDS files can be stored as assets, but are not automatically reconstructed into simulation conductors or ports.

## Junction sources

**Parametric overlap candidate** constructs two Al electrode layers with a specified linewidth, overlap and coarse-contact bridge. The same width × overlap area drives both the drawing and the forward electrical model: Ic = Jc × area, EJ = ℏIc/(2e), and Cj = specific capacitance × area. The process preview reports Ic, EJ/h and Cj. These resolved values override the duplicate EJ/Cj engine inputs in a Studio project, so changing the junction geometry updates the expected spectrum. The generated plan-view drawing is a design intent, not a Dolan/Manhattan evaporation stencil. It has no qualified undercut, resist thickness, dose, shadow evaporation, oxidation or bandage process.

**Laboratory GDS cell** uses an uploaded junction asset. Declare its top cell, electrode contact layers, horizontal anchors and calibrated/declared Ic and Cj. Declared Ic determines EJ, and declared Cj is used independently of the area-based capacitance approximation. The Jc-inferred area is an effective electrical estimate, not a measurement of an uploaded polygon. The worker verifies the source checksum, database units, contact landing and agreement with the resolved circuit model within 5%, using the existing KLayout assembly adapter. The original source cell travels with the result. This route is blocked in the workflow map if KLayout is unavailable; the optional integration has not been run in the delivery environment.

The declared process minimum and overlay tolerance are stored for review. The current validation checks a limited set of numeric width/gap/contact constraints. It is not a complete laboratory DRC/overlay/evaporation checker. An uploaded cell may contain additional source layers; inspect their mapping before exposure.

## Accessory geometry

Alignment crosses, identification lettering and raster logos are emitted as real polygon rectangles on an annotation/accessory layer. Font pixels and logos are vectorized at bounded resolution and checked against the declared minimum feature width and die boundary. Increase the physical size if a converted feature is too small. Select a raster logo in the process form after uploading it. These accessories are excluded from the EM conductor model; placing them into an electrically relevant process layer requires a reviewed geometry-provider extension.

The junction illustration in the browser is a schematic, not a scale-accurate mask viewer. Inspect the exported GDS in KLayout before fabrication.

## Outputs

The process phase writes `chip_candidate.gds`, a hierarchical `wafer_candidate.gds`, a `wafer_map.csv`, a local `write_field_plan.csv` and `process_review.json`. Wafer placement includes a complete half-street envelope around each die and rejects dies that cross the usable circular edge. The write-field CSV is a planning aid, not writer-specific fracture or a job deck. Wafer flats/notches and rotation-specific mounting constraints are not modeled in this release.

A laboratory-cell assembly also preserves its source GDS, manifest and contact-validation result. Every output remains `PROCESS_REVIEW_REQUIRED`. A process input flag or a user-consolidated workflow phase does not change that status automatically. See [fabrication handoff](fabrication.md) for the laboratory-specific work that remains.
