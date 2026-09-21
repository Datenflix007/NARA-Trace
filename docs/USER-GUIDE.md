# NARATrace Nutzeranleitung

NARATrace ist ein lokales Recherchewerkzeug. Treffer sind prüfbare Hinweise, keine automatisch gesicherten Identifizierungen.

## Installation und Schlüssel

```powershell
python -m pip install -e .\backend[test]
cd frontend
npm install
npm run build
cd ..
python -m naratrace --port 8766
```

Hinterlege deinen persönlichen NARA-Catalog-API-Schlüssel unter **Einstellungen** und prüfe ihn dort. Er bleibt im Betriebssystem-Keyring, nie im Browser, in SQLite oder im Export. Das A3340 Open Dataset ist ein separater öffentlicher Datenweg; dafür ist kein Catalog-Key erforderlich.

Für den ersten vollständigen A3340-Durchlauf kann der lokale Textindex bewusst vorab aufgebaut werden. Das lädt alle offiziellen MFKL- und MFOK-Roll-JSON-Dateien, aber keine Massenkopie der Kartenbilder:

```powershell
python -m naratrace --index-a3340
```

Oder unter Windows direkt:

```powershell
.\quickstart.bat index
```

Der Befehl ist fortsetzbar; nur noch nicht indexierte Rollen werden geladen. `--refresh-a3340-index` baut den Textindex bewusst neu auf. `.\quickstart.bat all` indiziert zuerst und startet anschließend die Anwendung.

## Bulk-Download der offiziellen Rohdaten

Der A3340-Datensatz liegt laut NARA oeffentlich im AWS-S3-Bucket `s3://nara-nsdap` (Region `us-east-2`). Fuer die Recherche ist der eingebaute Gesamtindex normalerweise vorzuziehen: Er uebernimmt die JSON-Metadaten samt OCR, aber keine Bildmassen.

Wenn ein eigener Rohdatenbestand benoetigt wird, bereitet dieses Skript einen fortsetzbaren AWS-CLI-Sync vor (AWS CLI v2 erforderlich):

```powershell
.\scripts\bulk-nsdap.ps1 -Destination D:\NARATrace-NSDAP -Mode Metadata
```

`Metadata` laedt nur JSON-Dateien. Ein Vollsync mit TIFFs und PDFs wird erst mit zwei bewussten Argumenten freigegeben:

```powershell
.\scripts\bulk-nsdap.ps1 -Destination E:\NARATrace-NSDAP-vollbestand -Mode FullDataset -ConfirmFullDataset
```

Der Vollbestand ist sehr gross; NARA empfiehlt dafuer externen Speicher. Diese Bulk-Aktion startet keinen NARA-Catalog-API-Abruf und braucht keinen persoenlichen API-Schluessel.

## Suche anlegen

1. Öffne **Neue Suche** und trage mindestens einen Nachnamen ein.
2. Ergänze Vorname, Geburtsdatum/-jahr, bekannte Orte, Namensvarianten oder Mitgliedsnummer nur, wenn sie quellenbasiert sind.
3. Starte den Suchjob und prüfe Status, Warnungen und gespeicherte Abfragen.

Bei einer Personensuche prüft NARATrace zuerst den öffentlichen A3340-MFKL-Karteiindex. Ein A3340-Treffer öffnet immer den konkreten Kartenframe mit Originalbild, Transkript, Frame- und Rollenprovenienz - nie ein vollständiges Rollen-PDF mit hunderten oder tausenden Seiten. Nur wenn dort kein Kartenframe vorliegt, folgt der Catalog-Weg (mit API-Schlüssel).

Fundstellen im Transkript werden anhand der Suchnamen, Varianten und einer eingegebenen Mitgliedsnummer markiert. Die Markierung macht den textlichen Hinweis sichtbar; sie ist kein Identitätsnachweis.

## Treffer quellenkritisch prüfen

Prüfe nie nur den Score. Öffne die Detailansicht und vergleiche:

- Originalseite beziehungsweise NARA-Catalog-Ansicht;
- Transkript und eine eventuelle manuelle Korrektur;
- NAID, Serie, Quelle und Abrufkontext;
- bei A3340: MFKL/MFOK, Rolle, Frame, `objectFilename`, Original-URL und OCR-Herkunft;
- positive wie negative Evidenzen.

Ein hoher Name-Score ohne passende unabhängige Merkmale ist kein Identitätsnachweis. Unklare OCR, fehlende Bilder, Netzwerkfehler oder keine Kandidaten müssen als solche erkennbar bleiben.

## Lokale Dokumente, Verläufe und Exporte

**Lokale Dokumente** verarbeitet PDF-, Bild- und TIFF-Dateien auf dem lokalen Rechner. **Suchverläufe** öffnen, löschen oder exportieren vergangene Jobs. Die manuelle Transkriptkorrektur ist eine lokale Annotation; sie überschreibt weder das Original noch die dokumentierte NARA-Textquelle.

Weitere Hintergründe: [Suchmethodik](SEARCH-METHODOLOGY.md), [NARA-Architektur](NARA_Architekture.md) und [Programmarchitektur](TRAXER_Architekture.md).
