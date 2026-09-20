# NARA-Trace Roadmap

Stand: 2026-09-20. Diese Datei ist der verbindliche Einstiegspunkt für die nächste Sitzung. Nach jedem abgeschlossenen Teilabschnitt müssen Tests, Dokumentation und dieser Status aktualisiert werden.

## Projektziel

NARA-Trace soll Personen in NARAs digitalisierter NSDAP-Mitgliederkartei A3340 quellennahe finden: zunächst anhand der archivischen Rollenstruktur, dann anhand von Frames und OCR, zuletzt durch nachvollziehbares Record Linkage. Ein Ergebnis ist nur ein Forschungshinweis, bis Originalkarte und Evidenz geprüft sind. Demo-/Mock-/lokale Dateien dürfen niemals den realen Suchpfad oder dessen Regressionstests erfüllen.

## Aktueller technischer Stand

- [x] Lokales FastAPI-/Svelte-System, SQLite-Suchverläufe, Exporte, lokale Dokumente, TIFF-Anzeige, Transkripte und manuelle Korrekturen vorhanden.
- [x] NARA Catalog API v2 ist mit lokalem Keyring-Key, Pagination, Fehlerbehandlung und klarer Mock-Trennung angebunden.
- [x] Suchjob nutzt den A3340-FTS5-Gesamtindex primär und den Catalog als dokumentierten Fallback; Identity Ranking ist weiterhin eine offene getrennte Ausbaustufe.
- [x] Offizielles NARA-Manifest `docs/nsdap.json` geprüft: 5.420 Rollen (3.153 MFKL, 2.267 MFOK; Abruf 2026-09-20).
- [x] Neue Schicht `naratrace.nsdap` angelegt: Manifest-/Roll-Cache, Rollenmodelle, Bereichsauswahl, Roll-JSON-Lader, Frame-Provenienz und erstes retrieval-orientiertes Frame-Matching.
- [x] Gewichtete Namensnormalisierung für Bindestriche, Umlaute, ß und Adelsprädikate angelegt.
- [x] Search Jobs bauen beziehungsweise aktualisieren einen lokalen Gesamtindex über alle MFKL- und MFOK-Rollen und speichern nur konkrete Kartenframes als Treffer.

## Zielarchitektur

`SearchRequest -> SearchProfile -> Query Planner -> Roll Candidates -> Frame Candidates -> Entity Extraction -> Match Evidence -> Person Candidate -> Ranked SearchResult -> Frontend`

Der Catalog bleibt Metadaten-/Provenienz-/Fallback-Quelle. Das A3340 Open Dataset wird der primäre Retrieval-Weg für MFKL/MFOK. Retrieval Score und Identity Score bleiben getrennt. Details: [ARCHITECTURE.md](ARCHITECTURE.md), [NARA_Architekture.md](docs/NARA_Architekture.md), [TRAXER_Architekture.md](docs/TRAXER_Architekture.md).

## Phase 1 – Analyse und Datenquellen

- [x] Repository, bestehende Suche, Datenbank- und Materialisierungsweg analysiert.
- [x] Catalog API und offizielles A3340 Open Dataset abgegrenzt und dokumentiert.
- [x] Offizielles Manifest und die echte S3-Roll-JSON-Struktur geprüft.
- [x] Baseline-Tests vor dem Umbau ausgeführt.
- [ ] Fehler- und Rate-Limit-Verhalten der neuen NSDAP-Schicht in Jobs/UI darstellen.

## Phase 2 – NSDAP-Rollenindex

- [x] Manifestmodell für NAID, agency, box, title, S3-Pfad und Bereichsgrenzen implementiert.
- [x] Lokaler Manifestcache und gezielter Roll-JSON-Cache implementiert.
- [x] MFKL/MFOK-Rollen werden vollständig im lokalen Frameindex erfasst; keine bekannte Rolle und kein fester R-Bereich wird für die Suche vorgegeben.
- [x] Unit Tests für Bereichsauswahl und Manifest-/Roll-Parsing erstellt.
- [ ] Manifestcache mit Abrufdatum/ETag und administrativem Refresh sichtbar machen.
- [x] Persistenten SQLite-FTS5-Frameindex für alle geladenen MFKL-/MFOK-Roll-JSONs implementiert; Originalbilder bleiben ausgeschlossen.

## Phase 3 – Namensnormalisierung

- [x] Originalnamen und gewichtete Varianten für Bindestrich, Umlaute, ß und `von` implementiert.
- [x] Tests für Doppelname, Umlaute, ß und Adelsprädikat erstellt.
- [ ] OCR-spezifische Zeichenverwechslungen kontextsensitiv ergänzen.
- [ ] Ortsvarianten und Ortsarten (Geburtsort, Wohnort, Ortsgruppe usw.) modellieren.
- [ ] Mitgliedsnummern feldnah extrahieren und OCR-Alternativen robust prüfen.

## Phase 4 – Candidate Retrieval

- [x] Roll-JSON kann gezielt geladen werden; `objectFilename`, `objectUrl` und `extractedText` bleiben erhalten.
- [x] Erstes Frame-Retrieval mit dokumentierter Strategie implementiert.
- [ ] Query Planner mit getrennten Pässen und gespeicherten Retrieval-Strategien implementieren.
- [x] A3340-Retrieval in `SearchJob` integriert; bei fehlenden Frame-Kandidaten bleibt der Catalog der Fallback.
- [ ] Deduplizierung über Rollen, Frames und Nachbarframes implementieren.

## Phase 5 – OCR-/Frame-Suche

- [x] NARA Extracted Text als Framequelle angelegt.
- [ ] Nachbarframes gruppieren und Karten-Vorder-/Rückseiten erkennen.
- [x] Nur die drei höchstgerankten Frame-Kandidaten werden als Einzel-TIFF geladen und browserfähig bereitgestellt; Rollen-PDFs werden nicht als Treffer verlinkt.
- [ ] Lokale OCR-Provider-Schnittstelle von der Materialisierung trennen.

## Phase 6 – Record Linkage

- [ ] Entitäten für Name, Datum, Mitgliedsnummer, Ort und OCR-Sicherheit extrahieren.
- [ ] Positive und negative Evidenz als strukturierte Objekte erzeugen.
- [ ] MFKL/MFOK-Treffer derselben Person mit Quellenbezug verknüpfen.
- [ ] Widersprüche sichtbar machen statt wegzupunkten.

## Phase 7 – Ranking

- [x] Frame Retrieval Score ist als eigener, noch einfacher Score vorhanden.
- [ ] Identity Score getrennt von Retrieval Score implementieren.
- [ ] Gewichtung kalibrieren; häufige Namen deckeln und Einzelhinweise begrenzen.
- [ ] Scoreaufschlüsselung und Debug-Evidenz speichern.

## Phase 8 – Regressionstests

- [x] Erweiterbare Fixture-Struktur `backend/tests/fixtures/nsdap_gold/` angelegt.
- [x] PSN-Fall als ausdrücklich unaufgelöste Fixture vorbereitet; keine NAID-, Rollen- oder Frame-Hartcodierung.
- [x] Reale Recherche gegen die allgemeine Rollen-/Roll-JSON-Schicht: R0013 Frame 2947 dokumentiert die Mitgliedsnummer 347541, Frame 2948 ist die anschließende Karteiseite. Der Produktionspfad verwendet jedoch keinen bekannten R0013-/Nachbarrollenbereich, sondern den Gesamtindex. Noch keine Goldfixture, weil Bildprüfung und allgemeines Identity Ranking fehlen.
- [ ] Tatsächliche Paul-Schultze-Naumburg-Karte über die allgemeine Pipeline und Originalbild quellenkritisch verifizieren.
- [ ] Erst dann Goldreferenz, Tests A–D und Top-5/Top-1-Auswertung hinzufügen.
- [ ] Zusätzliche unabhängige Goldfälle ergänzen; Recall@1/@5/@10/@20 und MRR messen.
- [ ] Test absichern, dass reale Pipeline weder LOCAL, MOCK noch Demo-PDF verwendet.

## Phase 9 – Frontend

- [x] Bestehende Suche, Fortschritt, Treffer, Detailansicht, Transkript, manuelle Korrektur und Verläufe erhalten.
- [x] Konkrete Kartenframes werden mit Rolle, Frame, `objectFilename`, NARA-Extracted-Text und Originalbild-Provenienz gespeichert.
- [x] Transkriptansicht markiert Suchbegriffe und robuste Nummernformen direkt im Text; der TextMarkerEditor bleibt ein optionaler Adapter, da seine GitHub-Pakete aktuell nicht als stabile Runtime-Dependency ausgeliefert werden.
- [ ] Debug-/Methodikansicht mit Varianten, Rollenwahl, Frameanzahl und Scoreaufschlüsselung bauen.
- [ ] Kandidatenvergleich und semantische Transkriptmarkierung vorbereiten; TS_TextMarker nur über optionalen Adapter anbinden.

## Phase 10 – Dokumentation

- [x] `docs/NARA_Architekture.md` mit realer externer Struktur und Mermaid-Diagramm erstellt.
- [x] `docs/TRAXER_Architekture.md` mit Programmschichten, Entscheidungen und Mermaid-Diagramm erstellt.
- [x] `ARCHITECTURE.md`, `README.md`, `SEARCH-METHODOLOGY.md` und `USER-GUIDE.md` verlinkt/aktualisiert.
- [ ] Datenvertrag für Trefferprovenienz und Evaluation dokumentieren.
- [ ] Nach jeder Moduländerung Architekturtexte gegen Code prüfen.

## Phase 11 – Performance und Packaging

- [ ] FTS5-Index über lokale Roll-JSONs benchmarken.
- [ ] Cache-Größen, Refresh, Beschädigung und LRU-Strategie festlegen.
- [ ] Rate-Limits, Offline-Verhalten, Timeouts und große Rollen testen.
- [ ] Packaging nach stabiler Pipeline überprüfen.

## Aktuelle Blocker

- [ ] Der erste vollständige lokale A3340-Korpusaufbau muss auf einem realen Rechner gegen alle offiziellen Roll-JSON-Dateien durchgeführt und auf Abbrüche/Rate-Limits geprüft werden.
- [ ] Der PSN-Goldstandard darf erst nach reproduzierbarer Originalbildprüfung eingetragen werden.
- [ ] Feldextraktion für historische OCR ist noch nicht implementiert.

## Bekannte Fehler

- [ ] `processing/jobs.py` bündelt weiterhin Query-Bau, Catalog-Retrieval, Speicherung, Materialisierung und Bewertung; schrittweise in kleine Module zerlegen.
- [ ] Die bestehende Catalog-Query baut noch breite OR-Terme und ist für A3340 nicht ausreichend präzise.
- [ ] Browserinkompatible Remote-TIFFs benötigen weiterhin gezielte lokale Materialisierung für die Anzeige.

## Entscheidungen / Architecture Decisions

- [x] A3340 Open Dataset für Roll-/Frame-Retrieval; Catalog API für Metadaten, Provenienz und Fallback.
- [x] Gesamtkorpus wird einmalig aus den Roll-JSONs in SQLite FTS5 indexiert; Suchläufe fragen anschließend den lokalen Index ab statt nur Nachbarrollen oder das entfernte Korpus erneut zu laden.
- [x] MFKL und MFOK getrennt verarbeiten und erst als Evidenz verknüpfen.
- [x] Retrieval Score und Identity Score konzeptionell trennen.
- [x] Originalbilder lazy laden; keine Massen-OCR großer Rollen im Suchpfad.
- [x] Goldtests enthalten Testdaten, nicht Produktions-Sonderlogik.

## Regressionstest Paul Schultze-Naumburg

- [x] Eingangsszenarien festgehalten: exakter Name; `Schulte-Naumburg` + 1869; Orte; Mitgliedsnummer.
- [x] Rahmen gesetzt: keine lokale PDF, Demo-, Mock-, NAID-, Rollen- oder Frame-Sonderbehandlung.
- [ ] Test A: nur `Paul` / `Schultze-Naumburg`, reale Karte Top 5 (Ziel Top 1).
- [ ] Test B: `Schulte-Naumburg` + 1869, reale Karte weiterhin oben.
- [ ] Test C: Orte verbessern oder bestätigen Ranking nachvollziehbar.
- [ ] Test D: bestätigte Mitgliedsnummer führt zu Top 1.

## Nächste konkrete Aufgaben

1. `QueryPlanner` und `candidate_pipeline` aus `processing/jobs.py` auslagern.
2. Vollständigen MFKL-/MFOK-Index mit `python -m naratrace --index-a3340` aufbauen und Laufzeit, Cachegröße sowie Fehlerfälle dokumentieren.
3. Den PSN-Kandidaten über die allgemeine Korpussuche ermitteln und Frame/Originalbild quellenkritisch prüfen.
4. Mitgliedsnummer-/Datum-/Ort-Extraktion, negative Evidenz und getrenntes Identity Ranking implementieren.
5. Erst nach erfolgreicher Prüfung Goldfixture konkretisieren, Regressionsevaluation hinzufügen und die Frontend-Provenienz erweitern.

## Sitzungsabschluss

- [x] 2026-09-20: Architektur- und Datenquellenanalyse abgeschlossen; offizielle Manifest- und Roll-JSON-Struktur live geprüft.
- [x] 2026-09-20: NSDAP-Basisschicht, gewichtete Namensvarianten und Unit Tests implementiert.
- [x] 2026-09-20: Direkter MFKL-Jobpfad ergänzt: die Suche mit `347541` erzeugt R0013 Frame 2947/2948 als einzelne Kartenframes statt eines Rollen-PDFs; öffentliche `medialz`-URLs umgehen den nicht zugänglichen Legacy-S3-Pfad.
- [x] 2026-09-20: Direkter A3340-Pfad auf einen persistenten SQLite-FTS5-Gesamtindex umgestellt: MFKL und MFOK werden über alle Rollen indexiert; spätere Suchläufe verwenden diesen Index statt eines auf R0013 begrenzten Abrufs.
- [x] 2026-09-20: Backend-Tests `python -m pytest tests` erfolgreich (40 bestanden); neuer Manifest-/Rollen-Smoke-Test gegen offizielle Quelle erfolgreich.
- [x] 2026-09-20: Frontend-Tests `npm run test -- --run` erfolgreich (18 bestanden); `npm run build` erfolgreich.
- [x] 2026-09-20: `git diff --check` ohne Befund.
