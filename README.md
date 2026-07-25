# NARATrace

Lokale, quellennahe Personensuche im National Archives Catalog.

NARATrace ist ein unabhängiges, inoffizielles Forschungswerkzeug für historische Archivarbeit mit digitalisierten Beständen der U.S. National Archives and Records Administration (NARA). Die Anwendung läuft lokal auf dem Rechner des Benutzers. Es gibt kein Cloud-Backend, keine Telemetrie und kein GitHub-Pages-Deployment.

## Status

Dieses Repository befindet sich im ersten MVP-Aufbau. Aktuell vorhanden:

- lokale Backend-Grundstruktur mit FastAPI
- lokales Datenverzeichnis über `platformdirs`
- SQLite-Initialisierung über Alembic
- Health-Endpunkt unter `/api/health`
- lokaler Launcher für `python -m naratrace`
- Start-, Build- und Test-Skripte
- minimales Svelte/Vite-Gerüst für den nächsten Meilenstein

## Datenquelle

Datenquelle: U.S. National Archives and Records Administration - National Archives Catalog.

NARATrace verwendet perspektivisch die National Archives Catalog API v2. Echte Suchergebnisse dürfen nicht erfunden werden. Ein ausdrücklich gekennzeichneter Mock-Modus ist für Entwicklung und Demonstration vorgesehen.

## Lokaler Start

Voraussetzungen:

- Python 3.11 oder neuer
- Node.js 22 oder neuer für das Frontend
- Tesseract OCR für spätere lokale OCR-Funktionen

Backend installieren:

```powershell
python -m pip install -e .\backend[test]
```

Anwendung starten:

```powershell
python -m naratrace
```

Der Server bindet standardmäßig nur an `127.0.0.1` und verwendet Port `8765`. Beim Start wird der Standardbrowser mit `http://127.0.0.1:8765` geöffnet.

Ohne Browserstart:

```powershell
python -m naratrace --no-browser
```

Entwicklungsstart per Skript:

```powershell
.\scripts\dev.ps1
```

## Lokale Daten

Benutzerdaten werden nicht im Repository gespeichert. NARATrace verwendet das lokale Betriebssystem-Datenverzeichnis. Unter Windows ist das standardmäßig:

```text
%LOCALAPPDATA%\NARATrace\
```

Darin werden angelegt:

- `database/`
- `cache/`
- `documents/`
- `thumbnails/`
- `ocr/`
- `exports/`
- `logs/`
- `temp/`

Für Entwicklung und Tests kann das Datenverzeichnis mit `NARATRACE_DATA_DIR` überschrieben werden.

## API-Schlüssel

Der NARA-API-Schlüssel wird später bevorzugt im Betriebssystem-Keyring gespeichert:

- Service: `NARATrace`
- Account: `nara-api-key`

Für Entwicklung ist die Umgebungsvariable `NARA_API_KEY` vorgesehen. Der Schlüssel darf nicht in SQLite, Browser Local Storage, Frontend-Code, Logs, Tests, Git-Commits oder Exporte geschrieben werden.

In der Oberfläche unter `Einstellungen` kann der Schlüssel lokal gespeichert, getestet und gelöscht werden. Ohne gültigen persönlichen NARA API-Schlüssel kann NARATrace keine echten Treffer aus dem National Archives Catalog abrufen.

Einen API-Schlüssel fordert man laut NARA über `Catalog_API@nara.gov` an. Die offizielle API-Dokumentation liegt unter:

```text
https://catalog.archives.gov/api/v2/api-docs/
```

Siehe `.env.example` für lokale Entwicklungsvariablen ohne echte Geheimnisse.

## Tests

Backend:

```powershell
.\scripts\test.ps1
```

Direkt:

```powershell
python -m pytest .\backend\tests
```

Frontend-Tests werden ergänzt, sobald die Svelte-Oberfläche im nächsten Meilenstein ausgebaut ist.

## Grenzen

Automatische Treffer in NARATrace sind Forschungshinweise und keine gesicherten Identifizierungen. OCR-Text kann fehlerhaft sein. Archivische Metadaten, Rechtehinweise und Zitierweisen müssen für wissenschaftliche Nutzung am Originaldatensatz geprüft werden.

NARATrace ist ein unabhängiges, inoffizielles Forschungswerkzeug. Es steht nicht in Verbindung mit der U.S. National Archives and Records Administration und wird nicht von NARA betrieben oder unterstützt.
