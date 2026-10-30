"""Declared scientific artifact graph; edges never imply a numerical conversion.

The scheduler only selects work. A native adapter or a separately reviewed
conversion implementation must materialize every output; this module does not.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Iterable, Mapping
from .artifacts import valid_sha


class GraphBlocked(ValueError):
    """A required artifact, revision, mapping or review is unavailable."""


@dataclass(frozen=True)
class Stage:
    id: str
    output_type: str
    parents: tuple[str, ...]
    owner: str
    engine: str | None = None
    review_gate: str | None = None
    # The baseline has no verified execution contract for the graph bridges.
    available_in_foundation: bool = False


STAGES = (
    Stage('qdesign', 'quantum_metal.qdesign_recipe', (), 'A02', 'quantum_metal'),
    Stage('gds', 'quantum_metal.gdsii', ('qdesign',), 'A02', 'quantum_metal'),
    Stage('mesh', 'gmsh.mesh', ('qdesign',), 'A03', 'sqdmetal_palace', 'qdesign_to_mesh'),
    Stage('deck', 'palace.deck', ('mesh',), 'A03', 'sqdmetal_palace', 'mesh_to_deck'),
    Stage('em_modes', 'palace.eigenmodes', ('deck',), 'A03', 'sqdmetal_palace'),
    Stage('em_ports', 'palace.sparameters', ('deck',), 'A03', 'sqdmetal_palace', 'verified_em_ports'),
    Stage('em_capacitance', 'palace.capacitance_matrix', ('deck',), 'A03', 'sqdmetal_palace'),
    Stage('quantum_map', 'validation.report', ('em_modes', 'em_capacitance'), 'A01',
          review_gate='quantization_parameter_mapping'),
    Stage('quantum_native', 'scqubits.spectrum', ('quantum_map',), 'A04', 'scqubits'),
    Stage('netlist', 'circuit.netlist', (), 'A01', review_gate='verified_schematic_netlist'),
    Stage('circuit_native', 'josephson.sparameters', ('netlist',), 'A05',
          'josephson_circuits', 'verified_josephson_ports'),
)


class ArtifactDAG:
    """Topological dependency scheduler over explicitly typed, immutable refs.

    ``capabilities`` must be supplied by trusted adapter/A01 integration, not
    by a user study. The foundation declares no graph bridges executable.
    Direct, explicitly parameterized scqubits studies remain a separate path.
    """

    def __init__(self, stages: Iterable[Stage] = STAGES):
        stages = tuple(stages)
        self.nodes = {n.id: n for n in stages}
        if len(self.nodes) != len(stages):
            raise ValueError('Duplicate DAG node')
        for node in self.nodes.values():
            if not node.output_type or any(p not in self.nodes for p in node.parents):
                raise ValueError('Unknown DAG dependency or artifact type')
        self.order = self._topological()

    def _topological(self) -> tuple[str, ...]:
        temporary, permanent, order = set(), set(), []

        def visit(node_id):
            if node_id in temporary:
                raise ValueError('Cycle in scientific artifact DAG')
            if node_id in permanent:
                return
            temporary.add(node_id)
            for parent in self.nodes[node_id].parents:
                visit(parent)
            temporary.remove(node_id)
            permanent.add(node_id)
            order.append(node_id)

        for node_id in self.nodes:
            visit(node_id)
        return tuple(order)

    def prerequisites(self, node_id: str) -> tuple[str, ...]:
        return self.nodes[node_id].parents

    def require_ready(self, node_id: str, provided: Mapping, *, revision_id: str,
                      project_digest: str, capabilities: Iterable[str] = (),
                      reviews: Mapping | None = None) -> tuple:
        """Select only fully reviewed, current inputs; never mark stale valid.

        Input refs are verified by ArtifactRepository first. Every ref must
        expose artifact_type/revision_id/project_digest/scientific_status.
        """
        node = self.nodes[node_id]
        parents = []
        for parent_id in node.parents:
            if parent_id not in provided:
                raise GraphBlocked(f'{node_id}: missing prerequisite {parent_id}')
            ref = provided[parent_id]
            expected = self.nodes[parent_id].output_type
            if ref.artifact_type != expected:
                raise GraphBlocked(f'{node_id}: {parent_id} type mismatch ({expected})')
            if ref.revision_id != revision_id or ref.project_digest != project_digest:
                raise GraphBlocked(f'{node_id}: {parent_id} belongs to an old or different revision')
            if ref.scientific_status not in ('review_required', 'reviewed') or not valid_sha(getattr(ref, 'manifest_sha256', None)):
                raise GraphBlocked(f'{node_id}: {parent_id} lacks verified native content evidence')
            if ref.artifact_type == 'validation.report' and ref.scientific_status != 'reviewed':
                raise GraphBlocked(f'{node_id}: {parent_id} requires a reviewed mapping report')
            parents.append(ref)
        if node.review_gate:
            review = (reviews or {}).get(node.review_gate)
            if (not isinstance(review, dict) or review.get('decision') != 'approved' or
                    not isinstance(review.get('reviewer'), str) or not review['reviewer'].strip() or
                    not valid_sha(review.get('evidence_sha256')) or
                    review.get('revision_id') != revision_id or
                    review.get('project_digest') != project_digest or
                    review.get('parent_manifest_sha256') != [p.manifest_sha256 for p in parents]):
                raise GraphBlocked(f'{node_id}: requires revision/parent-bound {node.review_gate} review')
        if not node.available_in_foundation and node_id not in set(capabilities):
            raise GraphBlocked(f'{node_id}: native typed adapter/conversion is not integrated (owner {node.owner})')
        return tuple(parents)

    def next_ready(self, provided: Mapping, *, revision_id: str, project_digest: str,
                   capabilities: Iterable[str] = (), reviews: Mapping | None = None) -> tuple[str, ...]:
        """Return executable nodes only, not hoped-for or simulated stages."""
        selected = []
        for node_id in self.order:
            if node_id in provided:
                continue
            try:
                self.require_ready(node_id, provided, revision_id=revision_id,
                                   project_digest=project_digest, capabilities=capabilities,
                                   reviews=reviews)
            except GraphBlocked:
                continue
            selected.append(node_id)
        return tuple(selected)
