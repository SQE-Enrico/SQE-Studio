"""Single approved scientific-engine registry; no dynamic imports from requests."""
from . import scqubits_adapter, quantum_metal_adapter, sqdmetal_palace_adapter, josephson_adapter
REGISTRY={
 'scqubits': scqubits_adapter.run,
 'quantum_metal': quantum_metal_adapter.run,
 'sqdmetal_palace': sqdmetal_palace_adapter.run,
 'josephson_circuits': josephson_adapter.run,
}
