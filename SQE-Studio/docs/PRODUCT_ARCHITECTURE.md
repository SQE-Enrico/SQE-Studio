# Product architecture — current canonical description

SQE Studio is **one design-led GUI and one native computation graph**, serving superconducting QPU, microwave, RF and nonlinear-circuit families. The application is not an experiment registry, a series of dedicated demos, or a collection of unrelated solver windows. The GUI is a view/controller over saved, revisioned `sqe.project.v1` designs. Solver outputs are native and evidence-checked; the designer iterates the project.

For **binding design principles** see [DEVELOPER_PRINCIPLES.md](DEVELOPER_PRINCIPLES.md), for the module ownership, future typed edges and priorities see [EDA_EXTENSION_ARCHITECTURE.md](EDA_EXTENSION_ARCHITECTURE.md), and for specific literature-driven acceptance cases see [SCIENTIFIC_DESIGN_CASES.md](SCIENTIFIC_DESIGN_CASES.md).

Original foundation contracts and agent protocol remain unchanged. A01 typed quantities and A06 job/artifact checks must not be bypassed by a new UI, example or optimizer. A missing engine/physical mapping is a blocked edge; fabrication remains HOLD. The current symbolic layout preview is not native QGeometry, and a completed unit test is not a scientific validation.
