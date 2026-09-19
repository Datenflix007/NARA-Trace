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
   Fuer schnelle Suchlaeufe werden Originalseiten und lokale OCR auf die staerksten Kandidaten begrenzt. Weitere plausible Treffer bleiben als Metadatenhinweise sichtbar und koennen ueber den NARA-Datensatz geprueft werden.
   Ausgewaehlte Quellenarten priorisieren passende Treffer, sind aber kein harter Ausschluss, wenn NARA einen Kandidaten wegen Volltext- oder OCR-Treffern hoch bewertet.

5. **Evidenzen bewerten**
   Mehrere unabhängige Übereinstimmungen zählen stärker als Namensähnlichkeit allein. Beispiele:
   - Name und Namensvarianten
   - Geburtsdatum oder Jahr
   - Wohnorte
   - Mitgliedsnummern
   - Record Group oder NAID
   - Treffer im NARA-Text oder in lokaler OCR

   Zusammengesetzte Nachnamen werden konservativ geprueft: Ohne exakte Mitgliedsnummer oder NAID reicht ein einzelner Namensteil nicht aus. Wenn mehrere Suchmerkmale auf derselben relevanten Originalseite stehen, wird der Treffer staerker priorisiert als ein Treffer mit nur loser Metadatenuebereinstimmung.

6. **Treffer ranken**
   Kandidaten werden nach Plausibilitaet sortiert. Der Score ist die primaere Reihenfolge; Datierungen, Quellenart und NAID dienen als nachgeordnete Tie-Breaker. Der Score ist eine Arbeitspriorisierung, kein Beweis.

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
