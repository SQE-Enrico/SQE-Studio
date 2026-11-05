# Sviluppo tracciato su GitHub

Ogni incremento parte da una issue con risultato atteso, criteri di completamento
e test richiesti. La roadmap raccoglie le issue nelle cinque milestone del progetto.

1. Lavorare su una branch `codex/<numero-issue>-<argomento>`.
2. Eseguire test mirati e Recommended nella macchina scientifica. A funzionalita
   completata eseguire `software` e i profili nativi richiesti dall'issue.
3. Creare commit descrittivi e pubblicare la branch dopo i controlli pertinenti.
4. Creare o aggiornare una PR collegata con `Refs #numero`. Usare `Closes #numero`
   quando tutti i criteri dell'issue sono verificati.
5. Controllare la CI della revisione corrente, correggere gli errori e aggiornare
   la PR con report ed esclusioni. L'integrazione avviene mediante merge della PR.

Push e pull request avviano GitHub Actions. Ogni job mostra commit, ambiente,
famiglie di test, domini della regressione e report scaricabili, anche su errore.
Le issue collegate con `Closes` si chiudono al merge nella branch predefinita;
GitHub aggiorna automaticamente l'avanzamento della relativa milestone.

Gli agenti che lavorano su questo repository mantengono issue e PR aggiornate a
ogni incremento verificato, includendo i risultati locali quando eseguono test
nativi. La pubblicazione di commit e PR fa parte del ciclo di sviluppo richiesto;
il merge richiede un'istruzione dell'utente. I controlli periodici da chat non sono
parte di questa configurazione.

La CI ospitata su GitHub installa gli strumenti software e browser. I backend
scientifici della workstation sono verificati con i profili locali pertinenti.
Un PASS software e gli skip in CI non costituiscono qualificazione fisica.
I file numerici/core restano protetti e ogni loro cambiamento richiede una
revisione scientifica corrente con riferimenti primari e benchmark significativi.

Gli extra `dev` includono NumPy e SciPy nelle versioni della workstation verificata:
i test di compatibilita delle matrici sparse devono poter essere raccolti anche
su un runner pulito, indipendentemente dalla presenza di scqubits.
