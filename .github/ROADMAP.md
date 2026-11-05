# Development roadmap

Milestones and issues define the increments. Commits and PRs link code to
evidence; CI publishes results automatically.

| Order | Milestone | Issue and expected outcome |
|---|---|---|
| 1 | [Baseline and CI](https://github.com/SQE-Enrico/SQE-Studio/milestone/1) | [#1](https://github.com/SQE-Enrico/SQE-Studio/issues/1) - Verified dev81 baseline and Windows/Linux CI |
| 2 | [Native electrostatic capacitance](https://github.com/SQE-Enrico/SQE-Studio/milestone/2) | [#2](https://github.com/SQE-Enrico/SQE-Studio/issues/2) - Layout-derived matrix with explicit pad and ground identities |
| 3 | [Single transmon: layout to spectrum](https://github.com/SQE-Enrico/SQE-Studio/milestone/3) | [#3](https://github.com/SQE-Enrico/SQE-Studio/issues/3) - Saved native EM data, reduction, scqubits and verified UI results |
| 4 | [Convergence and sensitivity](https://github.com/SQE-Enrico/SQE-Studio/milestone/4) | [#4](https://github.com/SQE-Enrico/SQE-Studio/issues/4) - Mesh, domain, material and basis stability |
| 5 | [Readout, EPR and optimization](https://github.com/SQE-Enrico/SQE-Studio/milestone/5) | [#5](https://github.com/SQE-Enrico/SQE-Studio/issues/5) - Verified multimode benchmarks and optimization observables |

Issues contain acceptance criteria and required test profiles. Merging linked
PRs closes completed issues and updates milestone progress. See
[DEVELOPMENT.md](DEVELOPMENT.md) for the working protocol.

The single-transmon implementation is described in
[SINGLE_TRANSMON.md](../SQE-Studio/docs/SINGLE_TRANSMON.md).
The extraction profile keeps its explicit EM fixture and genuine scqubits test.
Scientific qualification NOT_ESTABLISHED; fabrication HOLD.
