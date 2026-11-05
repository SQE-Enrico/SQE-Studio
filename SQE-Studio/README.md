# SQE Studio — modular edition / 0.1.1.dev81

Sviluppo locale dalla radice Git: `.\dev.ps1` esegue i controlli,
`.\dev.ps1 -Watch` li ripete dopo i salvataggi e `-Doctor` verifica i tool.
[Analisi e automazione](docs/AUTOMATION.md) descrive profili, CI e report.

Questa consegna riparte dal pacchetto dev78 e dal report allegato. Riorganizza
server, UI, test e istruzioni di sviluppo, senza cambiare i modelli numerici.
Lo storico di versioni, dispatch, autorizzazioni e ZIP annidati è stato tolto.

La verifica dei moduli legge ora esplicitamente UTF-8 anche su Windows.
L’ordine dei file usato nei fingerprint dei test è uniforme fra Windows e Linux.
Due regressioni riproducono questi casi senza cambiare i modelli numerici.

Estrai in una cartella nuova, apri **Launch SQE Studio.pyw** e mantieni
l'ambiente scientifico Windows già configurato. Lascia **Recommended** e premi
**Automatic Test** una volta. Per questa ristrutturazione il profilo predefinito
verifica software e HTTP; **Extraction** aggiunge scqubits sulla matrice fixture
esplicitamente dichiarata. CAD, Quantum, RF, campi e Palace restano selezionabili.
Invia lo ZIP numerato originale da `qualification-reports/`, anche con errori.

Per lavorare sul codice bastano [AGENTS.md](AGENTS.md),
[CURRENT_STATE.json](CURRENT_STATE.json) e una ricerca mirata:

```bash
python tools/context.py
python tools/context.py http
python tools/context.py --symbol sqe_studio.http_api.extraction:extract
```

Il server HTTP è diviso per risorsa. La UI ha moduli distinti e un solo elenco
ordinato; il programma serve automaticamente lo stesso script alla pagina.
Nessuna nuova dipendenza o compilazione frontend. I test sono raggruppati per
funzione; la verifica della sorgente usa soltanto lo stato corrente.

[Architettura](docs/ARCHITECTURE.md) · [Sviluppo](docs/DEVELOPMENT.md) ·
[Test](docs/TESTING.md) · [Stato scientifico](docs/SCIENCE.md) ·
[Ambiente nativo](docs/NATIVE_SETUP.md).

Il report dev78 conferma214 controlli e due casi scqubits reali, ma la matrice
EM del test era costruita. Questa consegna non contiene il percorso dev79
annunciato nella conversazione, che non è disponibile come sorgente allegato.
Il prossimo sviluppo scientifico rimane la matrice calcolata dal layout e poi
la quantizzazione. Scientific qualification NOT_ESTABLISHED; fabrication HOLD.
