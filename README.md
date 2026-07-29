# NARATrace

Lokale, quellennahe Personensuche und Dokumentprüfung für historische Arbeit mit dem National Archives Catalog.

NARATrace ist ein unabhängiges, inoffizielles Forschungswerkzeug für digitalisierte Bestände der U.S. National Archives and Records Administration (NARA). Die Anwendung läuft lokal auf dem Rechner des Benutzers. Es gibt kein Cloud-Backend, keine Telemetrie und kein GitHub-Pages-Deployment.

Automatische Treffer sind Forschungshinweise und keine gesicherten Identifizierungen.

## Screenshots

### Startseite und Anzeige-Beispiel

Die Startseite zeigt direkt eine kompakte Demo-Trefferliste mit Quellenbadge, Trefferwahrscheinlichkeit und Personenfakten.
Neue Nutzer sehen dort außerdem den Forschungsworkflow vom eigenen API-Schlüssel bis zum exportierbaren Recherchebericht.

![Startseite mit Anzeige-Beispiel](docs/screenshots/01-start.png)

### Neue Suche

Das Suchformular erfasst Namen, Varianten, Lebensdaten, Orte, Mitgliedsnummern und archivische Eingrenzungen. Suchjobs laufen im Hintergrund, zeigen Fortschritt und können abgebrochen werden.

![Suchformular mit ausgefülltem Suchprofil](docs/screenshots/02-search-form.png)

### Lokale Dokumente

Lokale PDF-, Bild- und TIFF-Dateien können lokal analysiert werden. NARATrace erzeugt eine Browser-Vorschau, führt OCR aus und markiert Prüfbegriffe mit Fundstellen.

![Lokale Dokumentanalyse mit Vorschau und OCR](docs/screenshots/03-local-documents.png)

### Methodik

Der Methodik-Reiter erklärt den Workflow von Suchprofil über Kandidatenabruf und OCR bis zur quellenkritischen Prüfung.

![Methodik-Reiter mit Workflow-Schema](docs/screenshots/04-methodology.png)

## Funktionsumfang

- lokale FastAPI-Anwendung mit Svelte/Vite-Frontend
- lokale SQLite-Datenbank über Alembic
- NARA Catalog API v2 mit lokal gespeichertem API-Schlüssel
- asynchrone Suchjobs mit Fortschritt, Laufzeit, Restzeit und Abbruch
- gerankte Trefferlisten mit Evidenzhinweisen
- Suchverläufe mit lokal gespeicherten Treffern
- Markdown-Rechercheberichte mit Suchprofil, Abfragen, Treffer- und Evidenzdokumentation
- Originalseitenanzeige mit TIFF-zu-JPEG-Konvertierung für den Browser
- Transkriptansicht und manuelle Transkriptkorrektur
- lokale Dokumentanalyse für PDF, PNG, JPEG, TIFF, WebP und GIF
- lokale OCR mit Tesseract, falls auf dem System verfügbar
- Methodikseite mit Workflow-Schema und Grenzen der automatischen Bewertung

## Datenquelle

Datenquelle ist die U.S. National Archives and Records Administration - National Archives Catalog.

NARATrace verwendet die National Archives Catalog API v2, sobald ein persönlicher API-Schlüssel gespeichert ist. Echte Suchergebnisse dürfen nicht erfunden werden. Demo- und Mock-Daten sind ausdrücklich gekennzeichnet.

Die offizielle API-Dokumentation liegt unter:

```text
https://catalog.archives.gov/api/v2/api-docs/
```

Einen API-Schlüssel fordert man laut NARA über `Catalog_API@nara.gov` an.

## Lokaler Start

Voraussetzungen:

- Python 3.11 oder neuer
- Node.js 22 oder neuer
- Tesseract OCR, wenn lokale OCR genutzt werden soll

Backend installieren:

```powershell
python -m pip install -e .\backend[test]
```

Frontend bauen:

```powershell
cd frontend
npm install
npm run build
cd ..
```

Anwendung starten:

```powershell
python -m naratrace
```

Der Server bindet standardmäßig nur an `127.0.0.1` und verwendet Port `8765`.

Falls der Port belegt ist:

```powershell
python -m naratrace --port 8766
```

Ohne Browserstart:

```powershell
python -m naratrace --no-browser
```

Windows-Schnellstart:

```powershell
.\quickstart.bat
```

Das Batch-Skript baut das Frontend und startet NARATrace auf Port `8766`.

## API-Schlüssel

Der NARA-API-Schlüssel wird lokal im Betriebssystem-Keyring gespeichert:

- Service: `NARATrace`
- Account: `nara-api-key`

Für Entwicklung ist alternativ die Umgebungsvariable `NARA_API_KEY` vorgesehen. Der Schlüssel darf nicht in SQLite, Browser Local Storage, Frontend-Code, Logs, Tests, Git-Commits oder Exporte geschrieben werden.

In der Oberfläche unter `Einstellungen` kann der Schlüssel lokal gespeichert, getestet und gelöscht werden. Ohne gültigen persönlichen NARA API-Schlüssel kann NARATrace keine echten Treffer aus dem National Archives Catalog abrufen.

Siehe `.env.example` für lokale Entwicklungsvariablen ohne echte Geheimnisse.

Eine kompakte Anleitung für neue Nutzer liegt unter [docs/USER-GUIDE.md](docs/USER-GUIDE.md).

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

## Methodik und Quellenkritik

NARATrace darf keine Person allein aufgrund eines ähnlichen Namens sicher identifizieren. Das Ranking kombiniert Namen, Varianten, Orte, Lebensdaten, Mitgliedsnummern, Metadaten, NARA Extracted Text und lokale OCR. Je mehr unabhängige Merkmale konsistent zusammenpassen, desto plausibler wird ein Treffer.

Weitere Notizen:

- [Nutzeranleitung](docs/USER-GUIDE.md)
- [Suchmethodik](docs/SEARCH-METHODOLOGY.md)
- [NARA-Attribution](docs/NARA-ATTRIBUTION.md)

## Tests

Kompletter Projekttest:

```powershell
.\scripts\test.ps1
```

Backend direkt:

```powershell
python -m pytest .\backend\tests
```

Frontend direkt:

```powershell
cd frontend
npm run test -- --run
```

## Grenzen

OCR-Text kann fehlerhaft sein. Archivische Metadaten, Rechtehinweise und Zitierweisen müssen für wissenschaftliche Nutzung am Originaldatensatz geprüft werden. NARATrace ist ein unabhängiges, inoffizielles Forschungswerkzeug. Es steht nicht in Verbindung mit NARA und wird nicht von NARA betrieben oder unterstützt.
