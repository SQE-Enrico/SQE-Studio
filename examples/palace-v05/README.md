# Esempio v0.5 — input Palace, QGeometry, singolo transmon

Gli `.json` in questa cartella sono generati dal **modello fisico predefinito** del progetto. Contengono etichette e condizioni per `Electrostatic`, `Eigenmode`, `Eigenmode` con giunzione linearizzata `LJ/Cj`, e sweep `Driven` con 61 frequenze e 2 eccitazioni port1/port2. `geometry.json` e `qmetal-positive-mask.json` hanno lo **stesso identificatore** `geometry_sha256`.

Il file mesh 3D `device.msh` è **intenzionalmente assente**: non è stato calcolato o validato in questo container. Per eseguire realmente i JSON bisogna prima generare la mesh usando il job Web *Gmsh* e la configurazione geometrica corrispondente, poi utilizzare il solver Palace WSL o nativo. Non modificare direttamente la geometria dopo la mesh: il worker verifica SHA della geometria e del mesh file.

Per rigenerare le configurazioni localmente:

```python
from pathlib import Path
from sqw.studio.process import document,resolve
from sqw.geometry import build
from sqw.em import export_configs
from sqw.qmetal_interop import manifest
from sqw.io import write_json
cfg,_=resolve(document())
geo=build(cfg)
export_configs(cfg,geo,Path('my-em'))
write_json(Path('my-em/qmetal-positive-mask.json'),manifest(cfg))
```

Leggi `docs/palace-windows.md` e `docs/quantum-metal-integration.md`. Le geometrie e i parametri non sono risultati di una misura sperimentale e non qualificano la fabbricazione.
