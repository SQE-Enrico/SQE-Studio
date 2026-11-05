# Roadmap di sviluppo

Le milestone e le issue sono il riferimento per gli incrementi. Commit e pull
request collegano codice ed evidenze; la CI pubblica automaticamente i risultati.

| Ordine | Milestone | Issue e risultato atteso |
|---|---|---|
| 1 | [Baseline e CI](https://github.com/SQE-Enrico/SQE-Studio/milestone/1) | [#1](https://github.com/SQE-Enrico/SQE-Studio/issues/1) - Baseline dev81 e prima CI Windows/Linux verificata |
| 2 | [Capacita elettrostatica nativa](https://github.com/SQE-Enrico/SQE-Studio/milestone/2) | [#2](https://github.com/SQE-Enrico/SQE-Studio/issues/2) - Matrice calcolata dal layout, conduttori e ground espliciti |
| 3 | [Transmon dal layout allo spettro](https://github.com/SQE-Enrico/SQE-Studio/milestone/3) | [#3](https://github.com/SQE-Enrico/SQE-Studio/issues/3) - Dati EM nativi, riduzione e scqubits fino alla UI |
| 4 | [Convergenza e sensibilita](https://github.com/SQE-Enrico/SQE-Studio/milestone/4) | [#4](https://github.com/SQE-Enrico/SQE-Studio/issues/4) - Mesh, dominio, materiali e stabilita della base |
| 5 | [Readout, EPR e ottimizzazione](https://github.com/SQE-Enrico/SQE-Studio/milestone/5) | [#5](https://github.com/SQE-Enrico/SQE-Studio/issues/5) - Benchmark multimodo verificati e osservabili utilizzabili nell'ottimizzazione |

Le issue contengono i criteri di completamento e i profili di test richiesti.
La chiusura tramite merge delle PR collegate aggiorna l'avanzamento delle milestone.
I dettagli del ciclo operativo sono in [DEVELOPMENT.md](DEVELOPMENT.md).

Il profilo `extraction` corrente usa una matrice EM fixture e scqubits reale.
La seconda e la terza milestone richiedono un nuovo controllo del flusso nativo
completo. Scientific qualification NOT_ESTABLISHED; fabrication HOLD.
