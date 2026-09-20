# NARA- und A3340-Datenarchitektur

Stand: 2026-09-20. Dieses Dokument beschreibt die externe, offizielle Datenwelt. Die Architektur von NARATrace selbst steht in [TRAXER_Architekture.md](TRAXER_Architekture.md).

## Archivische Struktur

NARA bewahrt in Record Group 242 die *National Archives Collection of Foreign Records Seized*. Die Serie **Records Relating to Membership in the Nationalsozialistische Deutsche Arbeiterpartei (NSDAP), 1927–1945** trägt die Mikrofilm-Publikationsnummer **A3340** und die Serien-NAID **12044361**.

Für die Personensuche sind zwei veröffentlichte Teile entscheidend:

- **MFKL**, die Zentralkartei, ist die alphabetische Mitgliedskartei der zentralen NSDAP-Verwaltung. Sie ist der primäre Weg für Namensrecherche.
- **MFOK**, die Ortsgruppenkartei, ist eine zentrale geographische Kartei. Sie kann ortsbezogene, unabhängige Evidenz liefern und wird getrennt bewertet.

Eine Mikrofilmrolle (im Manifest `box`, etwa `R0014`) ist ein archivischer Container mit einem Namen- oder Ortsbereich. Die Ordnung der Rollen bleibt wichtiges Kontextwissen: Sie erklärt, aus welchem Teilbestand ein Kartenframe stammt und macht einen Treffer überprüfbar. NARATrace baut für MFKL und MFOK dennoch einen lokalen Gesamtindex auf. Damit wird der OCR-Text korpusweit durchsucht, ohne die Rolle, den Frame oder die ursprüngliche Zuordnung zu verlieren.

```mermaid
flowchart TD
    NARA[NARA] --> RG[Record Group 242]
    RG --> SERIES[A3340: NSDAP-Mitgliedschaftsunterlagen]
    SERIES --> MFKL[MFKL: alphabetische Zentralkartei]
    SERIES --> MFOK[MFOK: Ortsgruppenkartei]
    MANIFEST[docs/nsdap.json] --> MFKL
    MANIFEST --> MFOK
    MFKL --> ROLL[Mikrofilmrolle / Container]
    MFOK --> ROLL
    ROLL --> RJSON[Roll-JSON]
    RJSON --> FRAME[Digital Objects / Frames]
    FRAME --> OCR[extractedText]
    FRAME --> IMAGE[Original-TIFF oder PDF]
    CATALOG[National Archives Catalog] --> API[Catalog API v2]
    API --> META[NAID, Metadaten, Provenienz]
    META --> ROLL
```

## Historische Einordnung und Quellenkritik

Die hier erschlossenen Karteien sind keine nachträglich erstellten Forschungsdaten, sondern administrative Unterlagen der NSDAP und ihrer Gliederungen aus der Zeit des Nationalsozialismus. Sie wurden nach 1945 in alliierte Obhut genommen. Das Berlin Document Center wurde 1945 eingerichtet, um die übernommenen deutschen Unterlagen für Verfahren zu Kriegsverbrechen und Entnazifizierung zusammenzuführen; die biografischen Bestände umfassten NSDAP-Mitgliedschafts- und Personalunterlagen. NARA bewahrt für große Teile dieses Kontextes Mikrofilmüberlieferungen in Record Group 242. [NARA zur Geschichte von RG 242](https://www.archives.gov/research/guide-fed-records/groups/242.html)

Diese Überlieferungskette ist für die Interpretation wesentlich:

```mermaid
flowchart LR
    A[NSDAP-Verwaltung\nErstellung der Karteikarten] --> B[Überlieferung und Auswahl\nim Verwaltungshandeln]
    B --> C[Alliierte Übernahme 1945\nBerlin Document Center]
    C --> D[Mikroverfilmung und\narchivische Erschließung]
    D --> E[NARA A3340\nRolle und Kartenframe]
    E --> F[Digitalisat und NARA-OCR]
    F --> G[NARATrace-Volltextindex\nals Recherchezugang]
    G --> H[Prüfung am Originalframe\nund im Archivkontext]
```

Die Karteien sind deshalb weder vollständig noch neutral. Ein Eintrag kann Verwaltungsinformationen, Namensformen und weitere Angaben überliefern; er ersetzt jedoch keinen belastbaren Nachweis einer eindeutig identifizierten Person, einer Mitgliedschaft zu einem bestimmten Zeitpunkt oder einer individuellen Handlung. Namensgleichheiten, Schreibvarianten, Lücken der Überlieferung und Fehler der maschinellen Texterkennung sind ausdrücklich mitzudenken. Negative Suchergebnisse beweisen ebenfalls nicht das Fehlen einer Person oder Information im historischen Bestand.

Für eine zitierfähige Recherche müssen mindestens Serie, Rolle, Frame, NAID, Original-URL und Abrufdatum festgehalten werden. NARATrace bewahrt diese Provenienz am Treffer und trennt sie von der automatischen Ähnlichkeitsbewertung. Das Originalbild und sein archivischer Zusammenhang haben gegenüber OCR und Ranking immer Vorrang.

Die offizielle NARA-Übersicht nennt für A3340 die Reihen MFKL (Zentralkartei) und MFOK (Ortsgruppenkartei) als getrennte Mikrofilmserien. [NARA: Microfilmed Records Received from the Berlin Document Center](https://www.archives.gov/research/captured-german-records/berlin-document-center.html)

## Technische Struktur des Open Dataset

NARA veröffentlicht das Dataset im öffentlichen S3-Bucket `nara-nsdap` und beschreibt den Zugriff im offiziellen Repository [`usnationalarchives/nsdap`](https://github.com/usnationalarchives/nsdap). Das offizielle Manifest `docs/nsdap.json` enthält pro Rolle die Felder: `id` (NAID), `agency` (MFKL/MFOK), `box`, `title` und `s3`.

```text
docs/nsdap.json
  -> Rollenbeschreibung (agency, box, title, NAID, s3)
  -> s3://nara-nsdap/<Rollenpfad>/<NAID>.json
  -> record.digitalObjects[]
  -> objectFilename + extractedText + objectUrl
  -> Original-TIFF bzw. rollenweises PDF
```

Ein Roll-JSON spiegelt einen Catalog-Datensatz: `record.naId` bezeichnet die Rolle, `record.digitalObjects` ihre Frames. `objectFilename` verknüpft OCR und Bild, `extractedText` ist die von NARA bereitgestellte Textract-OCR. Das Originalbild bleibt maßgeblich; OCR ist ein Such- und Prüfhinweis.

## Pipeline des lokalen Gesamtindex

Die folgende Darstellung zeigt den technischen Ablauf des Erstaufbaus und einer späteren Suche. Der zeitaufwändige Netz- und Indexierungsschritt fällt nur für noch fehlende Rollen an; bereits vollständig gespeicherte Rollen werden beim Fortsetzen übersprungen.

```mermaid
flowchart TD
    A[Start: Index aufbauen oder fortsetzen] --> B[Offizielles A3340-Manifest laden]
    B --> C{MFKL oder MFOK?}
    C -- nein --> D[Für diesen Index auslassen]
    C -- ja --> E{Rolle lokal vollständig indexiert?}
    E -- ja --> F[Überspringen]
    E -- nein --> G[Roll-JSON von NARA laden]
    G --> H[Frames, OCR-Text und Provenienz auslesen]
    H --> I[In SQLite FTS5 schreiben]
    I --> J[Rollstatus lokal speichern]
    F --> K[Gesamtindex]
    J --> K
    K --> L[Name oder Mitgliedsnummer suchen]
    L --> M[Passende Kartenframes]
    M --> N[Einzelnes Originalbild bei NARA prüfen]
```

Beispiel einer aktuell geprüften Manifestbeobachtung: `MFKL R0014` hat NAID `593495034`, Titel `Schultze, Paul - Schultze, Robert` und einen S3-Pfad unter `A3340-MFKL/A3340-MFKL-R0014`. Das ist kein Produktions-Sonderfall, sondern ein normales Ergebnis der Bereichsauswahl.

## Catalog API und A3340 Open Dataset

| Quelle | Einsatz in NARATrace | Nicht ihr Ersatz |
| --- | --- | --- |
| National Archives Catalog API v2 | Archivmetadaten, NAID, Rechte, öffentliche Catalog-URL, Serienkontext und Fallback-Suche | rollenpräzise Volltextsuche über A3340 |
| A3340 Open Dataset | Rollenindex, Roll-JSON, Frames, `extractedText`, `objectFilename`, Originalobjekt-URLs | Identitätsentscheidung oder manuelle Quellenkritik |

Die Catalog API ist schlüsselgeschützt und darf nicht für Corpus-Scraping missbraucht werden. Das Open Dataset ist für die gezielte Rollennutzung vorgesehen. NARATrace verwendet daher erst den lokalen Rollenindex und nur ergänzend den Catalog als Metadaten- und Fallback-Weg.

## Quellen und Grenzen

- [NARA: offizielles NSDAP-Repository](https://github.com/usnationalarchives/nsdap)
- [NARA: A3340, NAID 12044361](https://catalog.archives.gov/id/12044361)
- [NARA: Captured German Records / Berlin Document Center](https://www.archives.gov/research/captured-german-records/berlin-document-center.html)
- [NARA Catalog API](https://catalog.archives.gov/api/v2/api-docs/)

Die Feld- und Pfadbeschreibung wurde gegen Manifest und Roll-JSON am 2026-09-20 geprüft. NARA kann Dataset-Struktur oder OCR künftig aktualisieren; Cache-Inhalte sind daher mit Abrufdatum und Original-URL zu behandeln.
