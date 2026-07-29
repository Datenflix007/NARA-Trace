<script lang="ts">
  import { onMount } from 'svelte';
  import {
    deleteSearchJob,
    deleteSearchResult,
    deleteNaraApiKey,
    fetchHealth,
    fetchSearchHistory,
    fetchSearchJob,
    fetchSearchResults,
    fetchSettings,
    saveNaraApiKey,
    startSearch,
    testNaraApiKey,
    updateSearchResultTranscript,
    type ApiKeyTestResponse,
    type HealthResponse,
    type NaraApiUsageResponse,
    type SearchJobResponse,
    type SearchResultResponse,
    type SettingsResponse
  } from './lib/api';
  import schultzePage2Url from './assets/demo/schultze-page-2.png';

  type RouteId = 'start' | 'search' | 'history' | 'local-documents' | 'settings' | 'methodology' | 'about' | 'result-detail';
  type DetailOrigin = 'start' | 'history' | 'search';

  type TranscriptLine = {
    id: string;
    label: string;
    value: string;
    note: string;
    box: { x: number; y: number; width: number; height: number };
  };

  type DisplayResult = {
    resultId: number | null;
    jobId: string | null;
    key: string;
    title: string;
    matchScore: number;
    category: string;
    dataSource: 'NARA' | 'MOCK' | 'LOCAL';
    naid: string;
    textOrigin: string;
    name: string;
    birthDate: string;
    birthPlace: string;
    residencePlace: string;
    portraitUrl: string | null;
    sourcePageUrl: string | null;
    sourceCatalogUrl: string | null;
    sourcePageLabel: string;
    lines: TranscriptLine[];
    transcriptText: string;
    transcriptSource: string;
    transcriptEdited: boolean;
    evidence: string[];
  };

  const navItems: { id: Exclude<RouteId, 'result-detail'>; label: string }[] = [
    { id: 'start', label: 'Start' },
    { id: 'search', label: 'Neue Suche' },
    { id: 'history', label: 'Suchverläufe' },
    { id: 'local-documents', label: 'Lokale Dokumente' },
    { id: 'settings', label: 'Einstellungen' },
    { id: 'methodology', label: 'Methodik' },
    { id: 'about', label: 'Über NARATrace' }
  ];

  const routeIds: RouteId[] = [...navItems.map((item) => item.id), 'result-detail'];
  const schultzeNaumburgPhotoUrl = '/demo/schultze-naumburg.png';
  const SEARCH_STATUS_POLL_MS = 1000;
  const SEARCH_STATUS_MAX_POLL_FAILURES = 5;
  const HISTORY_LOAD_RETRY_MS = 800;
  const HISTORY_LOAD_MAX_ATTEMPTS = 8;

  const demoTranscriptLines: TranscriptLine[] = [
    {
      id: 'name',
      label: 'Name',
      value: 'Schultze-Naumburg, Paul',
      note: 'Namensfeld der Mitgliedskarte',
      box: { x: 25.5, y: 27.4, width: 30.5, height: 3.8 }
    },
    {
      id: 'birth-date',
      label: 'Geburtsdatum',
      value: '10.06.1869',
      note: 'Geb.-Datum auf der Karte',
      box: { x: 25.0, y: 32.4, width: 22.0, height: 3.4 }
    },
    {
      id: 'birth-place',
      label: 'Geburtsort',
      value: 'Almrich',
      note: 'Geb.-Ort auf der Karte',
      box: { x: 46.0, y: 32.2, width: 13.5, height: 3.6 }
    },
    {
      id: 'membership',
      label: 'Mitgliedsnummer',
      value: '347 541',
      note: 'Mitgl.-Nr. auf der Karte',
      box: { x: 25.0, y: 35.0, width: 28.0, height: 3.4 }
    },
    {
      id: 'admission',
      label: 'Aufnahme',
      value: '01.11.1930',
      note: 'Aufnahmedatum auf der Karte',
      box: { x: 46.0, y: 35.0, width: 15.0, height: 3.4 }
    },
    {
      id: 'residence',
      label: 'Wohnort',
      value: 'Naumburg',
      note: 'Wohnortangabe aus der Karte',
      box: { x: 7.0, y: 31.2, width: 16.0, height: 3.6 }
    },
    {
      id: 'later-residence',
      label: 'Späterer Wohnort',
      value: 'Weimar',
      note: 'spätere Wohnortangabe aus der Karte',
      box: { x: 6.0, y: 38.0, width: 19.0, height: 3.8 }
    }
  ];

  const demoTranscriptText = demoTranscriptLines.map((line) => `${line.label}: ${line.value}`).join('\n');

  const demoDisplayResults: DisplayResult[] = sortDisplayResults([
    {
      resultId: null,
      jobId: null,
      key: 'demo-local-schultze',
      title: 'Lokale Demo-Datei: Paul Schultze-Naumburg, NSDAP-Kartei 1931',
      matchScore: 96,
      category: 'sehr wahrscheinlich',
      dataSource: 'LOCAL',
      naid: 'LOCAL-PDF-SCHULTZE-NAUMBURG-1931',
      textOrigin: 'lokale PDF, manuell transkribierte Demo-Zeilen',
      name: 'Paul Schultze-Naumburg',
      birthDate: '10.06.1869',
      birthPlace: 'Almrich',
      residencePlace: 'Naumburg; später Weimar',
      portraitUrl: schultzeNaumburgPhotoUrl,
      sourcePageUrl: schultzePage2Url,
      sourceCatalogUrl: null,
      sourcePageLabel: 'SchulzeNaumburg_NSDAP_Kartei1931.pdf, Seite 2',
      lines: demoTranscriptLines,
      transcriptText: demoTranscriptText,
      transcriptSource: 'manuelle Demo-Transkription',
      transcriptEdited: false,
      evidence: ['Name und Mitgliedsnummer passen.', 'Geburtsort Almrich sowie Wohnorte Naumburg und später Weimar stützen den Treffer.', 'Aktenfoto ist in Seite 4 der lokalen PDF enthalten.']
    },
    {
      resultId: null,
      jobId: null,
      key: 'demo-mock-possible',
      title: 'MOCK-DATENSATZ: ähnliche Schreibweise ohne sichere Lebensdaten',
      matchScore: 58,
      category: 'möglich',
      dataSource: 'MOCK',
      naid: 'MOCK-NAID-0002',
      textOrigin: 'künstlicher Vergleichstreffer',
      name: 'Paul Schultze Naumburg',
      birthDate: 'nicht belegt',
      birthPlace: 'nicht belegt',
      residencePlace: 'Naumburg ähnlich',
      portraitUrl: null,
      sourcePageUrl: null,
      sourceCatalogUrl: null,
      sourcePageLabel: 'kein lokales Bild',
      lines: [],
      transcriptText: '',
      transcriptSource: 'kein Transkript',
      transcriptEdited: false,
      evidence: ['Namensähnlichkeit vorhanden.', 'Geburtsdaten fehlen.']
    },
    {
      resultId: null,
      jobId: null,
      key: 'demo-mock-weak',
      title: 'MOCK-DATENSATZ: widersprüchliche Personendaten',
      matchScore: 34,
      category: 'schwach',
      dataSource: 'MOCK',
      naid: 'MOCK-NAID-0003',
      textOrigin: 'künstlicher Vergleichstreffer',
      name: 'Paul Schulze',
      birthDate: 'abweichend',
      birthPlace: 'nicht belegt',
      residencePlace: 'abweichender Ort',
      portraitUrl: null,
      sourcePageUrl: null,
      sourceCatalogUrl: null,
      sourcePageLabel: 'kein lokales Bild',
      lines: [],
      transcriptText: '',
      transcriptSource: 'kein Transkript',
      transcriptEdited: false,
      evidence: ['Nachname teilweise ähnlich.', 'Geburtsdatum widerspricht dem Suchprofil.']
    }
  ]);

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
  let searchProgressHint = '';
  let searchStartedAt: number | null = null;
  let searchNow = Date.now();
  let searchTimer: ReturnType<typeof setInterval> | null = null;
  let searchRuntimeEstimateSeconds = 0;
  let searchRuntimeEstimateKey = '';
  let currentJob: SearchJobResponse | null = null;
  let currentResults: DisplayResult[] = [];
  let historyJobs: SearchJobResponse[] = [];
  let selectedHistoryJob: SearchJobResponse | null = null;
  let selectedHistoryResults: DisplayResult[] = [];
  let historyLoading = false;
  let historyResultsLoading = false;
  let deletingJobId = '';
  let deletingResultId: number | null = null;
  let historyError = '';
  let historyHint = '';
  let settings: SettingsResponse | null = null;
  let settingsLoading = false;
  let settingsError = '';
  let settingsNotice = '';
  let naraApiKeyInput = '';
  let keyTest: ApiKeyTestResponse | null = null;
  let detailResult: DisplayResult | null = null;
  let detailOrigin: DetailOrigin = 'start';
  let hoveredLineId = '';
  let pinnedLineId = '';
  let transcriptDraft = '';
  let transcriptDrafts: Record<string, string> = {};
  let transcriptSaving = false;
  let transcriptSavingKey = '';
  let transcriptNotice = '';
  let transcriptError = '';
  let transcriptNotices: Record<string, string> = {};
  let transcriptErrors: Record<string, string> = {};

  $: focusedLineId = hoveredLineId || pinnedLineId;
  $: currentSearchProgressPercent = searchProgressPercent(currentJob);
  $: currentSearchProgressLabel = searchProgressLabel(currentJob);
  $: currentSearchElapsedSeconds = calculateSearchElapsedSeconds(searchStartedAt, searchNow);
  $: currentEstimatedTotalRuntimeLabel = estimatedTotalRuntimeLabel(
    currentJob,
    currentSearchElapsedSeconds,
    searchRuntimeEstimateSeconds
  );
  $: currentEstimatedRemainingRuntimeLabel = estimatedRemainingRuntimeLabel(
    currentJob,
    currentSearchElapsedSeconds,
    searchRuntimeEstimateSeconds
  );
  $: currentSearchSubmitLabel = searchLoading ? (currentJob ? 'Suchjob läuft...' : 'Lege Suchjob an...') : 'Suchjob anlegen';

  onMount(() => {
    const syncRoute = () => {
      activeRoute = routeFromHash(window.location.hash);
    };

    syncRoute();
    void loadSettings();
    if (activeRoute === 'history') {
      void loadHistory();
    }
    window.addEventListener('hashchange', syncRoute);

    return () => {
      stopSearchTimer();
      window.removeEventListener('hashchange', syncRoute);
    };
  });

  function routeFromHash(hash: string): RouteId {
    const route = hash.replace(/^#\/?/, '') as RouteId;
    if (route === 'result-detail' && !detailResult) {
      return 'start';
    }
    return routeIds.includes(route) ? route : 'start';
  }

  function navigate(event: MouseEvent, route: Exclude<RouteId, 'result-detail'>) {
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

  function sortDisplayResults(results: DisplayResult[]): DisplayResult[] {
    return [...results].sort((left, right) => {
      const displayPriority = Number(Boolean(right.sourcePageUrl)) - Number(Boolean(left.sourcePageUrl));
      return displayPriority || right.matchScore - left.matchScore;
    });
  }

  function sourceBadgeClass(source: DisplayResult['dataSource']) {
    if (source === 'LOCAL') return 'local-badge';
    if (source === 'MOCK') return 'mock-badge';
    return '';
  }

  function scoreLabel(score: number) {
    return `${Math.round(score)} %`;
  }

  function apiUsageLabel(usage: NaraApiUsageResponse) {
    return `${formatApiUsagePercent(usage.percent_used)} % (${usage.request_count}/${usage.request_limit})`;
  }

  function formatApiUsagePercent(value: number) {
    const digits = value > 0 && value < 10 ? 1 : 0;
    return new Intl.NumberFormat('de-DE', { maximumFractionDigits: digits }).format(value);
  }

  function apiUsageTone(usage: NaraApiUsageResponse) {
    if (usage.percent_used >= 90) return 'danger';
    if (usage.percent_used >= 70) return 'warning';
    return 'ok';
  }

  function terminalJobStatus(status: string) {
    return status === 'complete' || status === 'failed' || status === 'cancelled';
  }

  function searchStepLabel(job: SearchJobResponse | null) {
    const status = job?.status ?? 'queued';
    const labels: Record<string, string> = {
      queued: 'Suchlauf wird angelegt',
      preparing_search: 'Suchprofil, Varianten und Abfrage werden vorbereitet',
      searching_catalog: 'NARA Catalog wird abgefragt',
      downloading_pages_ocr: 'Originalseiten werden geladen und OCR wird vorbereitet',
      ranking: 'Treffer werden bewertet und lokal gespeichert',
      complete: 'Suche abgeschlossen',
      failed: 'Suche fehlgeschlagen',
      cancelled: 'Suche abgebrochen'
    };
    return labels[status] ?? status;
  }

  function searchProgressPercent(job: SearchJobResponse | null) {
    if (!job || job.progress_total <= 0) return 3;
    return Math.max(3, Math.min(100, Math.round((job.progress_current / job.progress_total) * 100)));
  }

  function searchProgressLabel(job: SearchJobResponse | null) {
    if (!job) return `0 von 6 Schritten (${searchProgressPercent(job)} %)`;
    if (job.progress_total <= 0) return `${searchProgressPercent(job)} %`;
    return `${job.progress_current} von ${job.progress_total} Schritten (${searchProgressPercent(job)} %)`;
  }

  function formatDuration(seconds: number) {
    const clamped = Math.max(0, Math.round(seconds));
    const minutes = Math.floor(clamped / 60);
    const restSeconds = clamped % 60;
    if (minutes <= 0) return `${restSeconds} s`;
    return `${minutes} min ${restSeconds.toString().padStart(2, '0')} s`;
  }

  function calculateSearchElapsedSeconds(startedAt: number | null, now: number) {
    if (!startedAt) return 0;
    return Math.max(0, (now - startedAt) / 1000);
  }

  function formatEstimatedDuration(seconds: number) {
    const clamped = Math.max(0, seconds);
    if (clamped === 0) return formatDuration(0);
    const step = clamped < 90 ? 5 : 15;
    return formatDuration(Math.max(step, Math.round(clamped / step) * step));
  }

  function estimatedTotalRuntimeLabel(job: SearchJobResponse | null, elapsedSeconds: number, estimateSeconds: number) {
    if (job && terminalJobStatus(job.status)) {
      return formatDuration(elapsedSeconds);
    }
    const estimateWithOverrun = elapsedSeconds > estimateSeconds ? elapsedSeconds + 5 : estimateSeconds;
    return `ca. ${formatEstimatedDuration(estimateWithOverrun)}`;
  }

  function estimatedRemainingRuntimeLabel(job: SearchJobResponse | null, elapsedSeconds: number, estimateSeconds: number) {
    if (job && terminalJobStatus(job.status)) {
      return '0 s';
    }
    const remainingSeconds = estimateSeconds - elapsedSeconds;
    if (remainingSeconds <= 0) return 'ca. < 5 s';
    return `ca. ${formatEstimatedDuration(remainingSeconds)}`;
  }

  function initialSearchRuntimeEstimate(job: SearchJobResponse | null) {
    if (job?.mock_mode) return 8;
    const candidateBudget = Math.max(1, Math.min(maxCandidates, 100));
    return 20 + candidateBudget * 0.7;
  }

  function updateSearchRuntimeEstimate(job: SearchJobResponse | null) {
    if (!job) {
      searchRuntimeEstimateSeconds = initialSearchRuntimeEstimate(null);
      searchRuntimeEstimateKey = '';
      return;
    }

    const estimateKey = `${job.status}:${job.progress_current}:${job.progress_total}`;
    if (estimateKey === searchRuntimeEstimateKey && !terminalJobStatus(job.status)) {
      return;
    }
    searchRuntimeEstimateKey = estimateKey;

    const baselineEstimate = initialSearchRuntimeEstimate(job);
    const elapsedSeconds = calculateSearchElapsedSeconds(searchStartedAt, Date.now());
    if (terminalJobStatus(job.status)) {
      searchRuntimeEstimateSeconds = elapsedSeconds;
      return;
    }
    if (elapsedSeconds < 2 || job.progress_current <= 0 || job.progress_total <= 0) {
      searchRuntimeEstimateSeconds = baselineEstimate;
      return;
    }

    const progressFraction = Math.min(0.95, Math.max(0.1, job.progress_current / job.progress_total));
    const observedTotal = elapsedSeconds / progressFraction;
    const blendedEstimate = baselineEstimate * 0.65 + observedTotal * 0.35;
    searchRuntimeEstimateSeconds = Math.max(baselineEstimate * 0.75, Math.min(baselineEstimate * 1.75, blendedEstimate));
  }

  function startSearchTimer() {
    searchStartedAt = Date.now();
    searchNow = searchStartedAt;
    if (searchTimer) {
      clearInterval(searchTimer);
    }
    searchTimer = setInterval(() => {
      searchNow = Date.now();
    }, 1000);
  }

  function stopSearchTimer() {
    if (searchStartedAt) {
      searchNow = Date.now();
    }
    if (searchTimer) {
      clearInterval(searchTimer);
      searchTimer = null;
    }
  }

  function wait(milliseconds: number) {
    return new Promise((resolve) => window.setTimeout(resolve, milliseconds));
  }

  async function retryHistoryRequest<T>(request: () => Promise<T>, retryLabel: string) {
    let lastError: unknown = null;
    for (let attempt = 1; attempt <= HISTORY_LOAD_MAX_ATTEMPTS; attempt += 1) {
      try {
        const response = await request();
        historyHint = '';
        return response;
      } catch (error) {
        lastError = error;
        if (attempt >= HISTORY_LOAD_MAX_ATTEMPTS) {
          break;
        }
        historyHint = `${retryLabel} (${attempt + 1}. Versuch).`;
        await wait(HISTORY_LOAD_RETRY_MS);
      }
    }
    throw lastError;
  }

  async function pollSearchJob(jobId: string) {
    let latestJob = currentJob;
    let consecutivePollFailures = 0;
    while (latestJob && !terminalJobStatus(latestJob.status)) {
      await wait(SEARCH_STATUS_POLL_MS);
      try {
        latestJob = await fetchSearchJob(jobId);
        currentJob = latestJob;
        updateSearchRuntimeEstimate(latestJob);
        consecutivePollFailures = 0;
        searchProgressHint = '';
      } catch {
        consecutivePollFailures += 1;
        if (consecutivePollFailures >= SEARCH_STATUS_MAX_POLL_FAILURES) {
          searchProgressHint = `Statusantwort seit ${consecutivePollFailures} Versuchen unterbrochen. NARATrace wartet weiter auf den laufenden Suchjob.`;
          continue;
        }
        const attemptLabel = consecutivePollFailures > 1 ? ` (${consecutivePollFailures}. Versuch)` : '';
        searchProgressHint = `Statusantwort kurz unterbrochen${attemptLabel}. Der Suchjob läuft weiter.`;
      }
    }
    return latestJob;
  }

  function initials(name: string) {
    return name
      .split(/\s+/)
      .filter(Boolean)
      .slice(0, 2)
      .map((part) => part[0]?.toUpperCase())
      .join('');
  }

  function formatDate(value: string | null) {
    if (!value) return '';
    const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
    if (!match) return value;
    return `${match[3]}.${match[2]}.${match[1]}`;
  }

  function displayResultFromResponse(result: SearchResultResponse): DisplayResult {
    const isLocal = result.data_source === 'LOCAL' || result.naid.startsWith('LOCAL-');
    const evidence = result.evidences.map((evidence) => (evidence.detail ? `${evidence.label}: ${evidence.detail}` : evidence.label));
    const transcriptText = result.transcript_text?.trim() || (isLocal ? demoTranscriptText : evidence.join('\n'));
    return {
      resultId: result.id,
      jobId: result.job_id,
      key: `${result.job_id}-${result.id}`,
      title: result.title ?? 'Ohne Titel',
      matchScore: result.match_score,
      category: result.category,
      dataSource: result.data_source,
      naid: result.naid,
      textOrigin: result.text_origin,
      name: result.suspected_person_name || result.title || 'Nicht ermittelt',
      birthDate: formatDate(result.birth_date) || (isLocal ? '10.06.1869' : 'nicht ermittelt'),
      birthPlace: result.birth_place || (isLocal ? 'Almrich' : 'nicht ermittelt'),
      residencePlace: isLocal ? 'Naumburg; später Weimar' : 'nicht ermittelt',
      portraitUrl: isLocal ? schultzeNaumburgPhotoUrl : null,
      sourcePageUrl: isLocal ? schultzePage2Url : result.source_page_url,
      sourceCatalogUrl: isLocal ? null : result.original_url,
      sourcePageLabel: isLocal
        ? 'SchulzeNaumburg_NSDAP_Kartei1931.pdf, Seite 2'
        : result.source_page_label || result.original_url || 'kein lokales Bild',
      lines: isLocal ? demoTranscriptLines : [],
      transcriptText,
      transcriptSource: isLocal ? 'manuelle Demo-Transkription' : result.transcript_source || result.text_origin,
      transcriptEdited: Boolean(result.transcript_edited),
      evidence
    };
  }

  function hotspotStyle(line: TranscriptLine) {
    return `left: ${line.box.x}%; top: ${line.box.y}%; width: ${line.box.width}%; height: ${line.box.height}%;`;
  }

  function transcriptRowsFor(result: DisplayResult): TranscriptLine[] {
    if (result.lines.length > 0) {
      return result.lines;
    }
    const rows = [
      buildTranscriptRow(result, 'name', 'Name', result.name, 'aus Suchprofil oder NARA-Metadaten'),
      buildTranscriptRow(result, 'birth-date', 'Geburtsdatum', result.birthDate, 'aus NARA-Text, OCR oder Suchprofil'),
      buildTranscriptRow(result, 'birth-place', 'Geburtsort', result.birthPlace, 'aus NARA-Text, OCR oder Suchprofil'),
      buildTranscriptRow(result, 'residence', 'Wohnort', result.residencePlace, 'aus NARA-Text, OCR oder Suchprofil')
    ].filter((line): line is TranscriptLine => Boolean(line));
    return rows.length > 0
      ? rows
      : [buildTranscriptRow(result, 'title', 'Datensatz', result.title, 'NARA-Metadaten') as TranscriptLine];
  }

  function buildTranscriptRow(
    result: DisplayResult,
    id: string,
    label: string,
    value: string,
    note: string
  ): TranscriptLine | null {
    const cleaned = value.trim();
    if (!cleaned || ['nicht ermittelt', 'nicht belegt', 'abweichend'].includes(cleaned.toLowerCase())) {
      return null;
    }
    return {
      id: `${result.key}-${id}`,
      label,
      value: cleaned,
      note,
      box: { x: 0, y: 0, width: 0, height: 0 }
    };
  }

  function transcriptDraftFor(result: DisplayResult) {
    return transcriptDrafts[result.key] ?? result.transcriptText;
  }

  function transcriptNoticeFor(result: DisplayResult) {
    return transcriptNotices[result.key] ?? '';
  }

  function transcriptErrorFor(result: DisplayResult) {
    return transcriptErrors[result.key] ?? '';
  }

  function isTranscriptSaving(result: DisplayResult) {
    return transcriptSavingKey === result.key;
  }

  function updateTranscriptDraft(result: DisplayResult, event: Event) {
    transcriptDrafts = {
      ...transcriptDrafts,
      [result.key]: (event.currentTarget as HTMLTextAreaElement).value
    };
  }

  function clearTranscriptMessages(result: DisplayResult) {
    transcriptNotices = { ...transcriptNotices, [result.key]: '' };
    transcriptErrors = { ...transcriptErrors, [result.key]: '' };
  }

  function setTranscriptNotice(result: DisplayResult, message: string) {
    transcriptNotices = { ...transcriptNotices, [result.key]: message };
    transcriptErrors = { ...transcriptErrors, [result.key]: '' };
  }

  function setTranscriptError(result: DisplayResult, message: string) {
    transcriptErrors = { ...transcriptErrors, [result.key]: message };
    transcriptNotices = { ...transcriptNotices, [result.key]: '' };
  }

  function openResultDetail(result: DisplayResult, origin: DetailOrigin) {
    detailResult = result;
    detailOrigin = origin;
    hoveredLineId = '';
    pinnedLineId = '';
    transcriptDraft = result.transcriptText;
    transcriptNotice = '';
    transcriptError = '';
    activeRoute = 'result-detail';
    window.location.hash = 'result-detail';
  }

  function openResultDetailWithKeyboard(event: KeyboardEvent, result: DisplayResult, origin: DetailOrigin) {
    if (event.key !== 'Enter' && event.key !== ' ') {
      return;
    }
    event.preventDefault();
    openResultDetail(result, origin);
  }

  function backFromDetail() {
    const route = detailOrigin === 'history' ? 'history' : detailOrigin === 'search' ? 'search' : 'start';
    activeRoute = route;
    window.location.hash = route;
  }

  function setHoveredLine(lineId: string) {
    hoveredLineId = lineId;
  }

  function clearHoveredLine() {
    hoveredLineId = '';
  }

  function togglePinnedLine(lineId: string) {
    pinnedLineId = pinnedLineId === lineId ? '' : lineId;
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
    searchProgressHint = '';
    currentJob = null;
    currentResults = [];
    updateSearchRuntimeEstimate(null);
    startSearchTimer();
    try {
      const startedJob = await startSearch({
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
      currentJob = startedJob;
      updateSearchRuntimeEstimate(startedJob);
      const finishedJob = terminalJobStatus(startedJob.status) ? startedJob : await pollSearchJob(startedJob.id);
      if (finishedJob) {
        currentJob = finishedJob;
        updateSearchRuntimeEstimate(finishedJob);
      }
      if (currentJob && terminalJobStatus(currentJob.status)) {
        searchProgressHint = '';
      }
      await loadSettings();
      if (currentJob?.status === 'complete') {
        const results = await fetchSearchResults(startedJob.id);
        currentResults = sortDisplayResults(results.map(displayResultFromResponse));
        searchNotice = `Suchjob für "${name}" abgeschlossen. ${currentJob.result_count} Treffer gespeichert.`;
      } else if (currentJob?.status === 'failed') {
        searchError = currentJob.error_message ?? 'Der Suchjob konnte nicht abgeschlossen werden.';
      } else if (currentJob?.status === 'cancelled') {
        searchNotice = `Suchjob für "${name}" wurde abgebrochen.`;
      } else {
        searchNotice = `Suchjob für "${name}" wurde lokal gespeichert. Status: ${currentJob?.status ?? startedJob.status}.`;
      }
      await loadHistory();
    } catch (error) {
      searchError = error instanceof Error ? error.message : 'Der Suchjob konnte nicht angelegt werden.';
    } finally {
      searchLoading = false;
      stopSearchTimer();
    }
  }

  async function loadHistory() {
    historyLoading = true;
    historyError = '';
    historyHint = '';
    try {
      historyJobs = await retryHistoryRequest(fetchSearchHistory, 'Suchverläufe konnten kurz nicht geladen werden');
    } catch (error) {
      historyHint = '';
      historyError = error instanceof Error ? error.message : 'Die Suchverläufe konnten nicht geladen werden.';
    } finally {
      historyLoading = false;
    }
  }

  async function openHistoryJob(job: SearchJobResponse) {
    selectedHistoryJob = job;
    selectedHistoryResults = [];
    historyResultsLoading = true;
    historyError = '';
    historyHint = '';
    try {
      const results = await retryHistoryRequest(
        () => fetchSearchResults(job.id),
        'Treffer konnten kurz nicht geladen werden'
      );
      selectedHistoryResults = sortDisplayResults(results.map(displayResultFromResponse));
    } catch (error) {
      historyHint = '';
      historyError = error instanceof Error ? error.message : 'Die Treffer konnten nicht geladen werden.';
    } finally {
      historyResultsLoading = false;
    }
  }

  async function removeHistoryJob(job: SearchJobResponse) {
    if (!window.confirm(`Suchlauf "${job.title}" wirklich löschen?`)) {
      return;
    }
    deletingJobId = job.id;
    historyError = '';
    try {
      await deleteSearchJob(job.id);
      historyJobs = historyJobs.filter((historyJob) => historyJob.id !== job.id);
      if (selectedHistoryJob?.id === job.id) {
        selectedHistoryJob = null;
        selectedHistoryResults = [];
      }
    } catch (error) {
      historyError = error instanceof Error ? error.message : 'Der Suchlauf konnte nicht gelöscht werden.';
    } finally {
      deletingJobId = '';
    }
  }

  async function removeHistoryResult(result: DisplayResult) {
    if (!selectedHistoryJob || result.resultId === null) {
      return;
    }
    if (!window.confirm(`Treffer "${result.name}" aus diesem Suchlauf löschen?`)) {
      return;
    }
    deletingResultId = result.resultId;
    historyError = '';
    try {
      await deleteSearchResult(selectedHistoryJob.id, result.resultId);
      selectedHistoryResults = selectedHistoryResults.filter((historyResult) => historyResult.resultId !== result.resultId);
      const nextResultCount = Math.max(0, selectedHistoryJob.result_count - 1);
      selectedHistoryJob = { ...selectedHistoryJob, result_count: nextResultCount };
      historyJobs = historyJobs.map((historyJob) =>
        historyJob.id === selectedHistoryJob?.id ? { ...historyJob, result_count: nextResultCount } : historyJob
      );
      if (detailResult?.resultId === result.resultId) {
        detailResult = null;
      }
    } catch (error) {
      historyError = error instanceof Error ? error.message : 'Der Treffer konnte nicht gelöscht werden.';
    } finally {
      deletingResultId = null;
    }
  }

  async function saveTranscript() {
    if (!detailResult) {
      return;
    }
    await saveResultTranscript(detailResult, transcriptDraft);
  }

  async function saveResultTranscript(result: DisplayResult, draftOverride?: string) {
    const draft = draftOverride ?? transcriptDraftFor(result);
    if (!result.jobId || result.resultId === null) {
      const message = 'Diese Beispielansicht kann nicht gespeichert werden.';
      setTranscriptError(result, message);
      if (detailResult?.key === result.key) {
        transcriptError = message;
        transcriptNotice = '';
      }
      return;
    }
    if (!draft.trim()) {
      const message = 'Die Transkription darf nicht leer sein.';
      setTranscriptError(result, message);
      if (detailResult?.key === result.key) {
        transcriptError = message;
        transcriptNotice = '';
      }
      return;
    }
    transcriptSaving = true;
    transcriptSavingKey = result.key;
    clearTranscriptMessages(result);
    if (detailResult?.key === result.key) {
      transcriptError = '';
      transcriptNotice = '';
    }
    try {
      const updatedResult = await updateSearchResultTranscript(result.jobId, result.resultId, draft);
      applyUpdatedResult(updatedResult);
      setTranscriptNotice(result, 'Transkription gespeichert.');
      if (detailResult?.key === result.key) {
        transcriptNotice = 'Transkription gespeichert.';
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Die Transkription konnte nicht gespeichert werden.';
      setTranscriptError(result, message);
      if (detailResult?.key === result.key) {
        transcriptError = message;
      }
    } finally {
      transcriptSaving = false;
      transcriptSavingKey = '';
    }
  }

  function applyUpdatedResult(result: SearchResultResponse) {
    const updated = displayResultFromResponse(result);
    currentResults = sortDisplayResults(currentResults.map((item) => (item.resultId === updated.resultId ? updated : item)));
    selectedHistoryResults = sortDisplayResults(
      selectedHistoryResults.map((item) => (item.resultId === updated.resultId ? updated : item))
    );
    transcriptDrafts = { ...transcriptDrafts, [updated.key]: updated.transcriptText };
    if (detailResult?.resultId === updated.resultId) {
      detailResult = updated;
      transcriptDraft = updated.transcriptText;
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
      await loadSettings();
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
    {#if settings?.nara_api_key_configured}
      <span class={`quota-badge ${apiUsageTone(settings.nara_api_usage)}`}>
        NARA API: {apiUsageLabel(settings.nara_api_usage)}
      </span>
    {/if}
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
      <div class="intro-copy">
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
      </div>

      <section class="example-panel" aria-label="Anzeige-Beispiel">
        <div class="section-heading">
          <span class="eyebrow">Anzeige-Beispiel</span>
          <h2>Paul Schultze-Naumburg</h2>
        </div>
        <div class="ranked-list compact">
          {#each demoDisplayResults as result}
            <button class="match-row" type="button" onclick={() => openResultDetail(result, 'start')}>
              <span class="portrait-frame">
                {#if result.portraitUrl}
                  <img src={result.portraitUrl} alt={`Aktenfoto ${result.name}`} />
                {:else}
                  <span class="portrait-placeholder">{initials(result.name)}</span>
                {/if}
              </span>
              <span class="match-summary">
                <span class="match-topline">
                  <span class={`source-badge ${sourceBadgeClass(result.dataSource)}`}>{result.dataSource}</span>
                  <span class="score-pill">{scoreLabel(result.matchScore)}</span>
                </span>
                <span class="match-name">{result.name}</span>
                <span class="match-record">{result.naid}</span>
                <span class="match-facts">
                  <span>Geburtsdatum: {result.birthDate}</span>
                  <span>Wohnort: {result.residencePlace}</span>
                </span>
              </span>
            </button>
          {/each}
        </div>
      </section>

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
    <section class="page search-page">
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
          {currentSearchSubmitLabel}
        </button>
      </form>
      {#if searchLoading}
        <div class="search-progress-overlay" role="status" aria-live="polite">
          <section class="search-progress-panel" aria-label="Suchfortschritt">
            <div class="progress-summary">
              <span>Aktueller Schritt</span>
              <strong>{searchStepLabel(currentJob)}</strong>
            </div>
            <div
              class="progress-bar"
              role="progressbar"
              aria-label="Fortschritt des Suchjobs"
              aria-valuemin="0"
              aria-valuemax="100"
              aria-valuenow={currentSearchProgressPercent}
            >
              <span style={`width: ${currentSearchProgressPercent}%;`}></span>
            </div>
            <div class="progress-stats">
              <span>
                <strong>{currentSearchProgressLabel}</strong>
                <small>Aktueller Fortschritt</small>
              </span>
              <span>
                <strong>{currentEstimatedTotalRuntimeLabel}</strong>
                <small>Voraussichtliche Laufzeit</small>
              </span>
              <span>
                <strong>{currentEstimatedRemainingRuntimeLabel}</strong>
                <small>Restzeit</small>
              </span>
              <span>
                <strong>{formatDuration(currentSearchElapsedSeconds)}</strong>
                <small>Suchlaufzeit</small>
              </span>
            </div>
            {#if searchProgressHint}
              <p class="progress-hint">{searchProgressHint}</p>
            {/if}
          </section>
        </div>
      {/if}
      {#if searchNotice}
        <p class="notice">{searchNotice}</p>
      {/if}
      {#if searchError}
        <p class="error">{searchError}</p>
      {/if}
      {#if currentJob && !searchLoading}
        <section class="status-panel" aria-label="Suchjob-Status">
          <h2>{terminalJobStatus(currentJob.status) ? 'Suchjob gespeichert' : 'Suchjob läuft'}</h2>
          <div class="progress-tracker" aria-live="polite">
            <div class="progress-summary">
              <span>Aktueller Schritt</span>
              <strong>{searchStepLabel(currentJob)}</strong>
            </div>
            <div
              class="progress-bar"
              role="progressbar"
              aria-label="Fortschritt des Suchjobs"
              aria-valuemin="0"
              aria-valuemax="100"
              aria-valuenow={currentSearchProgressPercent}
            >
              <span style={`width: ${currentSearchProgressPercent}%;`}></span>
            </div>
            <div class="progress-stats">
              <span>
                <strong>{currentSearchProgressPercent} %</strong>
                <small>Fortschritt</small>
              </span>
              <span>
                <strong>{currentEstimatedRemainingRuntimeLabel}</strong>
                <small>Restzeit</small>
              </span>
              <span>
                <strong>{currentEstimatedTotalRuntimeLabel}</strong>
                <small>Erwartete Gesamtzeit</small>
              </span>
              <span>
                <strong>{formatDuration(currentSearchElapsedSeconds)}</strong>
                <small>Bisherige Laufzeit</small>
              </span>
            </div>
          </div>
          <dl>
            <dt>Job-ID</dt>
            <dd>{currentJob.id}</dd>
            <dt>Status</dt>
            <dd>{currentJob.status}</dd>
            <dt>Fortschritt</dt>
            <dd>{currentSearchProgressLabel}</dd>
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
          <div class="section-heading">
            <span class="eyebrow">Treffer</span>
            <h2>Nach Trefferwahrscheinlichkeit</h2>
          </div>
          <div class="result-card-list">
            {#each currentResults as result}
              <article class="result-card" aria-label={`Treffer ${result.name}`}>
                <div class="result-card-header">
                  <div>
                    <div class="match-topline">
                    <span class={`source-badge ${sourceBadgeClass(result.dataSource)}`}>{result.dataSource}</span>
                    <span class="score-pill">{scoreLabel(result.matchScore)}</span>
                    </div>
                    <h3>{result.name}</h3>
                    <p>{result.category} · Trefferwahrscheinlichkeit {scoreLabel(result.matchScore)} · {result.naid}</p>
                  </div>
                  <button class="button secondary" type="button" onclick={() => openResultDetail(result, 'search')}>
                    Vollansicht öffnen
                  </button>
                </div>

                <div class="detail-shell inline-detail-shell">
                  <section class="original-pane" aria-label={`Originalseite ${result.name}`}>
                    <div class="section-heading">
                      <span class="eyebrow">Originalseite</span>
                      <h2>{result.sourcePageLabel}</h2>
                    </div>
                    {#if result.sourcePageUrl}
                      <div class="document-stage">
                        <img src={result.sourcePageUrl} alt={result.sourcePageLabel} />
                        {#each result.lines as line}
                          <button
                            class="document-hotspot"
                            class:active={focusedLineId === line.id}
                            style={hotspotStyle(line)}
                            type="button"
                            aria-label={line.label}
                            onmouseenter={() => setHoveredLine(line.id)}
                            onmouseleave={clearHoveredLine}
                            onfocus={() => setHoveredLine(line.id)}
                            onblur={clearHoveredLine}
                            onclick={() => togglePinnedLine(line.id)}
                          >
                            <span>{line.label}</span>
                          </button>
                        {/each}
                      </div>
                    {:else if result.sourceCatalogUrl}
                      <div class="catalog-preview">
                        <iframe title={`NARA Catalog Datensatz ${result.naid}`} src={result.sourceCatalogUrl}></iframe>
                        <div class="catalog-preview-link">
                          <a class="button secondary" href={result.sourceCatalogUrl} target="_blank" rel="noreferrer">
                            NARA-Datensatz öffnen
                          </a>
                        </div>
                      </div>
                    {:else}
                      <div class="empty-state compact-empty">
                        <h2>Kein lokales Originalbild</h2>
                        <p>Für diesen Treffer ist noch keine Bildseite im lokalen Cache vorhanden.</p>
                      </div>
                    {/if}
                  </section>

                  <section class="transcript-pane" aria-label={`Transkript ${result.name}`}>
                    <div class="section-heading">
                      <span class="eyebrow">Transkript</span>
                      <h2>Personendaten</h2>
                    </div>
                    <div class="identity-grid">
                      <span>
                        <strong>Name</strong>
                        {result.name}
                      </span>
                      <span>
                        <strong>Geburtsdatum</strong>
                        {result.birthDate}
                      </span>
                      <span>
                        <strong>Geburtsort</strong>
                        {result.birthPlace}
                      </span>
                      <span>
                        <strong>Wohnort</strong>
                        {result.residencePlace}
                      </span>
                    </div>
                    <div class="transcript-lines">
                      {#each transcriptRowsFor(result) as line}
                        <button
                          class="transcript-line"
                          class:active={focusedLineId === line.id}
                          type="button"
                          onmouseenter={() => setHoveredLine(line.id)}
                          onmouseleave={clearHoveredLine}
                          onfocus={() => setHoveredLine(line.id)}
                          onblur={clearHoveredLine}
                          onclick={() => togglePinnedLine(line.id)}
                        >
                          <span>{line.label}</span>
                          <strong>{line.value}</strong>
                          <small>{line.note}</small>
                        </button>
                      {/each}
                    </div>
                    <div class="transcript-editor-panel">
                      <div class="transcript-meta">
                        <span>{result.transcriptSource}</span>
                        {#if result.transcriptEdited}
                          <span>manuell korrigiert</span>
                        {/if}
                      </div>
                      <label>
                        Transkription
                        <textarea
                          class="transcript-editor"
                          value={transcriptDraftFor(result)}
                          rows="16"
                          oninput={(event) => updateTranscriptDraft(result, event)}
                        ></textarea>
                      </label>
                      <div class="actions">
                        <button
                          class="button"
                          type="button"
                          onclick={() => saveResultTranscript(result)}
                          disabled={isTranscriptSaving(result) || result.resultId === null}
                        >
                          {isTranscriptSaving(result) ? 'Speichere...' : 'Transkription speichern'}
                        </button>
                      </div>
                      {#if transcriptNoticeFor(result)}
                        <p class="notice compact-message">{transcriptNoticeFor(result)}</p>
                      {/if}
                      {#if transcriptErrorFor(result)}
                        <p class="error compact-message">{transcriptErrorFor(result)}</p>
                      {/if}
                    </div>
                    {#if result.evidence.length > 0}
                      <div class="evidence-list">
                        {#each result.evidence as evidence}
                          <p>{evidence}</p>
                        {/each}
                      </div>
                    {/if}
                  </section>
                </div>
              </article>
            {/each}
          </div>
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
    <section class="page wide">
      <div class="page-header">
        <div>
          <h1>Suchverläufe</h1>
          <p>Gespeicherte Suchläufe und ihre gerankten Treffer.</p>
        </div>
        <button class="button secondary" type="button" onclick={loadHistory} disabled={historyLoading}>
          {historyLoading ? 'Aktualisiere...' : 'Aktualisieren'}
        </button>
      </div>
      {#if historyHint}
        <p class="notice">{historyHint}</p>
      {/if}
      {#if historyError}
        <p class="error">{historyError}</p>
      {/if}
      <div class="history-workspace">
        <section class="history-sidebar" aria-label="Gespeicherte Suchläufe">
          {#if historyJobs.length > 0}
            {#each historyJobs as job}
              <article class="history-entry">
                <button
                  class="history-row"
                  class:selected={selectedHistoryJob?.id === job.id}
                  type="button"
                  onclick={() => openHistoryJob(job)}
                >
                  <span class="history-title">{job.title}</span>
                  <span>{job.status} · {job.result_count} Treffer</span>
                  <span>{new Date(job.created_at).toLocaleString('de-DE')}</span>
                </button>
                <button
                  class="danger-button"
                  type="button"
                  disabled={deletingJobId === job.id}
                  onclick={() => removeHistoryJob(job)}
                >
                  {deletingJobId === job.id ? 'Lösche...' : 'Suchlauf löschen'}
                </button>
              </article>
            {/each}
          {:else if historyLoading}
            <p class="muted">Lade Suchverläufe...</p>
          {:else}
            <div class="empty-state compact-empty">
              <h2>Noch keine Suchläufe</h2>
              <p>Neue Suchjobs werden lokal in SQLite gespeichert und erscheinen danach hier.</p>
            </div>
          {/if}
        </section>

        <section class="history-results" aria-label="Treffer des Suchlaufs">
          {#if selectedHistoryJob}
            <div class="section-heading">
              <span class="eyebrow">Trefferliste</span>
              <h2>{selectedHistoryJob.title}</h2>
            </div>
            {#if historyResultsLoading}
              <p class="muted">Lade Treffer...</p>
            {:else if selectedHistoryResults.length > 0}
              <div class="result-card-list">
                {#each selectedHistoryResults as result}
                  <article class="result-card" aria-label={`Treffer ${result.name}`}>
                    <div class="result-card-header">
                      <div>
                        <div class="match-topline">
                          <span class={`source-badge ${sourceBadgeClass(result.dataSource)}`}>{result.dataSource}</span>
                          <span class="score-pill">{scoreLabel(result.matchScore)}</span>
                        </div>
                        <h3>{result.name}</h3>
                        <p>{result.category} · Trefferwahrscheinlichkeit {scoreLabel(result.matchScore)} · {result.naid}</p>
                      </div>
                      <button class="button secondary" type="button" onclick={() => openResultDetail(result, 'history')}>
                        Vollansicht öffnen
                      </button>
                    </div>

                    <div class="detail-shell inline-detail-shell">
                      <section class="original-pane" aria-label={`Originalseite ${result.name}`}>
                        <div class="section-heading">
                          <span class="eyebrow">Originalseite</span>
                          <h2>{result.sourcePageLabel}</h2>
                        </div>
                        {#if result.sourcePageUrl}
                          <div class="document-stage">
                            <img src={result.sourcePageUrl} alt={result.sourcePageLabel} />
                            {#each result.lines as line}
                              <button
                                class="document-hotspot"
                                class:active={focusedLineId === line.id}
                                style={hotspotStyle(line)}
                                type="button"
                                aria-label={line.label}
                                onmouseenter={() => setHoveredLine(line.id)}
                                onmouseleave={clearHoveredLine}
                                onfocus={() => setHoveredLine(line.id)}
                                onblur={clearHoveredLine}
                                onclick={() => togglePinnedLine(line.id)}
                              >
                                <span>{line.label}</span>
                              </button>
                            {/each}
                          </div>
                        {:else if result.sourceCatalogUrl}
                          <div class="catalog-preview">
                            <iframe title={`NARA Catalog Datensatz ${result.naid}`} src={result.sourceCatalogUrl}></iframe>
                            <div class="catalog-preview-link">
                              <a class="button secondary" href={result.sourceCatalogUrl} target="_blank" rel="noreferrer">
                                NARA-Datensatz öffnen
                              </a>
                            </div>
                          </div>
                        {:else}
                          <div class="empty-state compact-empty">
                            <h2>Kein lokales Originalbild</h2>
                            <p>Für diesen Treffer ist noch keine Bildseite im lokalen Cache vorhanden.</p>
                          </div>
                        {/if}
                      </section>

                      <section class="transcript-pane" aria-label={`Transkript ${result.name}`}>
                        <div class="section-heading">
                          <span class="eyebrow">Transkript</span>
                          <h2>Personendaten</h2>
                        </div>
                        <div class="identity-grid">
                          <span>
                            <strong>Name</strong>
                            {result.name}
                          </span>
                          <span>
                            <strong>Geburtsdatum</strong>
                            {result.birthDate}
                          </span>
                          <span>
                            <strong>Geburtsort</strong>
                            {result.birthPlace}
                          </span>
                          <span>
                            <strong>Wohnort</strong>
                            {result.residencePlace}
                          </span>
                        </div>
                        <div class="transcript-lines">
                          {#each transcriptRowsFor(result) as line}
                            <button
                              class="transcript-line"
                              class:active={focusedLineId === line.id}
                              type="button"
                              onmouseenter={() => setHoveredLine(line.id)}
                              onmouseleave={clearHoveredLine}
                              onfocus={() => setHoveredLine(line.id)}
                              onblur={clearHoveredLine}
                              onclick={() => togglePinnedLine(line.id)}
                            >
                              <span>{line.label}</span>
                              <strong>{line.value}</strong>
                              <small>{line.note}</small>
                            </button>
                          {/each}
                        </div>
                        <div class="transcript-editor-panel">
                          <div class="transcript-meta">
                            <span>{result.transcriptSource}</span>
                            {#if result.transcriptEdited}
                              <span>manuell korrigiert</span>
                            {/if}
                          </div>
                          <label>
                            Transkription
                            <textarea
                              class="transcript-editor"
                              value={transcriptDraftFor(result)}
                              rows="16"
                              oninput={(event) => updateTranscriptDraft(result, event)}
                            ></textarea>
                          </label>
                          <div class="actions">
                            <button
                              class="button"
                              type="button"
                              onclick={() => saveResultTranscript(result)}
                              disabled={isTranscriptSaving(result) || result.resultId === null}
                            >
                              {isTranscriptSaving(result) ? 'Speichere...' : 'Transkription speichern'}
                            </button>
                          </div>
                          {#if transcriptNoticeFor(result)}
                            <p class="notice compact-message">{transcriptNoticeFor(result)}</p>
                          {/if}
                          {#if transcriptErrorFor(result)}
                            <p class="error compact-message">{transcriptErrorFor(result)}</p>
                          {/if}
                        </div>
                        {#if result.evidence.length > 0}
                          <div class="evidence-list">
                            {#each result.evidence as evidence}
                              <p>{evidence}</p>
                            {/each}
                          </div>
                        {/if}
                      </section>
                    </div>
                    <button
                      class="match-row"
                      type="button"
                      onclick={() => openResultDetail(result, 'history')}
                      onkeydown={(event) => openResultDetailWithKeyboard(event, result, 'history')}
                    >
                      <span class="portrait-frame">
                        {#if result.portraitUrl}
                          <img src={result.portraitUrl} alt={`Aktenfoto ${result.name}`} />
                        {:else}
                          <span class="portrait-placeholder">{initials(result.name)}</span>
                        {/if}
                      </span>
                      <span class="match-summary">
                        <span class="match-topline">
                          <span class={`source-badge ${sourceBadgeClass(result.dataSource)}`}>{result.dataSource}</span>
                          <span class="score-pill">{scoreLabel(result.matchScore)}</span>
                        </span>
                        <span class="match-name">{result.name}</span>
                        <span class="match-record">{result.naid}</span>
                        <span class="match-title">{result.title}</span>
                        <span class="match-facts">
                          <span>Geburtsdatum: {result.birthDate}</span>
                          <span>Wohnort: {result.residencePlace}</span>
                        </span>
                      </span>
                    </button>
                    <button
                      class="danger-button result-delete"
                      type="button"
                      disabled={deletingResultId === result.resultId}
                      onclick={() => removeHistoryResult(result)}
                    >
                      {deletingResultId === result.resultId ? 'Lösche...' : 'Treffer löschen'}
                    </button>
                  </article>
                {/each}
              </div>
            {:else}
              <div class="empty-state compact-empty">
                <h2>Keine Treffer gespeichert</h2>
                <p>Dieser Suchlauf enthält keine Trefferliste.</p>
              </div>
            {/if}
          {:else}
            <div class="empty-state compact-empty">
              <h2>Kein Suchlauf ausgewählt</h2>
              <p>Wähle links einen Suchlauf aus.</p>
            </div>
          {/if}
        </section>
      </div>
    </section>
  {:else if activeRoute === 'result-detail' && detailResult}
    <section class="detail-page">
      <div class="detail-header">
        <button class="button secondary" type="button" onclick={backFromDetail}>Zurück</button>
        <div>
          <span class={`source-badge ${sourceBadgeClass(detailResult.dataSource)}`}>{detailResult.dataSource}</span>
          <h1>{detailResult.name}</h1>
          <p>{detailResult.category} · Trefferwahrscheinlichkeit {scoreLabel(detailResult.matchScore)} · {detailResult.naid}</p>
        </div>
      </div>

      <div class="detail-shell">
        <section class="original-pane" aria-label="Originalseite">
          <div class="section-heading">
            <span class="eyebrow">Originalseite</span>
            <h2>{detailResult.sourcePageLabel}</h2>
          </div>
          {#if detailResult.sourcePageUrl}
            <div class="document-stage">
              <img src={detailResult.sourcePageUrl} alt={detailResult.sourcePageLabel} />
              {#each detailResult.lines as line}
                <button
                  class="document-hotspot"
                  class:active={focusedLineId === line.id}
                  style={hotspotStyle(line)}
                  type="button"
                  aria-label={line.label}
                  onmouseenter={() => setHoveredLine(line.id)}
                  onmouseleave={clearHoveredLine}
                  onfocus={() => setHoveredLine(line.id)}
                  onblur={clearHoveredLine}
                  onclick={() => togglePinnedLine(line.id)}
                >
                  <span>{line.label}</span>
                </button>
              {/each}
            </div>
          {:else if detailResult.sourceCatalogUrl}
            <div class="catalog-preview">
              <iframe title={`NARA Catalog Datensatz ${detailResult.naid}`} src={detailResult.sourceCatalogUrl}></iframe>
              <div class="catalog-preview-link">
                <a class="button secondary" href={detailResult.sourceCatalogUrl} target="_blank" rel="noreferrer">
                  NARA-Datensatz öffnen
                </a>
              </div>
            </div>
          {:else}
            <div class="empty-state compact-empty">
              <h2>Kein lokales Originalbild</h2>
              <p>Für diesen Treffer ist noch keine Bildseite im lokalen Cache vorhanden.</p>
            </div>
          {/if}
        </section>

        <section class="transcript-pane" aria-label="Transkript">
          <div class="section-heading">
            <span class="eyebrow">Transkript</span>
            <h2>Personendaten</h2>
          </div>
          <div class="identity-grid">
            <span>
              <strong>Name</strong>
              {detailResult.name}
            </span>
            <span>
              <strong>Geburtsdatum</strong>
              {detailResult.birthDate}
            </span>
            <span>
              <strong>Geburtsort</strong>
              {detailResult.birthPlace}
            </span>
            <span>
              <strong>Wohnort</strong>
              {detailResult.residencePlace}
            </span>
          </div>

          {#if detailResult.lines.length > 0}
            <div class="transcript-lines">
              {#each detailResult.lines as line}
                <button
                  class="transcript-line"
                  class:active={focusedLineId === line.id}
                  type="button"
                  onmouseenter={() => setHoveredLine(line.id)}
                  onmouseleave={clearHoveredLine}
                  onfocus={() => setHoveredLine(line.id)}
                  onblur={clearHoveredLine}
                  onclick={() => togglePinnedLine(line.id)}
                >
                  <span>{line.label}</span>
                  <strong>{line.value}</strong>
                  <small>{line.note}</small>
                </button>
              {/each}
            </div>
          {/if}

          <div class="transcript-editor-panel">
            <div class="transcript-meta">
              <span>{detailResult.transcriptSource}</span>
              {#if detailResult.transcriptEdited}
                <span>manuell korrigiert</span>
              {/if}
            </div>
            <label>
              Transkription
              <textarea class="transcript-editor" bind:value={transcriptDraft} rows="16"></textarea>
            </label>
            <div class="actions">
              <button
                class="button"
                type="button"
                onclick={saveTranscript}
                disabled={transcriptSaving || detailResult.resultId === null}
              >
                {transcriptSaving ? 'Speichere...' : 'Transkription speichern'}
              </button>
            </div>
            {#if transcriptNotice}
              <p class="notice compact-message">{transcriptNotice}</p>
            {/if}
            {#if transcriptError}
              <p class="error compact-message">{transcriptError}</p>
            {/if}
          </div>

          {#if detailResult.lines.length === 0 && detailResult.evidence.length > 0}
            <div class="evidence-list">
              {#each detailResult.evidence as evidence}
                <p>{evidence}</p>
              {/each}
            </div>
          {/if}
        </section>
      </div>
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
