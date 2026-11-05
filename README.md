# SQE Studio

Piattaforma locale per progettazione quantum EDA, orchestrazione dei motori
scientifici, revisioni immutabili e verifica della provenienza dei risultati.
Il progetto Python e la documentazione tecnica sono nella cartella [SQE-Studio](SQE-Studio/README.md).

## Sviluppo e test

Dalla radice del repository:

```powershell
.\dev.ps1 -Doctor
.\dev.ps1 -Watch
```

Il watcher esegue Recommended dopo i salvataggi. Per la suite completa, arrestare
il watcher con Ctrl+C e usare `.\dev.ps1 -Profile software`.

Le modifiche seguono [issue e milestone](.github/ROADMAP.md), una branch dedicata
e una pull request. [GitHub Actions](https://github.com/SQE-Enrico/SQE-Studio/actions)
esegue controlli su commit e PR e conserva riepiloghi e report scaricabili.
Il [protocollo di sviluppo](.github/DEVELOPMENT.md) descrive come collegare test,
commit, PR e completamento delle issue.

La [baseline locale verificata](.github/evidence/local-baseline.json) registra
1757 test superati, 23 saltati e 62 controlli dei controller UI, oltre al browser
reale e all'installazione isolata della wheel. Le evidenze native e i criteri
fisici restano distinti dalla CI software.

Scientific qualification NOT_ESTABLISHED; fabrication HOLD.
