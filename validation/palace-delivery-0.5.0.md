# Verifica di consegna — SQE Studio / Quantum Metal + Palace 0.5.0

Data: 2026-10-28. Ambiente disponibile per verifica: container Linux Python 3.13, NumPy/SciPy e Node.js. **Windows/WSL2/Spack/Palace/Gmsh Python/Quantum Metal reali non erano disponibili**, quindi non si attribuisce loro un collaudo in hardware.

## Test eseguiti

La suite del progetto viene eseguita con:

```bash
PYTHONPATH=src python -m unittest discover -s tests -q
node --check src/sqw/studio/static/quantumlab.js
bash -n scripts/install_palace_wsl.sh scripts/palace-wsl-run.sh
python -m compileall -q src/sqw tests/test_palace_metal.py
```

**78 test**, nessun errore, **4 skip** opzionali. (I test finali si riportano nell'output del runner della consegna.) La suite preesistente comprende regressioni scientifiche, bootstrap, endpoint API, revisioni/job/capsule, scheduler, tracciabilità e controlli di produzione; nuove verifiche v0.5:

1. Validazione del layout unico e conversioni µm→mm degli esatti poligoni rettangolari.
2. Validazione dell'`manifest_sha256` e rifiuto di dati modificati.
3. Conversione QGeometry *con moduli Quantum Metal simulati*, per verificare invocazioni `QComponent` e 5 reti senza affermare un'installazione reale.
4. JSON Palace: 4 problemi, `L0`, porti 50 Ω e sweep driven multieccitazione.
5. Pianificazione e dipendenze delle fasi FEM, rifiuto target non permessi.
6. Command routing Palace Linux/Windows-WSL2, distro e path con spazi testati usando mocking.
7. Script runner bash reale con **solutore fittizio**: copie input, esecuzione in directory effimera, ritorno CSV, rifiuto sovrascrittura.
8. `run_palace` con subprocess fittizio, output verificato, hash e rilevazione di manomissione del CSV.
9. API Palace/Quantum Metal protette e checksum identico tra anteprima mesh e QGeometry.

Le unit test non equivalgono a esecuzione Palace. È obbligatorio un collaudo WSL reale prima della prima simulazione scientifica.

## Test non eseguibili qui / da fare su Windows reale

- **Installer**: `WINDOWS-FIRST-START.cmd`, firma dell'installer Python, dipendenze PyPI e Gmsh nativo Windows, primo avvio senza privilegi, avvii ripetuti e login effettivo in browser.
- **Ubuntu/Spack**: `wsl --install`, primo utente, password sudo, Spack `releases/v1.2`, effettiva compilazione ed esecuzione di `palace -h`; processi MPI a 1, 2, 4 rank.
- **End-to-end scientifico**: Gmsh OCC 3D sulla geometria default, import MSH v2.2, solutori Electrostatic/Eigenmode/Driven, estrazione CSV, campi ParaView, mesh convergence. Un JSON conforme allo schema non significa condizioni al contorno fisicamente giuste o convergenza numerica.
- **Quantum Metal reale**: installazione Windows di `quantum-metal[mesh]` in `.venv-metal` e import `QComponent/QGeometry` effettivo.
- **Browser**: rendering interattivo di tutti i pannelli, tabelle CSV, layout e form, upload/export e download Windows; la sintassi JavaScript è verificata ma l'esecuzione UI non è collaudata con browser reale in questo ambiente.

## Gate di accettazione per il laboratorio

- Pass: Web/worker locali con autorizzazioni, job successivi e salvataggio delle revisioni.
- Pass: percorso diretto `wsl -d Ubuntu -- bash -lc 'source ~/.sqe/spack/share/spack/setup-env.sh;spack load palace;palace -h'` senza interventi manuali o errori.
- Pass: impostazione Gmsh e un job `mesh` con tag e `geometry_sha256` coerenti.
- Pass: 3 raffittimenti di mesh con Cij, eigenmode e S(f) convergenti secondo tolleranze scientifiche fissate dal laboratorio; archivio dei file di controllo.
- Pass: modulo Quantum Metal installato e corrispondenza aree e connettività di un caso di riferimento con la geometria SQE.
- Pass: gestione job interrotti, errori Spack/solver/mesh, restart del Web senza perdere dati.
- **Non accettare** una QPU multi-qubit come layout FEM senza un modello unico schema↔geometria e verifica delle interconnessioni.

## Stato delle funzioni

| Funzione | Stato comprovato in questa consegna |
|---|---|
| UI/API schemi e simulazioni ridotte | Coperto dalle regression test; rendering manuale Windows da fare |
| Layout parametrico singolo transmon/CPW | Geometria realizzata e anteprima SVG; Gmsh OCC nativo da collaudare |
| JSON Palace Electrostatic/Eigenmode/Linearized/Driven | Generati e unit-tested contro requisiti e schema documentato |
| Engine Palace nativo Linux/WSL | Adattatore e workflow funzionanti con stub; binario reale non disponibile |
| WSL2 guided install | Script predisposti e bash sintatticamente verificato; da provare su Windows |
| QGeometry Quantum Metal | Manifest e chiamate API mock-tested; libreria effettiva opzionale non testata |
| EPR multiJJ/BBQ, packaging 3D, mesh multi-QPU | Non implementati / non qualificati |
| Remoto HPC multiworker | Migrazione monohost prevista, non scheduler distribuito |

Nessuna tabella o metrica fittizia viene inserita al posto di un output Palace reale. I report di produzione rimangono fabrication **HOLD**.
