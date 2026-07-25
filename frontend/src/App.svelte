<script lang="ts">
  import { onMount } from 'svelte';
  import {
    fetchHealth,
    fetchSearchHistory,
    fetchSearchResults,
    fetchSettings,
    saveNaraApiKey,
    startSearch,
    testNaraApiKey,
    deleteNaraApiKey,
    type ApiKeyTestResponse,
    type HealthResponse,
    type SettingsResponse,
    type SearchJobResponse,
    type SearchResultResponse
  } from './lib/api';

  type RouteId = 'start' | 'search' | 'history' | 'local-documents' | 'settings' | 'methodology' | 'about';

  const navItems: { id: RouteId; label: string }[] = [
    { id: 'start', label: 'Start' },
    { id: 'search', label: 'Neue Suche' },
    { id: 'history', label: 'Suchverläufe' },
    { id: 'local-documents', label: 'Lokale Dokumente' },
    { id: 'settings', label: 'Einstellungen' },
    { id: 'methodology', label: 'Methodik' },
    { id: 'about', label: 'Über NARATrace' }
  ];

  let activeRoute: RouteId = 'start';
  let health: HealthResponse | null = null;
  let healthError = '';
  let healthLoading = false;
  let firstName = '';
  let lastName = '';
  let variants = '';
  let birthDate = '';
  let birthYear: number | null = null;
  let residencePlaces = '';
  let membershipNumber = '';
  let naid = '';
  let recordGroup = '';
  let maxCandidates = 50;
  let searchNotice = '';
  let searchError = '';
  let searchLoading = false;
  let currentJob: SearchJobResponse | null = null;
  let currentResults: SearchResultResponse[] = [];
  let historyJobs: SearchJobResponse[] = [];
  let historyLoading = false;
  let historyError = '';
  let settings: SettingsResponse | null = null;
  let settingsLoading = false;
  let settingsError = '';
  let settingsNotice = '';
  let naraApiKeyInput = '';
  let keyTest: ApiKeyTestResponse | null = null;

  onMount(() => {
    const syncRoute = () => {
      activeRoute = routeFromHash(window.location.hash);
    };

    syncRoute();
    if (activeRoute === 'settings') {
      void loadSettings();
    }
    if (activeRoute === 'history') {
      void loadHistory();
    }
    window.addEventListener('hashchange', syncRoute);

    return () => window.removeEventListener('hashchange', syncRoute);
  });

  function routeFromHash(hash: string): RouteId {
    const route = hash.replace(/^#\/?/, '') as RouteId;
    return navItems.some((item) => item.id === route) ? route : 'start';
  }

  function navigate(event: MouseEvent, route: RouteId) {
    event.preventDefault();
    activeRoute = route;
    window.location.hash = route;
    if (route === 'history') {
      void loadHistory();
    }
    if (route === 'settings') {
      void loadSettings();
    }
  }

  async function checkBackend() {
    healthLoading = true;
    healthError = '';
    try {
      health = await fetchHealth();
    } catch (error) {
      health = null;
      healthError = error instanceof Error ? error.message : 'Der Backend-Status konnte nicht geladen werden.';
    } finally {
      healthLoading = false;
    }
  }

  async function prepareSearch(event: SubmitEvent) {
    event.preventDefault();
    const name = [firstName.trim(), lastName.trim()].filter(Boolean).join(' ');
    if (!lastName.trim()) {
      searchNotice = '';
      searchError = 'Bitte mindestens einen Nachnamen eingeben.';
      return;
    }
    searchLoading = true;
    searchNotice = '';
    searchError = '';
    currentJob = null;
    currentResults = [];
    try {
      currentJob = await startSearch({
        first_name: firstName.trim() || undefined,
        last_name: lastName.trim(),
        variants: variants.trim() || undefined,
        birth_date: birthDate || undefined,
        birth_year: birthYear || undefined,
        residence_places: residencePlaces.trim() || undefined,
        membership_number: membershipNumber.trim() || undefined,
        naid: naid.trim() || undefined,
        record_group: recordGroup.trim() || undefined,
        max_candidates: maxCandidates
      });
      currentResults = await fetchSearchResults(currentJob.id);
      searchNotice = `Suchjob für "${name}" wurde lokal gespeichert. Status: ${currentJob.status}.`;
      await loadHistory();
    } catch (error) {
      searchError = error instanceof Error ? error.message : 'Der Suchjob konnte nicht angelegt werden.';
    } finally {
      searchLoading = false;
    }
  }

  async function loadHistory() {
    historyLoading = true;
    historyError = '';
    try {
      historyJobs = await fetchSearchHistory();
    } catch (error) {
      historyError = error instanceof Error ? error.message : 'Die Suchverläufe konnten nicht geladen werden.';
    } finally {
      historyLoading = false;
    }
  }

  async function loadSettings() {
    settingsLoading = true;
    settingsError = '';
    try {
      settings = await fetchSettings();
    } catch (error) {
      settingsError = error instanceof Error ? error.message : 'Die Einstellungen konnten nicht geladen werden.';
    } finally {
      settingsLoading = false;
    }
  }

  async function saveKey() {
    settingsError = '';
    settingsNotice = '';
    keyTest = null;
    if (!naraApiKeyInput.trim()) {
      settingsError = 'Bitte einen NARA API-Schlüssel eingeben.';
      return;
    }
    try {
      settings = await saveNaraApiKey(naraApiKeyInput.trim());
      naraApiKeyInput = '';
      settingsNotice = 'NARA API-Schlüssel wurde lokal im Betriebssystem-Keyring gespeichert.';
    } catch (error) {
      settingsError = error instanceof Error ? error.message : 'Der NARA API-Schlüssel konnte nicht gespeichert werden.';
    }
  }

  async function runKeyTest() {
    settingsError = '';
    settingsNotice = '';
    keyTest = null;
    try {
      keyTest = await testNaraApiKey();
      settingsNotice = keyTest.message;
    } catch (error) {
      settingsError = error instanceof Error ? error.message : 'Der NARA API-Schlüssel konnte nicht getestet werden.';
    }
  }

  async function removeKey() {
    settingsError = '';
    settingsNotice = '';
    keyTest = null;
    try {
      settings = await deleteNaraApiKey();
      settingsNotice = 'NARA API-Schlüssel wurde gelöscht.';
    } catch (error) {
      settingsError = error instanceof Error ? error.message : 'Der NARA API-Schlüssel konnte nicht gelöscht werden.';
    }
  }
</script>

<header class="topbar">
  <div class="brand">
    <strong>NARATrace</strong>
    <span>Lokale, quellennahe Personensuche im National Archives Catalog</span>
  </div>
  <div class="source">
    <span>Datenquelle: U.S. National Archives and Records Administration - National Archives Catalog</span>
    <span class="badge">NARA Catalog</span>
  </div>
</header>

<nav class="navigation" aria-label="Hauptnavigation">
  {#each navItems as item}
    <a
      href={`#${item.id}`}
      class:active={activeRoute === item.id}
      aria-current={activeRoute === item.id ? 'page' : undefined}
      onclick={(event) => navigate(event, item.id)}
    >
      {item.label}
    </a>
  {/each}
</nav>

<main>
  {#if activeRoute === 'start'}
    <section class="intro">
      <h1>NARATrace</h1>
      <p>
        NARATrace unterstützt historische Archivforschung. Ergebnisse aus OCR und automatischem Matching
        sind Forschungshinweise und keine gesicherten Identifizierungen.
      </p>
      <div class="actions">
        <a class="button" href="#search" onclick={(event) => navigate(event, 'search')}>Personensuche starten</a>
        <button class="button secondary" type="button" onclick={checkBackend} disabled={healthLoading}>
          {healthLoading ? 'Prüfe Backend...' : 'Backend-Status prüfen'}
        </button>
      </div>

      {#if health}
        <section class="status-panel" aria-label="Backend-Status">
          <h2>Backend läuft</h2>
          <dl>
            <dt>Version</dt>
            <dd>{health.version}</dd>
            <dt>Lokale Adresse</dt>
            <dd>{health.bind_host}:{health.bind_port}</dd>
            <dt>Datenverzeichnis</dt>
            <dd>{health.data_dir}</dd>
            <dt>Datenbank</dt>
            <dd>{health.database_path}</dd>
          </dl>
        </section>
      {/if}

      {#if healthError}
        <p class="error">{healthError}</p>
      {/if}
    </section>
  {:else if activeRoute === 'search'}
    <section class="page">
      <h1>Neue Suche</h1>
      <p>
        Je mehr unabhängige Angaben vorhanden sind, desto besser kann NARATrace mögliche Treffer bewerten.
        Automatische Treffer stellen keine gesicherte Identifizierung dar.
      </p>
      <form class="search-form" onsubmit={prepareSearch}>
        <fieldset>
          <legend>Name</legend>
          <label>
            Vorname
            <input bind:value={firstName} autocomplete="given-name" />
          </label>
          <label>
            Nachname
            <input bind:value={lastName} autocomplete="family-name" />
          </label>
          <label class="wide">
            Varianten und alternative Schreibweisen
            <textarea bind:value={variants} rows="4" placeholder="Eine Variante pro Zeile"></textarea>
          </label>
        </fieldset>
        <fieldset>
          <legend>Lebensdaten</legend>
          <label>
            Geburtsdatum
            <input bind:value={birthDate} type="date" />
          </label>
          <label>
            Geburtsjahr oder bekanntes Jahr
            <input bind:value={birthYear} type="number" min="0" max="2100" placeholder="z. B. 1869" />
          </label>
        </fieldset>
        <fieldset>
          <legend>Orte</legend>
          <label class="wide">
            Wohnorte
            <textarea bind:value={residencePlaces} rows="4" placeholder="Ein Wohnort pro Zeile, z. B. Naumburg&#10;Saaleck&#10;Weimar"></textarea>
          </label>
        </fieldset>
        <fieldset>
          <legend>Identifikationsnummern</legend>
          <label>
            Mitgliedsnummer
            <input bind:value={membershipNumber} placeholder="z. B. 347541 oder 347.541" />
          </label>
        </fieldset>
        <fieldset>
          <legend>Archivische Eingrenzung</legend>
          <label>
            NAID
            <input bind:value={naid} placeholder="optional" />
          </label>
          <label>
            Record Group
            <input bind:value={recordGroup} placeholder="optional" />
          </label>
          <label>
            Maximale Kandidatenzahl
            <input bind:value={maxCandidates} type="number" min="1" max="500" />
          </label>
        </fieldset>
        <button class="button" type="submit" disabled={searchLoading}>
          {searchLoading ? 'Lege Suchjob an...' : 'Suchjob anlegen'}
        </button>
      </form>
      {#if searchNotice}
        <p class="notice">{searchNotice}</p>
      {/if}
      {#if searchError}
        <p class="error">{searchError}</p>
      {/if}
      {#if currentJob}
        <section class="status-panel" aria-label="Suchjob-Status">
          <h2>Suchjob gespeichert</h2>
          <dl>
            <dt>Job-ID</dt>
            <dd>{currentJob.id}</dd>
            <dt>Status</dt>
            <dd>{currentJob.status}</dd>
            <dt>Fortschritt</dt>
            <dd>{currentJob.progress_current} von {currentJob.progress_total}</dd>
            <dt>Treffer</dt>
            <dd>{currentJob.result_count}</dd>
            <dt>Mock-Modus</dt>
            <dd>{currentJob.mock_mode ? 'ja' : 'nein'}</dd>
            {#if currentJob.error_message}
              <dt>Fehler</dt>
              <dd>{currentJob.error_message}</dd>
            {/if}
          </dl>
          {#if currentJob.warnings.length > 0}
            <div class="warning-list" aria-label="Warnungen">
              {#each currentJob.warnings as warning}
                <p>{warning}</p>
              {/each}
            </div>
          {/if}
        </section>
      {/if}
      {#if currentResults.length > 0}
        <section class="results" aria-label="Suchergebnisse">
          <h2>Treffer</h2>
          {#each currentResults as result}
            <article class="result-card">
              <div>
                <span class={`source-badge ${result.data_source === 'MOCK' ? 'mock-badge' : ''}`}>
                  Datenquelle: {result.data_source}
                </span>
                <h3>{result.title}</h3>
                <p>{result.category} - MatchScore {result.match_score}</p>
              </div>
              <dl>
                <dt>NAID</dt>
                <dd>{result.naid}</dd>
                <dt>Textursprung</dt>
                <dd>{result.text_origin}</dd>
                <dt>Relevante Seiten</dt>
                <dd>{result.relevant_pages_count}</dd>
              </dl>
              {#if result.evidences.length > 0}
                <ul>
                  {#each result.evidences as evidence}
                    <li>{evidence.label}</li>
                  {/each}
                </ul>
              {/if}
            </article>
          {/each}
        </section>
      {:else if currentJob && currentJob.status === 'failed'}
        <div class="empty-state">
          <h2>Suche nicht ausgeführt</h2>
          <p>{currentJob.error_message ?? 'Der Suchjob konnte nicht abgeschlossen werden.'}</p>
          <p>Öffne die Einstellungen, speichere deinen NARA API-Schlüssel und teste ihn. Danach kann NARATrace echte Kandidaten abrufen.</p>
          <a class="button secondary" href="#settings" onclick={(event) => navigate(event, 'settings')}>Einstellungen öffnen</a>
        </div>
      {:else if currentJob && currentJob.result_count === 0}
        <div class="empty-state">
          <h2>Noch keine Treffer</h2>
          <p>
            Die NARA-Abfrage wurde ausgeführt, aber es wurden keine Kandidaten gefunden. Versuche weniger enge Angaben
            oder weitere Namensvarianten.
          </p>
        </div>
      {/if}
    </section>
  {:else if activeRoute === 'history'}
    <section class="page">
      <h1>Suchverläufe</h1>
      <div class="actions">
        <button class="button secondary" type="button" onclick={loadHistory} disabled={historyLoading}>
          {historyLoading ? 'Lade Suchverläufe...' : 'Suchverläufe aktualisieren'}
        </button>
      </div>
      {#if historyError}
        <p class="error">{historyError}</p>
      {/if}
      {#if historyJobs.length > 0}
        <section class="history-list" aria-label="Gespeicherte Suchläufe">
          {#each historyJobs as job}
            <article class="history-item">
              <h2>{job.title}</h2>
              <dl>
                <dt>Status</dt>
                <dd>{job.status}</dd>
                <dt>Treffer</dt>
                <dd>{job.result_count}</dd>
                <dt>Erstellt</dt>
                <dd>{new Date(job.created_at).toLocaleString('de-DE')}</dd>
              </dl>
              {#if job.warnings.length > 0}
                <p class="notice">{job.warnings[0]}</p>
              {/if}
            </article>
          {/each}
        </section>
      {:else if !historyLoading}
        <div class="empty-state">
          <h2>Noch keine Suchläufe</h2>
          <p>Neue Suchjobs werden lokal in SQLite gespeichert und erscheinen danach hier.</p>
        </div>
      {/if}
    </section>
  {:else if activeRoute === 'local-documents'}
    <section class="page">
      <h1>Lokale Dokumente</h1>
      <div class="empty-state">
        <h2>Lokales Dokument untersuchen</h2>
        <p>Dieser Modus wird für PDF, PNG, JPEG und TIFF vorbereitet. Dateien bleiben lokal und werden nicht hochgeladen.</p>
      </div>
    </section>
  {:else if activeRoute === 'settings'}
    <section class="page">
      <h1>Einstellungen</h1>
      <div class="settings-grid">
        <section class="status-panel">
          <h2>NARA API-Schlüssel</h2>
          <p>
            NARA API-Schlüssel:
            {settings?.nara_api_key_configured ? ` eingerichtet (${settings.nara_api_key_source})` : ' nicht eingerichtet'}
          </p>
          <label>
            API-Schlüssel eintragen oder ändern
            <input bind:value={naraApiKeyInput} type="password" autocomplete="off" placeholder="x-api-key" />
          </label>
          <div class="actions">
            <button class="button" type="button" onclick={saveKey}>Schlüssel speichern</button>
            <button class="button secondary" type="button" onclick={runKeyTest}>Schlüssel testen</button>
            <button class="button secondary" type="button" onclick={removeKey}>Schlüssel löschen</button>
          </div>
        </section>
        <section class="status-panel">
          <h2>Lokale Daten</h2>
          <p>Cache, Dokumente, OCR-Arbeitsdateien und Datenbank werden im lokalen App-Datenverzeichnis gespeichert.</p>
          <button class="button secondary" type="button" onclick={loadSettings} disabled={settingsLoading}>
            {settingsLoading ? 'Lade Status...' : 'Status laden'}
          </button>
        </section>
      </div>
      {#if settingsNotice}
        <p class="notice">{settingsNotice}</p>
      {/if}
      {#if settingsError}
        <p class="error">{settingsError}</p>
      {/if}
      {#if keyTest && !keyTest.ok}
        <p class="error">{keyTest.message}</p>
      {/if}
      {#if settings}
        <section class="status-panel">
          <h2>Aktueller Speicherort</h2>
          <dl>
            <dt>Datenverzeichnis</dt>
            <dd>{settings.data_dir}</dd>
            <dt>Cache</dt>
            <dd>{settings.cache_dir}</dd>
            <dt>Datenbank</dt>
            <dd>{settings.database_path}</dd>
          </dl>
        </section>
      {/if}
    </section>
  {:else if activeRoute === 'methodology'}
    <section class="page">
      <h1>Methodik</h1>
      <div class="method-list">
        <span>Query Expansion</span>
        <span>Candidate Retrieval</span>
        <span>Metadatenbewertung</span>
        <span>Textbewertung</span>
        <span>Ranking mit Evidenz</span>
      </div>
      <p>NARATrace darf keine Person allein aufgrund eines ähnlichen Namens sicher identifizieren.</p>
    </section>
  {:else if activeRoute === 'about'}
    <section class="page">
      <h1>Über NARATrace</h1>
      <p>
        NARATrace ist ein lokales Forschungswerkzeug für quellennahe Arbeit mit dem National Archives Catalog.
        Die Anwendung ist unabhängig und inoffiziell.
      </p>
    </section>
  {/if}
</main>

<footer>
  NARATrace ist ein unabhängiges, inoffizielles Forschungswerkzeug. Es steht nicht in Verbindung mit der
  U.S. National Archives and Records Administration und wird nicht von NARA betrieben oder unterstützt.
</footer>
