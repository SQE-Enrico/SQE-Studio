# Validazione SQE Studio 0.8.0 — 28 ottobre 2026

- Test: `PYTHONPATH=src python -m unittest discover -s tests -q`:
  **110 eseguiti, 0 errori/fallimenti, 4 saltati** (dipendenze opzionali).
- `node --check src/sqw/studio/static/quantumlab.js`: passato.
- Export CLI JosephsonCircuits dal file esempio QPU-01: file Julia e manifest
  prodotti; esportazione del package fisico parametrico 2Q: file `circuit.jl`
  e sidecar prodotto.
- Bridge Jacobian HB / `JosephsonCircuits.hbsolve`: **NON TESTATO**; backend
  Julia non disponibile nel laboratorio di consegna.
- Setup Windows/WSL2, `Gmsh` 3D reale, esecuzione Palace reale: **NON TESTATI**;
  tool nativi assenti nel laboratorio di consegna.
- I nuovi test Palace usano esclusivamente CSV e record di solver di prova,
  specificamente etichettati `Palace-TEST-DOUBLE`; non danno prove di precisione
  scientifica o di un'installazione Palace funzionante.
- Il nuovo studio di convergenza NON dimostra fedeltà degli stack 3D né
  corretta mappatura delle JJ e delle porte, perché quello richiede R2/R3.
- Nessun sign-off della fabbricazione o equivalenza ad ADS QuantumPro.
