# Contributing

Create a branch, describe the physical/software problem, and include the smallest useful independent check. Run `python -m unittest discover -s tests -v` and regenerate an affected end-to-end example in a new output directory. Report optional integration skips and native tool versions explicitly.

Preserve unit-bearing keys, Maxwell sign/node conventions and provenance. Never promote synthetic data to experimental or FEM validation. Changes to a physical approximation need a documented limit/assumption and comparison against an independent result. Changes to masks need process review before fabrication.

Do not commit personal correspondence, credentials or restricted laboratory data. `data/private/`, build products and virtual environments are ignored. Reviewed small public benchmark artifacts may be committed with their provenance and license.

Dependency upgrades require an intentional environment requalification. Keep the original freeze/native solver versions with prior runs. Pull requests should explain the resulting behavior, how it was verified, and any remaining physical limitation.

Application changes must preserve per-project authorization, immutable inputs, checkpoint provenance and the distinction between numerical completion, user consolidation and process qualification. Add meaningful HTTP/worker tests for changes to these boundaries. Keep deployment secrets and studio-data out of Git. Maintainer: Emanuele Enrico, e.enrico@inrim.it.
