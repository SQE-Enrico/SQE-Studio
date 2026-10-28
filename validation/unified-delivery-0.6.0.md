# SQE Studio 0.6 — matrice di verifica e limiti dell'ambiente

Data: 2026-10-28. Questa non è una qualification di prodotto o solver.

## Verifiche eseguibili sulla macchina di sviluppo

- Python: suite `PYTHONPATH=src python -m pytest -q` su Linux: **84 passed, 4 skipped, 9 subtests passed**; inoltre i 10 test `test_physical_qpu.py` e gli 11 test `test_quantumlab.py` passano con `unittest` come nel bootstrap Windows.
- Script: `python -m py_compile ...` e `node --check ...`.
- Layout/contratto 1/2/4: dimensioni, reti, tag, generazione positiva GDS,
  verifiche su livelli 1/91/92/99 e hash della geometria.
- JJ: modificare EJ non modifica erroneamente il GDS ma cambia il modello
  lineare Palace e l'hash della specifica.
- Circuito: stessi Q0...Qn, componenti e 2 porte per readout, rimozione dei
  coupler nominali non giustificati dalla geometria; etichetta `nominal`.
- Palace JSON: una sola RF excitation per ognuno dei `2*n` driver; rigore
  sui terminal indices e su LJ/Cj delle JJ.
- HTTP: URL di manifest/preview/GDS richiedono autenticazione.
- Persistenza: job `physical:package` realmente eseguito dallo scheduler,
  revision, output e SHA-256 successivo.
- Frontiera solver: un **eseguibile falso esplicitamente fittizio** serve a testare
  invocazione e controllo degli output; non misura capacità o frequenze reali.
- Sicurezza: CSV alterato successivamente viene rifiutato dall'estrazione.

## Verifiche non compiute in questo ambiente

- Compilazione/installazione reale di Palace con Spack in WSL2/Ubuntu Windows.
- Importabilità del wheel Gmsh nativo (rete e libreria non disponibili qui),
  generazione tet mesh/qualità geometrica e correttezza delle physical surfaces.
- Run reali Palace electrostatic/eigenmode/Driven sulle nuove 2/4 celle.
- Correttezza del `port-EPR.csv` della specifica versione Palace scelta.
- Importazione reale in Quantum Metal versione installata.
- DRC, fab signoff, comparazione con benchmark EM o dispositivo misurato.

L'assenza dei test sopra **impedisce di dichiarare la release FEM validata**.
Si consegna un'implementazione con contratto, toolchain e test automatici,
non una QPU fisicamente caratterizzata o un software scientificamente certificato.
