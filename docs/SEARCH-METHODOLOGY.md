# Suchmethodik

NARATrace erzeugt keine gesicherten Identifizierungen. Das Tool bewertet Kandidaten als Forschungshinweise und macht sichtbar, welche Evidenzen für oder gegen einen Treffer sprechen.

## Workflow

1. **Suchprofil erfassen**
   Namen, Varianten, Geburtsdaten, Orte, Mitgliedsnummern, NAID und Record Group werden als strukturierte Suchfelder gespeichert.

2. **Normalisieren und Varianten bilden**
   Schreibweisen werden bereinigt. Bindestriche, Leerzeichen, Punkte und Nummernvarianten werden so verarbeitet, dass NARA-Abfragen nicht unnötig eng werden.

3. **NARA-Catalog-Abfragen ausführen**
   Der Suchjob ruft Kandidaten über die National Archives Catalog API v2 ab. Der persönliche API-Schlüssel des Nutzers wird lokal gelesen und nicht protokolliert.

4. **Originalmaterial und Textquellen sichern**
   NARATrace bevorzugt NARA Extracted Text. Falls darstellbare Digitalobjekte vorhanden sind, werden sie lokal gecacht. Browser-inkompatible TIFFs werden als Anzeige-JPEG bereitgestellt, während OCR möglichst auf dem Originalbild läuft.

5. **Evidenzen bewerten**
   Mehrere unabhängige Übereinstimmungen zählen stärker als Namensähnlichkeit allein. Beispiele:
   - Name und Namensvarianten
   - Geburtsdatum oder Jahr
   - Wohnorte
   - Mitgliedsnummern
   - Record Group oder NAID
   - Treffer im NARA-Text oder in lokaler OCR

6. **Treffer ranken**
   Kandidaten werden nach Plausibilität sortiert. Der Score ist eine Arbeitspriorisierung, kein Beweis.

7. **Quellenkritisch prüfen**
   Nutzer prüfen Originalseite, Transkript, Evidenzliste und NARA-Datensatz. Manuelle Transkriptkorrekturen werden lokal gespeichert.

8. **Bericht exportieren**
   Der Markdown-Recherchebericht dokumentiert Suchprofil, Abfragen, Treffer, Evidenzen, Transkript und Grenzen.

## Positive und negative Evidenz

Positive Evidenz erhöht die Plausibilität, wenn unabhängige Merkmale zusammenpassen. Negative Evidenz senkt die Plausibilität, wenn Angaben widersprechen oder nur sehr schwache Ähnlichkeiten vorliegen.

Ein Name allein reicht nicht. Ein Treffer mit ähnlichem Namen, passender Mitgliedsnummer und passendem Ort ist stärker als ein Treffer mit exakt gleichem Namen, aber widersprechendem Geburtsdatum.

## Grenzen

- OCR kann falsche Zeichen, Namen oder Nummern erzeugen.
- NARA-Metadaten können unvollständig sein.
- Nicht jedes Digitalobjekt ist als Browserbild darstellbar.
- Gleichnamige Personen können hohe Namensähnlichkeit erzeugen.
- Fehlende Treffer bedeuten nicht, dass keine Quelle existiert.
- Exportierte Berichte sind Arbeitsnotizen und ersetzen keine Zitierprüfung am Originaldatensatz.
