# R1 / v0.8 — Esame della convergenza del solver Palace

1. Avvia SQE Studio su Windows e configura Palace/WSL2.
2. Apri Quantum Design Lab → QPU fisica unificata. Configura un transmon
   single-layer da 1 Q; controlla l'anteprima e salva una revisione.
3. Esegui prima `package`, quindi `mesh` ed eventualmente `electrostatic`.
4. Se il solver è presente, usa `convergence-electrostatic` come job separato.
   Questo genera tre configurazioni Palace: `convergence-electrostatic-L0`,
   `L1`, `L2`, ognuna con `UniformLevels` differenti. Le simulazioni possono
   richiedere molta RAM e tempo; non avviarle su layout grandi come primo test.
5. Apri il job: il file `physical/convergence-electrostatic-report.json`
   contiene gli hash, i dati di ogni livello, gli scostamenti e il flag
   `numerically_converged`. Una simulazione completata può non convergere.
6. Prova `convergence-eigenmode` separatamente; ricorda che il matching per
   indice non rileva anticrossing. Un risultato 'pass' NON certifica la
   corrispondenza fisica dei modi.
7. Se compare errore di solver/mesh, conserva `*.log`, `solve-*.json`, `mesh.json`
   e i CSV. Non sostituire mai il calcolo con un output fittizio.

Per il contratto dei risultati, vedere `docs/roadmap-quantumpro-open-eda.md`.
