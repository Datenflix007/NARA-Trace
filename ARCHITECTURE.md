# Architekturüberblick – NARATrace

NARATrace ist eine vollständig lokale Forschungsanwendung mit FastAPI-Backend, Svelte/TypeScript-Frontend und SQLite. Sie erzeugt nachvollziehbare Forschungshinweise, keine automatischen Identitätsbehauptungen.

Die zwei detaillierten Architekturquellen sind bewusst getrennt:

- [NARA_Architekture.md](docs/NARA_Architekture.md): NARA, A3340, MFKL/MFOK, Rollen, Frames, Catalog API und Open Dataset.
- [TRAXER_Architekture.md](docs/TRAXER_Architekture.md): lokale Programmkomponenten, Verantwortlichkeiten, Speicher und Datenfluss.

Die wissenschaftliche Suchlogik steht in [SEARCH-METHODOLOGY.md](docs/SEARCH-METHODOLOGY.md), die Bedienung in [USER-GUIDE.md](docs/USER-GUIDE.md) und der sitzungsübergreifende Umsetzungsstand in [TODO.md](TODO.md).

## Kurzbild

```text
Svelte UI -> FastAPI -> Search Jobs
                    -> NSDAP-Rollen-/Frame-Retrieval -> Matching/Ranking
                    -> NARA Catalog API (Metadaten und Fallback)
                    -> SQLite, lokaler Cache, optionale lokale OCR
```

Die Anwendung bindet standardmäßig an `127.0.0.1`; API-Schlüssel bleiben im OS-Keyring. Originalbilder werden erst für relevante Frame-Kandidaten geladen. Die vorhandenen Suchverläufe, Demo-/Mock-Trennung, lokale Dokumente, Transkripte, manuelle Korrekturen und Exporte bleiben Bestandteile der Architektur.
