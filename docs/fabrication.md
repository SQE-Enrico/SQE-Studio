# From generated GDSII to a laboratory mask

The deliverable `device.gds` is a real positive-metal layout. It contains the base Al ground plane with CPW slots, two floating pads, coarse junction leads, a half-wave readout, feedline launch pads, a die-edge setback and annotation layers. It does **not** contain a qualified tunnel junction or a complete evaporation stencil. `fabrication.json` therefore remains `HOLD`, even if the illustrative configuration flag is changed.

## Layers and polarity

See [layers.csv](../technology/layers.csv). Layer 1/0 is **metal to retain/deposit**. A subtractive etch process usually needs the complementary pattern inside an approved write field. Lift-off polarity depends on resist and exposure process. Do not send layer 1 directly to an exposure tool without determining the correct polarity, bias, tone and ground-plane treatment.

Layers 90, 91 and 99 are annotations. Layer 91 is a junction location rectangle only; a colored marker is not a Josephson junction. Layer 99 is a thin die-outline frame, not a filled metal polygon. Ground metal has a configurable edge setback (100 µm in the example).

## Junction process integration

Use the electrical design's Ic, LJ and approximate area as targets. Obtain the laboratory's qualified single-/double-angle evaporation junction cell or another approved process primitive. Add explicit layers for deposited electrodes, overlaps/barrier, resist undercut, liftoff, bandages and alignment, as applicable. Validate electrode overlap and contact to the coarse leads, angular shadow geometry, oxidation calibration, dose bias and minimum features. Update both CAD and electrical Cj assumptions when the junction process changes.

The package does not turn Jc and area into a fabrication recipe. A nominal Al thickness alone does not define junction transparency, film disorder, contact cleaning, line loss or coherence.

## Assemble a lab-supplied junction mask

The implemented `assemble-mask` adapter accepts a separately supplied laboratory junction GDS. Copy `configs/process.example.json`, replace every placeholder, supply its exact SHA-256, contact electrode layers and left/right contact anchors, and set the process Ic/Cj consistent with the completed run. Relative GDS paths resolve against the process manifest. The cell origin must be the junction center, with horizontal contacts; no scaling or rotation is applied implicitly.

```bash
sqw assemble-mask --run build/demo --process configs/my-lab-process.json --out build/process-mask
```

This optional KLayout-Python route checks database-unit equality, cell checksum, electrical parameter agreement and that each declared electrode anchor lands within its coarse lead and a source electrode polygon. It preserves source layers and produces `process_candidate.gds` plus a provenance record. It still requires process DRC, barrier/overlap/evaporation/contact verification and job-deck review. No actual laboratory junction cell was provided, and this adapter's integration test is skipped when KLayout Python is absent. A generic illustrative contact test is not a fabricated junction validation.

## KLayout review

```bash
klayout build/demo/layout/device.gds -l technology/sqw.lyp
klayout -b -r technology/baseline.drc \
  -rd input=build/demo/layout/device.gds -rd output=build/demo/drc.lyrdb
```

The baseline deck checks 1 µm base-metal width/space and intersection with the outline annotation. It is a **smoke check**, has not been executed in the delivery environment, and is not an INRIM/foundry process deck. It does not check junction overlays, resist tone, density, dose, bandage contact, bridge clearance or connectivity of the final process-specific masks.

Review in KLayout: hierarchy, cell names, dimensions/units, absence of duplicate exposures, connectedness, ground continuity, port geometry, capacitive gaps, annotations excluded from write layers and sufficient die-edge clearance. Add the actual package grounding/bondwire or airbridge strategy; the example has no fabricated ground straps across its CPW.

## Reviewable handoff bundle

After qualification, archive the exact process-specific GDS and layer map, DRC result, junction/process identification, mask polarity and bias, fracture/job-deck settings, mesh convergence, expected parameter distributions, expected measurement report, independent benchmark comparison and source/dependency/native-solver versions. Assign the laboratory reviewer before converting this research starting point into an exposure job.

There is no command that automatically declares this generic layout tapeout-ready. The repository makes the remaining process work visible so that the software result and the laboratory's fabrication approval stay traceable.
