# Sviluppo e test locali automatici

Analisi del 5 novembre 2026: il progetto corrente e' `0.1.1.dev81`, con server
Python locale, SQLite/revisioni immutabili, UI JavaScript modulare senza build
frontend e adapter verso i motori scientifici. La separazione tra HTTP, UI,
orchestrazione e provenienza permette gia' verifiche per area. Automatic Test
dispone di selezione, dipendenze, timeout, esecuzione isolata e ZIP numerati.

Il report Windows dev81 `SQE-RC14_12-report-0001.zip` era gia' positivo. Il nuovo
report `0002` ripete con successo integrita', controlli mirati e HTTP nel runtime
scientifico Python 3.11 locale prima delle modifiche all'automazione.

I problemi trovati e affrontati:

- La CI era sotto `SQE-Studio/.github/`, mentre la radice Git e' la cartella
  esterna. Il workflow attivo ora vive in `.github/workflows/ci.yml` alla radice
  e imposta la corretta directory di lavoro.
- Il runner CLI restituiva zero quando un task era BLOCKED. Ora zero richiede
  PASS per tutti i task selezionati; errori e incompletezza restano distinguibili.
- Mancava un ciclo da terminale che aggiornasse i fingerprint software,
  eseguisse anche i controller UI e ripartisse dopo un salvataggio.
- Un import diretto di Playwright interrompeva la raccolta della suite quando
  il pacchetto opzionale mancava. Ora il motivo e' uno skip visibile nella suite
  portabile; selezionare esplicitamente Browser continua a dare BLOCKED.
- La CI copriva soltanto Linux e non conservava i report. Ora include Windows
  Python 3.11 e Linux Python 3.11/3.12/3.13, browser e installazione wheel isolata.
- La regressione completa ha trovato un riferimento residuo a `tests/A17`,
  un percorso del piano ricavato dal vecchio modulo server e il vecchio testo
  di un errore ZIP. Questi test ora puntano ai proprietari attuali, mantenendo
  le stesse verifiche di corruzione, identita' e prenotazione tra processi.
- Il test di corruzione dello snapshot di ottimizzazione scriveva nel posto
  sbagliato. Ora verifica l'esistenza e altera lo snapshot reale, con sei casi
  distinti. Il comportamento produttivo di rifiuto resta invariato.
- Il runner portabile ora assegna a ogni gruppo un'area temporanea esterna
  ai sorgenti, mantenendo il vincolo degli screenshot anche nei test annidati.
- Il test dei job aveva un'attesa di 55 secondi anche con un vero motore
  scientifico installato, contro i 180 secondi ammessi dall'applicazione. Ora
  prova separatamente l'assenza reale del motore (worker Python senza
  site-packages) e il motore nativo, con il budget produttivo e la verifica del
  manifest reale. Non vengono prodotti risultati scientifici sostitutivi.
- Git conserva i byte dei file inventariati, compresi i manifest CRLF prodotti
  da Windows. La normalizzazione automatica dei terminatori cambierebbe gli hash
  tra la macchina di sviluppo e la CI. Gli attributi ora impediscono questa
  trasformazione, mantenendo i normali diff testuali del codice.

## Comandi dalla radice del repository

```powershell
.\dev.ps1 -Doctor
.\dev.ps1
.\dev.ps1 -Watch
.\dev.ps1 -Profile software
.\dev.ps1 -Profile extraction
```

`dev.ps1` seleziona l'ambiente scientifico gia' associato a questa cartella;
in alternativa usa `.venv`, `py -3.11` o `python`. `-Python <percorso>` seleziona
esplicitamente un interprete. Non installa pacchetti e non modifica il Python
di sistema. `-Doctor` mostra interprete e disponibilita' dei moduli senza
importare i motori o affermare che siano funzionanti.

Per i controller UI usa Node dal PATH oppure il Node gia' incluso in Playwright,
anche da un terminale PowerShell che non eredita gli strumenti di Codex.
Gli extra di sviluppo includono esplicitamente setuptools e wheel: il build
isolato di `pip install -e` non garantisce che siano disponibili al successivo
build offline nell'interprete attivo.

Il comando predefinito aggiorna i fingerprint software tramite lo strumento
esistente, esegue i tre gruppi di controller UI in Node, poi Recommended:
integrita', test mirati e HTTP autenticato. Il refresh mantiene tutti i pin
numerici e i contratti congelati; una loro modifica interrompe il ciclo.

`-Watch` esegue subito il controllo e poi lo ripete dopo i salvataggi, accorpando
le scritture ravvicinate. Ignora cache, ambienti, report e build. Esegue un ciclo
alla volta in un nuovo interprete; un salvataggio durante i test richiede un nuovo
giro, che carica anche le modifiche al runner stesso. Ctrl+C richiede l'arresto
dopo il task corrente, conservando il report. La modalita'
continua supporta Recommended/Quick; i profili costosi si eseguono separatamente.
Il watcher dura finche' il terminale resta aperto. Non viene installato un servizio
o un avvio automatico del computer.

Su Linux o da un Python gia' selezionato:

```bash
python tools/dev.py --doctor
python tools/dev.py --watch
python tools/dev.py --check --profile software
```

Questi comandi Python partono dalla cartella interna `SQE-Studio/`.

## Risultati e requisiti

| Codice | Significato |
|---|---|
| 0 | Controlli UI e tutti i task scelti passati, sorgenti stabili |
| 1 | Test o refresh fallito |
| 2 | Blocco, timeout, prova mancante o sorgenti cambiate durante i test |
| 130 | Interruzione da tastiera |

`qualification-reports/local-latest.json` e' il riepilogo per gli strumenti;
lo ZIP numerato resta la prova immutabile di Automatic Test. Gli skip delle
dipendenze native nella suite portabile restano visibili e non sono prove
di esecuzione scientifica. Il profilo `software` richiede pytest, strumenti build,
Node, Playwright e Chromium; aggiunge regressioni di tutti i domini, browser reale
e wheel costruita/installata offline in un nuovo ambiente.

Per preparare un ambiente di sviluppo separato, se serve, installare gli extra
`.[dev,browser]` e poi `python -m playwright install chromium`. Il setup grafico
esistente ha gia' l'opzione Playwright + Chromium. Nessun download avviene durante
il comando dei test. Un tool mancante deve essere installato nel Python mostrato
da `-Doctor`, oppure il controllo rimane esplicitamente bloccato.

La CI usa `--check`: verifica i fingerprint committati e non li riscrive. Su push,
pull request o avvio manuale esegue lo stesso profilo software e conserva gli ZIP
anche in caso di errore. La verifica remota richiede il commit/push delle modifiche.

## Verifica sulla macchina Windows

Il profilo `software` ha completato tutti i 15 gruppi della suite: **1757 passed,
23 skipped**, zero errori. Le esclusioni riguardano condizioni dichiarate, fra
cui permessi symlink, un caso POSIX, comportamenti di assenza quando un pacchetto
e' invece presente ed evidenze native esterne non distribuite.

Passano inoltre i **62 controlli Node** dei controller UI, il browser Chromium
reale, HTTP autenticato e la costruzione/installazione offline della wheel in un
ambiente isolato. I cinque task selezionati sono PASS, senza BLOCKED o TIMEOUT.
Il controllo dei job ha eseguito sia l'assenza reale del motore sia scqubits reale.

Report: `qualification-reports/SQE-RC14_12-report-0005.zip`, Python 3.11.9,
durata 994.48 secondi (circa 16 minuti e 34 secondi), sorgenti stabili durante il
controllo. I 53 file numerici/core restano identici ai pin. I tempi variano con
carico e import dei backend; Recommended e' il ciclo previsto per i salvataggi.
La CI remota e le altre versioni Python non sono state eseguite in questa sessione.

## Prossimi passi

1. Usare Recommended e i test dell'area durante ogni modifica, `software` prima
   di integrare, il profilo nativo pertinente quando si tocca un adapter.
2. Misurare tempi e instabilita' della suite completa sulla macchina e correggere
   le regressioni emerse, senza trasformare skip o tool mancanti in PASS.
3. Aggiungere test end-to-end dei flussi scientifici realmente implementati:
   layout, capacita' con identita' conduttori/ground, quantizzazione, sensibilita'.
4. Solo se utile, collegare una macchina di test dedicata ai job remoti. Il ciclo
   locale su salvataggio e' gia' disponibile senza runner residente o credenziali.

Resta separato il lavoro sul prodotto: la capacita' calcolata dal layout e i
benchmark EPR richiedono ancora evidenza scientifica. Scientific qualification
NOT_ESTABLISHED; fabrication HOLD.

Riferimenti: [posizione dei workflow GitHub](https://docs.github.com/en/actions/how-tos/write-workflows/use-workflow-templates),
[Playwright in CI](https://playwright.dev/python/docs/ci),
[driver Node incluso in Playwright](https://github.com/microsoft/playwright-python/blob/main/playwright/_impl/_driver.py),
[skip espliciti pytest](https://docs.pytest.org/en/stable/how-to/skipping.html).
