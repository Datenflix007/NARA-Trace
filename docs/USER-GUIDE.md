# NARATrace Nutzeranleitung

Diese Anleitung richtet sich an Nutzer, die NARATrace lokal mit einem eigenen NARA API-Schlüssel einsetzen wollen.

## 1. Lokale Installation

```powershell
python -m pip install -e .\backend[test]
cd frontend
npm install
npm run build
cd ..
python -m naratrace
```

Wenn Port `8765` belegt ist:

```powershell
python -m naratrace --port 8766
```

Unter Windows kann alternativ `quickstart.bat` genutzt werden. Das Skript baut das Frontend und startet NARATrace auf Port `8766`.

## 2. Eigenen NARA API-Schlüssel einrichten

1. Öffne den Reiter `Einstellungen`.
2. Trage deinen persönlichen NARA API-Schlüssel ein.
3. Speichere den Schlüssel.
4. Führe `Schlüssel testen` aus.

Der Schlüssel wird lokal im Betriebssystem-Keyring gespeichert. Er wird nicht in Suchverläufe, Exporte, Screenshots, SQLite oder Frontend-Code geschrieben.

Für Entwicklung kann alternativ eine lokale Umgebungsvariable gesetzt werden:

```powershell
$env:NARA_API_KEY="dein-schluessel"
```

## 3. Personensuche durchführen

1. Öffne `Neue Suche`.
2. Trage mindestens einen Nachnamen ein.
3. Ergänze unabhängige Merkmale: Vorname, Namensvarianten, Geburtsdaten, Wohnorte, Mitgliedsnummern, Record Group oder NAID.
4. Starte den Suchjob.
5. Beobachte Fortschritt, Suchlaufzeit, Restzeit und Status.
6. Brich den Job ab, wenn die Anfrage falsch angelegt wurde oder zu breit läuft.

Je enger und unabhängiger die Angaben sind, desto besser kann NARATrace Kandidaten bewerten.

## 4. Treffer prüfen

Die Trefferliste ist eine Plausibilitätsrangfolge. Öffne Treffer in der Vollansicht und prüfe:

- Originalseite oder NARA-Catalog-Vorschau
- NAID und Titel
- Record Group oder Serie
- Trefferwahrscheinlichkeit
- Evidenzliste
- OCR beziehungsweise NARA Extracted Text
- manuelle Transkriptkorrekturen

Ein Treffer ist erst belastbar, wenn die Quelle selbst geprüft wurde.

## 5. Suchverläufe nutzen

Unter `Suchverläufe` werden abgeschlossene und abgebrochene Suchjobs lokal gespeichert. Dort kannst du:

- frühere Suchläufe wieder öffnen
- Treffer nach Wahrscheinlichkeit prüfen
- einzelne Treffer löschen
- komplette Suchläufe löschen
- den Suchlauf als Markdown-Recherchebericht exportieren

Der Bericht enthält Suchprofil, gespeicherte Abfragen, Treffer, Evidenzen, Transkript und Grenzen der automatischen Identifizierung.

## 6. Lokale Dokumente prüfen

Der Reiter `Lokale Dokumente` ist für lokale PDF-, Bild- und TIFF-Dateien gedacht, die noch nicht aus einem NARA-Suchjob stammen.

1. Datei auswählen.
2. Prüfbegriffe eintragen.
3. Dokument analysieren.
4. Vorschau, OCR-Text und Fundstellen prüfen.

Die Datei bleibt lokal im NARATrace-Datenverzeichnis.

## 7. Grenzen

NARATrace ersetzt keine quellenkritische Archivarbeit. Häufige Problemfälle:

- OCR erkennt Namen oder Nummern falsch.
- NARA-Metadaten sind unvollständig.
- Gleichnamige Personen erzeugen plausible, aber falsche Treffer.
- Digitalisate fehlen oder sind im Browser nicht direkt darstellbar.
- Ein hoher Score ist kein Identitätsnachweis.

Für wissenschaftliche Nutzung müssen Originaldatensatz, Rechtehinweise und Zitierweise direkt bei NARA geprüft werden.
