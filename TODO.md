# TODO - NARATrace

## Aktueller Stand

Arbeitsbeginn: 2026-07-25.

Repository-Analyse:

- [x] Bestehende Struktur geprüft.
- [x] Vorhandener Git-Status geprüft.
- [x] Bestehende README erhalten und erweitert.

M1 - Grundstruktur:

- [x] `TODO.md` angelegt.
- [x] `ARCHITECTURE.md` angelegt.
- [x] Backend-Verzeichnisstruktur angelegt.
- [x] Frontend-Verzeichnisstruktur angelegt.
- [x] Skript-Verzeichnis angelegt.
- [x] `.gitignore` und `.env.example` angelegt.
- [x] Lokale Datenverzeichnisse über `platformdirs` implementiert.
- [x] Grundkonfiguration implementiert.

M2 - erster lokaler Start:

- [x] FastAPI-Grundgerüst implementiert.
- [x] Health-Endpunkt implementiert.
- [x] SQLite-Konfiguration implementiert.
- [x] Alembic-Grundgerüst implementiert.
- [x] Launcher für `python -m naratrace` implementiert.
- [x] Standardbindung auf `127.0.0.1:8765` implementiert.
- [x] Browserstart nach erfolgreichem Health-Check implementiert.
- [x] Backend-Basistests ergänzt.

M7 - Jobsystem-Grundlage:

- [x] `POST /api/search` legt lokale Suchjobs in SQLite an.
- [x] `GET /api/search` zeigt gespeicherte Suchverläufe.
- [x] `GET /api/search/{job_id}` liefert Jobstatus.
- [x] `GET /api/search/{job_id}/results` liefert Ergebnisse.
- [x] Frontend-Suchformular ruft das Backend auf.
- [x] Suchformular erfasst Geburtsdatum, Geburtsjahr, Wohnorte und Mitgliedsnummer.
- [x] Backend speichert Geburtsdatum, Geburtsjahr, Wohnorte und Mitgliedsnummer als `SearchField`.
- [x] Mitgliedsnummern erzeugen erste Formatvarianten wie `347541`, `347.541`, `347 541`, `Nr. 347541`.
- [x] Frontend-Suchverläufe zeigen gespeicherte Jobs.
- [x] Suchverläufe sind klickbar und laden die Treffer des ausgewählten Jobs.
- [x] Suchverläufe können gelöscht werden.
- [x] Einzelne Treffer können aus einem Suchverlauf gelöscht werden.
- [x] Trefferlisten werden nach Trefferwahrscheinlichkeit sortiert.
- [x] Trefferzeilen zeigen links das Aktenfoto oder einen Platzhalter und rechts Name, Geburtsdatum und Wohnort.
- [x] Treffer öffnen eine Detailansicht mit Originalseite links und Transkript rechts.
- [x] Original-Hotspots und Transkriptzeilen markieren sich gegenseitig per Hover/Fokus/Klick.
- [x] Normalmodus erzeugt keine erfundenen NARA-Treffer.
- [x] Mock-Modus erzeugt klar gekennzeichnete Beispieltreffer.
- [x] Startseite zeigt ein Anzeige-Beispiel mit lokalem `LOCAL`-Treffer aus `SchulzeNaumburg_NSDAP_Kartei1931.pdf` und weiteren `MOCK`-Vergleichstreffern.
- [x] Demo-Bilder aus `frontend/public/demo/` werden unter `/demo/...` ausgeliefert.
- [x] Sichtbare Demo-Bilder werden zusätzlich als Vite-Assets eingebunden und über `/assets/...png` ausgeliefert.

M4/M6 - NARA-API-Grundlage:

- [x] Offizielle NARA Catalog API v2 Swagger-Dokumentation geprüft: `https://catalog.archives.gov/api/v2/api-docs/`, Spezifikation über `/api/v2/swagger.json`.
- [x] `NaraCatalogClient` mit async `httpx`, Timeout, User-Agent, `x-api-key`, JSON-Prüfung und verständlichen Fehlern implementiert.
- [x] NARA-Key-Live-Test in `/api/settings/test-nara-key` angebunden.
- [x] Einstellungen-Oberfläche kann NARA API-Schlüssel speichern, testen und löschen.
- [x] `POST /api/search` ruft bei vorhandenem API-Key die echte NARA Catalog API v2 ab.
- [x] Erste echte Kandidaten werden als `CandidateRecord`, `SearchResult` und `MatchEvidence` gespeichert.
- [x] Ohne API-Key schlägt der Suchjob klar mit `NARA API-Schlüssel fehlt.` fehl, statt scheinbar erfolgreich ohne Treffer zu sein.

## Nächste konkrete Schritte

- [ ] NARA Catalog API v2 Swagger-Dokumentation prüfen und daraus den gekapselten `NaraCatalogClient` ableiten.
- [ ] API-Schlüssel-Live-Test gegen NARA implementieren, ohne Schlüssel zu protokollieren.
- [ ] Svelte-Oberfläche für Startseite, Navigation und NARA-Quellenkennzeichnung ausbauen.
- [ ] Suchprofilmodell mit Normalisierung und Suchvarianten implementieren.
- [ ] Persistente Jobs und Suchverläufe in die API aufnehmen.
- [ ] Mock-Modus mit klarer Kennzeichnung und reproduzierbaren Beispieldaten implementieren.

## Offene Fehler und Risiken

- Die initiale Alembic-Migration verwendet im ersten MVP die SQLAlchemy-Metadaten als Schemaquelle. Vor produktiven Schemaänderungen sollen zukünftige Revisionen explizit generiert werden.
- Die Svelte-Oberfläche besitzt jetzt Start, Suche, klickbare Suchverläufe, Trefferlisten, Detailansicht, lokale Dokumente, Einstellungen, Methodik und Über-Ansicht. Einige Fachfunktionen sind weiterhin Platzhalter.
- Echte NARA-Suchtreffer sind angebunden, benötigen aber zwingend einen gültigen persönlichen NARA API-Schlüssel.
- Aktuell wird die erste Suchseite mit begrenzter Kandidatenzahl abgerufen. Tiefe Pagination, OCR, Detailansicht, lokale Dokumente und Exporte sind noch nicht vollständig implementiert.
- Lokale OCR, vollständige NARA-Pagination, detailliertes Matching und Exporte sind noch nicht implementiert.
- Die lokale Schultze-Naumburg-PDF ist als Demo-Quelle eingebunden; eine echte OCR-/Detailauswertung der Bildseiten folgt noch.
- Auf diesem Rechner ist der Standardport `8765` durch einen Systemlistener auf `::` mit PID 4 belegt. NARATrace bricht in diesem Fall jetzt mit verständlicher Meldung ab. Der echte Start wurde auf `127.0.0.1:8766` verifiziert.

## Sitzungsabschluss

- Backend-Tests: `python -m pytest .\backend\tests` erfolgreich, 2 bestanden.
- Frontend-Tests: `npm run test -- --run` erfolgreich, 1 bestanden.
- Windows-Testskript: `.\scripts\test.ps1` erfolgreich.
- Windows-Buildskript: `.\scripts\build.ps1` erfolgreich.
- Lokaler Start: `python -m naratrace --no-browser --port 8766` erfolgreich gegen `/api/health` geprüft.
- Standardport-Prüfung: `python -m naratrace --no-browser --port 8765` meldet korrekt, dass der Port belegt ist.
- Blank-Screen-Fehler im Svelte-Frontend behoben: `frontend/src/main.ts` verwendet jetzt Svelte-5-konform `mount()`.
- Frontend-Auslieferung nach Fix geprüft: FastAPI liefert den neuen Build-Bundle `index-BWhgbdf6.js` aus.
- Hauptnavigation im Frontend funktionsfähig gemacht: Start, Neue Suche, Suchverläufe, Lokale Dokumente, Einstellungen, Methodik und Über NARATrace wechseln jetzt clientseitig die Ansicht.
- Backend-Status wird in der Startseite angezeigt, statt den Benutzer auf die rohe JSON-Antwort weiterzuleiten.
- Frontend-Tests nach Navigationsfix: `npm run test -- --run` erfolgreich, 3 bestanden.
- Frontend-Build nach Navigationsfix: `npm run build` erfolgreich; FastAPI liefert den neuen Bundle `index-BTrZWwcU.js` aus.
- Backend-Tests nach Suchjob-Grundlage: `python -m pytest .\backend\tests` erfolgreich, 4 bestanden.
- Backend-Tests nach Suchmasken-Erweiterung: `python -m pytest .\backend\tests` erfolgreich, 4 bestanden.
- Frontend-Tests nach Suchmasken-Erweiterung: `npm run test -- --run` erfolgreich, 4 bestanden.
- Frontend-Build nach Suchmasken-Erweiterung: `npm run build` erfolgreich; neuer Bundle `index-CY1AwERp.js`.
- Integrierter API-Check: lokaler Server auf `127.0.0.1:8767`, `POST /api/search`, `GET /api/search/{job_id}/results` und `GET /api/search` erfolgreich.
- Integrierter API-Check mit Geburtsdatum, Geburtsjahr, Wohnorten und Mitgliedsnummer erfolgreich.
- NARA-Client-/Suchjob-Tests: `python -m pytest .\backend\tests` erfolgreich, 5 bestanden.
- Projekt-Testskript: `.\scripts\test.ps1` erfolgreich.
- End-to-End-Check ohne API-Key: Settings und Suche zeigen korrekt `NARA API-Schlüssel fehlt.`, neuer Frontend-Bundle `index-v9d6qszM.js` wird ausgeliefert.
- Demo-End-to-End-Check ohne API-Key: `POST /api/search` mit `demo_mode=true` erzeugt 4 MOCK-Treffer, neuer Frontend-Bundle `index-D1vCcqYH.js` wird ausgeliefert.
- Demo-Treffer aktualisiert: erster Treffer ist jetzt `LOCAL-PDF-SCHULTZE-NAUMBURG-1931` aus der lokalen PDF, weitere Vergleichstreffer bleiben `MOCK`.
- Backend-Tests nach lokalem PDF-Demo-Treffer: `python -m pytest .\backend\tests` erfolgreich, 6 bestanden.
- Frontend-Tests nach lokalem PDF-Demo-Treffer: `npm run test -- --run` erfolgreich, 5 bestanden.
- Frontend-Build nach lokalem PDF-Demo-Treffer: `npm run build` erfolgreich; neuer Bundle `index-CeW5-1nC.js`.
- Projekt-Testskript nach lokalem PDF-Demo-Treffer: `.\scripts\test.ps1` erfolgreich.
- Direkter API-Check: `POST /api/search` mit `demo_mode=true` liefert als ersten Treffer `LOCAL-PDF-SCHULTZE-NAUMBURG-1931`.
- Anzeige-Beispiel auf die Startseite verschoben; Suchmaske enthält keinen Demo-Treffer-Button mehr.
- Suchverlauf-Drilldown implementiert: Klick auf Suchlauf lädt gerankte Treffer; Klick auf Treffer öffnet Detailansicht.
- Detailansicht implementiert: Originalseite links, Transkript rechts, gegenseitige gelbe Markierung per Hover/Fokus/Klick.
- Demo-Bilder aus lokaler PDF erzeugt: `frontend/public/demo/schultze-page-1.png` bis `schultze-page-4.png` und `schultze-portrait.png`.
- Frontend-Tests nach Suchverlauf-/Detailumbau: `npm run test -- --run` erfolgreich, 6 bestanden.
- Backend-Tests nach Suchverlauf-/Detailumbau: `python -m pytest .\backend\tests` erfolgreich, 6 bestanden.
- Frontend-Build nach Suchverlauf-/Detailumbau: `npm run build` erfolgreich; neuer Bundle `index-BoVQUzxa.js`.
- Projekt-Testskript nach Suchverlauf-/Detailumbau: `.\scripts\test.ps1` erfolgreich.
- Demo-Bildauslieferung repariert: FastAPI mountet `/demo` aus `frontend/dist/demo` oder fallbackweise `frontend/public/demo`.
- Lösch-API ergänzt: `DELETE /api/search/{job_id}` und `DELETE /api/search/{job_id}/results/{result_id}`.
- Suchverlauf-Löschbuttons ergänzt: komplette Suchläufe und einzelne Treffer können mit Bestätigung gelöscht werden.
- Backend-Tests nach Lösch-/Demo-Fix: `python -m pytest .\backend\tests` erfolgreich, 7 bestanden.
- Frontend-Tests nach Lösch-/Demo-Fix: `npm run test -- --run` erfolgreich, 7 bestanden.
- Frontend-Build nach Lösch-/Demo-Fix: `npm run build` erfolgreich; neuer Bundle `index-BKCFK9ln.js`.
- Projekt-Testskript nach Lösch-/Demo-Fix: `.\scripts\test.ps1` erfolgreich.
- Demo-Fachdaten korrigiert: Geburtsort `Almrich`, Wohnorte `Naumburg` und später `Weimar`; alte falsche Wohnortangabe entfernt und per Tests abgesichert.
- Backend-Tests nach Demo-Fachdaten-Korrektur: `python -m pytest .\backend\tests` erfolgreich, 7 bestanden.
- Frontend-Tests nach Demo-Fachdaten-Korrektur: `npm run test -- --run` erfolgreich, 7 bestanden.
- Frontend-Build nach Demo-Fachdaten-Korrektur: `npm run build` erfolgreich; neuer Bundle `index-BJ8LOozF.js`.
- Demo-Bildanzeige repariert: Portrait und Originalseite werden aus bytegleich kopierten `frontend/src/assets/demo/` Dateien importiert; laufender Server liefert `/assets/schultze-portrait-ChQq2jBk.png` und `/assets/schultze-page-2-aFYLvqcI.png` mit `200 image/png`.
- Frontend-Build nach Asset-Fix: `npm run build` erfolgreich; neuer Bundle `index-De_ujF8I.js`.
- Geänderte Dateien werden im Abschlussbericht genannt.
