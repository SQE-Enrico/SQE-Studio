# Importable Studio projects

In the browser sidebar, select **Import project capsule** and choose one of these files:

| Capsule | What to inspect |
|---|---|
| `al-si-research.sqe.zip` | Three finalized jobs: an analytical circuit/report, a T1 change with compatible-stage reuse, and chip/wafer process candidates. Includes immutable revisions, logs, parameters, plots and GDSII. |
| `unfinished-study.sqe.zip` | An intentionally incomplete saved draft. The missing qubit frequency is visible as an execution blocker; fill it in and continue. |

The first example uses Al on high-resistivity Si at 20 mK, a 7 × 7 mm die and a 100 mm illustrative wafer. Its capacitance model is an uncalibrated analytical surrogate. Junction, lithography and wafer values are examples, not an INRiM process specification. Neither capsule contains the account/session database, passwords, an activated macro, measured-device data or a fabrication approval.

After import, inspect the historical reports and artifacts, consolidate a phase with your own review, then change T1 and run using the latest finalized **report** job as an explicit checkpoint. Compatible scientific stages can be retained. If the installed engine source or dependency versions differ from the capsule, reuse is conservatively rejected and the requested stages are recomputed. Historical files remain available.

The capsule with process candidates contains `chip_candidate.gds`, `wafer_candidate.gds`, `wafer_map.csv`, `write_field_plan.csv` and `process_review.json`. Open these in the simulation's artifact list. The GDS remains a review candidate; write-field planning does not generate a machine-specific exposure job deck.

To rebuild both capsules from current source, run `python examples/studio/build_example.py` from the repository root. The builder creates temporary local identity state and exports only the project research state. See also [the browser guide](../../docs/studio-user-guide.md) and [the independent process module example](../modules/07_process_and_wafer.py).
