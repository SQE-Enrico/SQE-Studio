# SQE Studio 0.10.0 consolidation record

## Input and preserved features

Consolidated the uploaded SQE Studio workstation ZIP rather than regenerating a skeleton. Preserved existing scientific modules, revisioned job workflows, physical QPU schema, stage contracts, Gmsh/Palace and Quantum Metal bridges and optional Julia exporter.

## Distribution hygiene

Excluded `.venv`, runtime databases/setup-token, locally generated diagnostic ZIPs, real installation logs, outdated hotfix scripts/backups and Python bytecode caches. None of those belong in a reusable source distribution. Existing data from an older installed workstation must be backed up and migrated separately; overwriting it is never part of this release.

## Browser workflows

New `/control.html` provides standard/extended diagnostics, result history, per-check explanation and explicit ZIP download. The browser does not accept arbitrary commands, install packages or perform elevation. The existing Quantum Design Lab still provides experimental physical-design and Palace job workflows.

## Planned next phase

Validate Palace on the actual Ubuntu/WSL2 laptop using a reproducible reference problem. Capture solver input, mesh, raw output, versions, elapsed time, memory use and independent numerical error into the same report framework. Only after scientific qualification should an automatic extraction pipeline be presented as reliable.
