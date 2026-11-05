# Automatic Test and local checks

Per lo sviluppo dalla radice Git: `.\dev.ps1` esegue i controlli locali;
`.\dev.ps1 -Watch` li rilancia dopo i salvataggi. `-Profile software` aggiunge
regressioni complete, browser reale e installazione wheel isolata.
Il riepilogo e' `qualification-reports/local-latest.json`; lo ZIP numerato rimane
il report di Automatic Test. Zero significa completato con successo; 1 indica
errore, 2 blocco/incompletezza. Vedi [automazione locale](AUTOMATION.md).

Estrai in una cartella nuova e usa l'ambiente scientifico già configurato.
Click **Automatic Test** once. Per questa ristrutturazione lascia Recommended,
che esegue integrità, controlli mirati e HTTP. Invia il file originale numerato,
per esempio `qualification-reports/SQE-RC14_12-report-0001.zip`.

| Profilo | Quando usarlo | Evidenza |
|---|---|---|
| Recommended / Quick | Refactor, HTTP, provenienza e moduli UI | Software/HTTP |
| Extraction | Cambi nel ponte capacità → spettro | Matrice EM fixture + scqubits reale |
| Quantum | Modelli e stabilità della base | Scqubits nativo e confronti di riferimento |
| CAD | Ricette Quantum Metal / GDS | Geometria nativa |
| Fields / Field compare | Lettori e confronto dei campi | Fixture VTK dichiarate |
| EM / Convergence | Cambi nella simulazione elettromagnetica | Solve Palace nativo |
| RF | Circuiti JosephsonCircuits.jl | Backend Julia nativo |
| Milestone | Verifica ampia quando necessaria | Famiglie selezionate, esclusioni visibili |

Il menu permette di scegliere le famiglie. L'AI deve indicare quale profilo
serve e quale report inviare, senza richiedere tutti i solve a ogni ciclo.
Budget globale3600s, riserva report120s, un job nativo alla volta.
Gli strumenti mancanti danno BLOCKED; le famiglie escluse sono esplicite.
Un PASS software non dimostra accuratezza EM o validità del dispositivo.

Controlli locali per dominio:

```bash
python -m unittest discover -s tests/core -p 'test_current_*.py'
python -m unittest discover -s tests/quantum -p test_basis_references.py
python -m unittest discover -s tests/fields -p test_reader_contracts.py
python -m unittest discover -s tests/fields -p test_field_comparison.py
python -m unittest discover -s tests/extraction -p test_conditional_transmon.py
node scripts/m17_ui_qa.cjs
node scripts/m18_ui_qa.cjs
node scripts/m19_ui_qa.cjs
python scripts/portable_regression.py
```

L'ultimo comando richiede pytest e copre tutti i test firmati per dominio;
Playwright e backend scientifici opzionali hanno disponibilità dichiarata.
I controlli Node eseguono le funzioni UI reali in VM, non un browser reale.
Un test con provider iniettato verifica il protocollo, non un risultato fisico.
I nomi m17/m18/m19 dei tre script identificano ancora i gruppi di regressione;
non implicano dipendenza da vecchi pacchetti o documentazione storica.
