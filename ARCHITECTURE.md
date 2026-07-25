# ARCHITECTURE - NARATrace

## Zielbild

NARATrace ist eine vollständig lokale Forschungsanwendung zur quellenahen Personensuche im National Archives Catalog der U.S. National Archives and Records Administration (NARA). Das System besteht aus einem Python/FastAPI-Backend, einem Svelte/TypeScript-Frontend und lokaler SQLite-Datenhaltung.

Die Anwendung bindet standardmäßig nur an `127.0.0.1:8765`. Es gibt kein Cloud-Backend, keine Telemetrie und keine automatische Datenübertragung an externe Dienste außerhalb bewusst ausgelöster NARA-Catalog-Aufrufe.

## Komponenten

Backend:

- `naratrace.main`: FastAPI-App, Health-Endpunkt, lokale Statusseite und spätere statische Frontend-Auslieferung.
- `naratrace.launcher`: lokaler Startprozess, Datenverzeichnisinitialisierung, Migrationen, Serverstart und Browseröffnung.
- `naratrace.core`: Konfiguration, lokale Pfade, Secret-Zugriff und gemeinsame Konstanten.
- `naratrace.database`: SQLAlchemy-Modelle, Session-Konfiguration und Alembic-Initialisierung.
- `naratrace.nara`: späterer gekapselter Client für die NARA Catalog API v2.
- `naratrace.matching`: spätere Normalisierung, Query Expansion, Evidence-Erzeugung und Ranking.
- `naratrace.ocr`: spätere OCR-Provider für NARA-Text, Transkriptionen, Tesseract und Mock-Modus.
- `naratrace.export`: spätere lokale Exporte.

Frontend:

- `frontend/src`: Svelte/TypeScript-Anwendung.
- `frontend/src/lib`: API-Client, UI-Hilfen, Typen.
- `frontend/src/components`: wiederverwendbare Komponenten.
- `frontend/src/routes`: spätere Ansichten für Start, Suche, Verläufe, lokale Dokumente, Einstellungen, Methodik und Über.
- `frontend/static`: statische Assets ohne NARA-Logo oder offizielles Siegel.

## Lokale Datenhaltung

Lokale Benutzerdaten liegen außerhalb des Repositorys. Der Pfad wird über `platformdirs` bestimmt und kann für Entwicklung mit `NARATRACE_DATA_DIR` überschrieben werden.

Unter Windows ist das Standardziel:

```text
%LOCALAPPDATA%\NARATrace\
```

Unterverzeichnisse:

- `database/` für SQLite
- `cache/` für API- und Verarbeitungscache
- `documents/` für bewusst gespeicherte Dokumente
- `thumbnails/` für Vorschaubilder
- `ocr/` für OCR-Arbeitsdateien
- `exports/` für lokale Exporte
- `logs/` für lokale Logs ohne Geheimnisse
- `temp/` für temporäre Dateien

## Datenbank

SQLite ist die lokale Persistenzschicht. SQLAlchemy modelliert die Domain-Objekte, Alembic verwaltet Migrationen.

Initiale Modelle:

- `SearchJob`
- `SearchProfile`
- `SearchField`
- `SearchVariant`
- `SearchQuery`
- `CandidateRecord`
- `DigitalObject`
- `CandidatePage`
- `ExtractedText`
- `MatchEvidence`
- `SearchResult`
- `ManualCorrection`
- `ApplicationSetting`
- `CacheEntry`

## Startablauf

`python -m naratrace` führt aus:

1. Konfiguration laden.
2. Host auf lokale Bindung prüfen.
3. Datenverzeichnisse anlegen.
4. SQLite-Datenbankpfad bestimmen.
5. Alembic-Migrationen ausführen.
6. FastAPI via Uvicorn starten.
7. `/api/health` pollen.
8. Standardbrowser mit `http://127.0.0.1:8765` öffnen.

## Sicherheitsgrenzen

- Standardbindung nur an `127.0.0.1`.
- API-Schlüssel nicht im Frontend, nicht in SQLite und nicht in Logs.
- Keyring vor Umgebungsvariable, Umgebungsvariable nur für Entwicklung.
- Keine externen Analytics- oder OCR-Dienste.
- NARA-Daten müssen als NARA-Daten gekennzeichnet werden.
- Automatisches Matching erzeugt Forschungshinweise, keine gesicherten Identifizierungen.

## NARA-Client

Der NARA-Client wird in einem späteren Schritt unter `naratrace.nara` implementiert. Vor der Umsetzung wird die aktuelle Swagger-Dokumentation der NARA Catalog API v2 geprüft. Der Client wird asynchrone `httpx`-Aufrufe, Timeouts, Backoff, 429-Behandlung, Pagination, Cache, Pydantic-Validierung und strukturierte Fehlerobjekte kapseln.

## OCR-Provider

Geplante Provider:

- `NaraTranscriptionProvider`
- `NaraExtractedTextProvider`
- `TesseractOcrProvider`
- `MockOcrProvider`

Textquellen werden getrennt gespeichert und sichtbar gekennzeichnet.

## Matching-Pipeline

Geplante Phasen:

1. Query Expansion
2. Candidate Retrieval
3. Metadatenbewertung
4. Textbewertung
5. begrenzte Tiefensuche
6. Ranking mit positiver und negativer Evidenz

NARATrace darf keine Identität allein aufgrund ähnlicher Namen behaupten.

## Frontend-Build

Das Svelte-Frontend wird später mit Vite gebaut. FastAPI liefert den Produktions-Build aus `frontend/dist` als statische lokale Anwendung aus. Bis dahin liefert das Backend eine einfache lokale Statusseite aus.

## Packaging

Der erste MVP läuft als lokaler Python-Start. Ein PyInstaller-Build für Windows ist ein späterer Meilenstein.
