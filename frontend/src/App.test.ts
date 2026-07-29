import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { afterEach, describe, expect, it, vi } from 'vitest';

import App from './App.svelte';

function searchJob(overrides = {}) {
  return {
    id: 'job-1',
    status: 'complete',
    mode: 'quick',
    title: 'Paul Schultze-Naumburg',
    progress_current: 6,
    progress_total: 6,
    warnings: [],
    error_message: null,
    created_at: new Date().toISOString(),
    completed_at: new Date().toISOString(),
    result_count: 2,
    mock_mode: false,
    ...overrides
  };
}

function localResult(overrides = {}) {
  return {
    id: 1,
    job_id: 'job-1',
    match_score: 96,
    category: 'sehr wahrscheinlich',
    suspected_person_name: 'Paul Schultze-Naumburg',
    birth_date: null,
    birth_place: null,
    relevant_pages_count: 4,
    naid: 'LOCAL-PDF-SCHULTZE-NAUMBURG-1931',
    title: 'Lokale Demo-Datei: Paul Schultze-Naumburg, NSDAP-Kartei 1931',
    record_group: 'Lokale Demo-Datei',
    series: 'A3340-MFKL-R0013.pdf',
    original_url: null,
    text_origin: 'lokale PDF ohne extrahierbare Textschicht',
    data_source: 'LOCAL',
    retrieved_at: new Date().toISOString(),
    source_page_id: null,
    source_page_url: null,
    source_page_label: null,
    transcript_text: null,
    transcript_source: null,
    transcript_edited: false,
    evidences: [
      {
        kind: 'positive',
        label: 'Lokale PDF zu Paul Schultze-Naumburg eingebunden',
        detail: null,
        score_delta: 28,
        source_type: 'lokale PDF ohne extrahierbare Textschicht'
      }
    ],
    ...overrides
  };
}

function settingsResponse(overrides = {}) {
  return {
    mock_mode: false,
    data_dir: 'C:\\Temp\\NARATrace',
    cache_dir: 'C:\\Temp\\NARATrace\\cache',
    database_path: 'C:\\Temp\\NARATrace\\database\\naratrace.sqlite3',
    nara_api_key_configured: true,
    nara_api_key_source: 'keyring',
    nara_api_usage: {
      request_count: 123,
      request_limit: 10000,
      percent_used: 1.23,
      period: '2026-07',
      reset_at: '2026-08-01T00:00:00Z',
      counted_locally: true
    },
    ...overrides
  };
}

function progressStatValue(label: string) {
  return screen.getByText(label).parentElement?.querySelector('strong')?.textContent ?? '';
}

describe('App', () => {
  afterEach(() => {
    window.location.hash = '';
    vi.restoreAllMocks();
    cleanup();
  });

  it('zeigt Projekttitel, Quellenkennzeichnung und das Anzeige-Beispiel', () => {
    render(App);

    expect(screen.getByRole('heading', { name: 'NARATrace' })).toBeTruthy();
    expect(screen.getByText('NARA Catalog')).toBeTruthy();
    expect(screen.getByText('Anzeige-Beispiel')).toBeTruthy();
    expect(screen.getByText('Recherche-Workflow')).toBeTruthy();
    expect(screen.getByText('Bericht exportieren')).toBeTruthy();
    expect(screen.getByText('LOCAL-PDF-SCHULTZE-NAUMBURG-1931')).toBeTruthy();
    expect(screen.getByText('Wohnort: Naumburg; später Weimar')).toBeTruthy();
    expect(screen.getByAltText('Aktenfoto Paul Schultze-Naumburg').getAttribute('src')).toBe(
      '/demo/schultze-naumburg.png'
    );
    expect(screen.queryByText(/Ulm|Münsterplatz/)).toBeNull();
    expect(
      screen.getByText(/U.S. National Archives and Records Administration - National Archives Catalog/)
    ).toBeTruthy();
  });

  it('zeigt die NARA-API-Nutzung prozentual und numerisch im Header', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      if (String(input) === '/api/settings') {
        return new Response(JSON.stringify(settingsResponse()), {
          status: 200,
          headers: { 'Content-Type': 'application/json' }
        });
      }
      return new Response('{}', { status: 404 });
    });

    render(App);

    await waitFor(() => {
      expect(screen.getByText('NARA API: 1,2 % (123/10000)')).toBeTruthy();
    });
  });

  it('öffnet vom Startseiten-Beispiel die Detailansicht mit synchroner Markierung', async () => {
    render(App);

    await fireEvent.click(screen.getAllByRole('button', { name: /Paul Schultze-Naumburg/ })[0]);

    expect(screen.getByRole('heading', { name: 'Paul Schultze-Naumburg' })).toBeTruthy();
    expect(screen.getByText('Originalseite')).toBeTruthy();
    expect(screen.getByText('Transkript')).toBeTruthy();
    expect(screen.getAllByText('Almrich').length).toBeGreaterThan(0);
    expect(screen.getByText('Naumburg; später Weimar')).toBeTruthy();
    expect(screen.getByRole('button', { name: /Späterer Wohnort Weimar/ })).toBeTruthy();

    const transcriptNameLine = screen.getByRole('button', { name: /Name Schultze-Naumburg, Paul/ });
    const originalNameHotspot = screen.getByRole('button', { name: 'Name' });
    await fireEvent.mouseEnter(transcriptNameLine);

    expect(originalNameHotspot.classList.contains('active')).toBe(true);
  });

  it('wechselt per Hauptnavigation zur neuen Suche ohne Demo-Schaltfläche', async () => {
    render(App);

    await fireEvent.click(screen.getByRole('link', { name: 'Neue Suche' }));

    expect(screen.getByRole('heading', { name: 'Neue Suche' })).toBeTruthy();
    expect(screen.getByLabelText('Nachname')).toBeTruthy();
    expect(screen.getByLabelText('Geburtsdatum')).toBeTruthy();
    expect(screen.getByLabelText('Wohnorte')).toBeTruthy();
    expect(screen.getByLabelText('Mitgliedsnummer')).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Demo-Treffer anzeigen' })).toBeNull();
  });

  it('wechselt per Hauptnavigation zu den Einstellungen', async () => {
    render(App);

    await fireEvent.click(screen.getByRole('link', { name: 'Einstellungen' }));

    expect(screen.getByRole('heading', { name: 'Einstellungen' })).toBeTruthy();
    expect(screen.getByText('NARA API-Schlüssel')).toBeTruthy();
    expect(screen.getByText(/Jeder Nutzer verwendet seinen eigenen NARA API-Schlüssel/)).toBeTruthy();
    expect(screen.getByText(/Catalog_API@nara.gov/)).toBeTruthy();
  });

  it('zeigt im Methodik-Reiter Erklärung und Workflow-Schema', async () => {
    render(App);

    await fireEvent.click(screen.getByRole('link', { name: 'Methodik' }));

    expect(screen.getByRole('heading', { name: 'Methodik' })).toBeTruthy();
    expect(screen.getByText('Ähnlichkeit ist kein Identitätsnachweis')).toBeTruthy();
    expect(screen.getByText('Von der Suchangabe zum prüfbaren Treffer')).toBeTruthy();
    expect(screen.getByText('Suchprofil erfassen')).toBeTruthy();
    expect(screen.getByText('Quellenprüfung')).toBeTruthy();
    expect(screen.getByText('Was NARATrace nicht entscheidet')).toBeTruthy();
  });

  it('analysiert lokale Dokumente mit Vorschau, OCR und Prüfbegriffen', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = String(input);
      if (url === '/api/settings') {
        return new Response(JSON.stringify(settingsResponse()), {
          status: 200,
          headers: { 'Content-Type': 'application/json' }
        });
      }
      if (url === '/api/local-documents' && init?.method === 'POST') {
        return new Response(
          JSON.stringify({
            id: 'local-1',
            file_name: 'karte.png',
            content_type: 'image/png',
            size_bytes: 2048,
            display_image_url: '/api/local-documents/local-1/image',
            ocr_text: 'Paul Schultze-Naumburg\nMitgliedsnummer 347541\nWohnort Naumburg',
            ocr_engine: 'Tesseract',
            warnings: [],
            stored_at: new Date().toISOString()
          }),
          { status: 201, headers: { 'Content-Type': 'application/json' } }
        );
      }
      return new Response('{}', { status: 404 });
    });

    render(App);

    await fireEvent.click(screen.getByRole('link', { name: 'Lokale Dokumente' }));
    await fireEvent.input(screen.getByLabelText('Prüfbegriffe'), { target: { value: 'Paul\n347541\nWeimar' } });
    await fireEvent.change(screen.getByLabelText('Datei auswählen'), {
      target: { files: [new File(['fake'], 'karte.png', { type: 'image/png' })] }
    });
    await fireEvent.click(screen.getByRole('button', { name: 'Dokument analysieren' }));

    await waitFor(() => {
      expect(screen.getByText('Lokales Dokument wurde analysiert.')).toBeTruthy();
    });
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/local-documents',
      expect.objectContaining({ method: 'POST', body: expect.any(FormData) })
    );
    expect(screen.getByAltText('Vorschau karte.png').getAttribute('src')).toBe('/api/local-documents/local-1/image');
    expect(screen.getByDisplayValue(/Paul Schultze-Naumburg/)).toBeTruthy();
    expect(screen.getAllByText('1 Fundstelle').length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText('Im OCR-Text nicht gefunden.')).toBeTruthy();
  });

  it('legt aus dem Suchformular einen Backend-Suchjob ohne Demo-Flag an', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = String(input);
      if (url === '/api/search' && init?.method === 'POST') {
        return new Response(JSON.stringify(searchJob({ id: 'job-new', result_count: 0 })), {
          status: 201,
          headers: { 'Content-Type': 'application/json' }
        });
      }
      if (url === '/api/search/job-new/results') {
        return new Response(JSON.stringify([]), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      if (url === '/api/search') {
        return new Response(JSON.stringify([]), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      return new Response('{}', { status: 404 });
    });

    render(App);

    await fireEvent.click(screen.getByRole('link', { name: 'Neue Suche' }));
    await fireEvent.input(screen.getByLabelText('Vorname'), { target: { value: 'Paul' } });
    await fireEvent.input(screen.getByLabelText('Nachname'), { target: { value: 'Schultze-Naumburg' } });
    await fireEvent.input(screen.getByLabelText('Geburtsdatum'), { target: { value: '1869-06-10' } });
    await fireEvent.input(screen.getByLabelText('Geburtsjahr oder bekanntes Jahr'), { target: { value: '1869' } });
    await fireEvent.input(screen.getByLabelText('Wohnorte'), { target: { value: 'Naumburg\nSaaleck' } });
    await fireEvent.input(screen.getByLabelText('Mitgliedsnummer'), { target: { value: '347.541' } });
    await fireEvent.click(screen.getByRole('button', { name: 'Suchjob anlegen' }));

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Suchjob gespeichert' })).toBeTruthy();
    });

    const searchCall = fetchMock.mock.calls.find(([url, init]) => String(url) === '/api/search' && init?.method === 'POST');
    expect(searchCall?.[1]?.body).toEqual(expect.stringContaining('membership_number'));
    expect(searchCall?.[1]?.body).not.toEqual(expect.stringContaining('demo_mode'));
  });

  it('zeigt bei laufendem Suchjob Fortschritt, Restzeit und aktuellen Schritt', async () => {
    let progressStatusCalls = 0;
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = String(input);
      if (url === '/api/settings') {
        return new Response(JSON.stringify(settingsResponse()), {
          status: 200,
          headers: { 'Content-Type': 'application/json' }
        });
      }
      if (url === '/api/search' && init?.method === 'POST') {
        return new Response(
          JSON.stringify(
            searchJob({
              id: 'job-progress',
              status: 'searching_catalog',
              progress_current: 2,
              progress_total: 6,
              result_count: 0,
              completed_at: null
            })
          ),
          { status: 201, headers: { 'Content-Type': 'application/json' } }
        );
      }
      if (url === '/api/search/job-progress') {
        progressStatusCalls += 1;
        if (progressStatusCalls === 1) {
          return new Response(JSON.stringify({ detail: 'kurz nicht erreichbar' }), {
            status: 503,
            headers: { 'Content-Type': 'application/json' }
          });
        }
        if (progressStatusCalls === 2) {
          return new Response(
            JSON.stringify(
              searchJob({
                id: 'job-progress',
                status: 'downloading_pages_ocr',
                progress_current: 4,
                progress_total: 6,
                result_count: 0,
                completed_at: null
              })
            ),
            { status: 200, headers: { 'Content-Type': 'application/json' } }
          );
        }
        return new Response(JSON.stringify(searchJob({ id: 'job-progress', result_count: 0 })), {
          status: 200,
          headers: { 'Content-Type': 'application/json' }
        });
      }
      if (url === '/api/search/job-progress/results') {
        return new Response(JSON.stringify([]), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      if (url === '/api/search') {
        return new Response(JSON.stringify([]), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      return new Response('{}', { status: 404 });
    });

    render(App);

    await fireEvent.click(screen.getByRole('link', { name: 'Neue Suche' }));
    await fireEvent.input(screen.getByLabelText('Nachname'), { target: { value: 'Schultze-Naumburg' } });
    await fireEvent.click(screen.getByRole('button', { name: 'Suchjob anlegen' }));

    await waitFor(() => {
      expect(screen.getByText('NARA Catalog wird abgefragt')).toBeTruthy();
    });
    expect(screen.getByRole('progressbar', { name: 'Fortschritt des Suchjobs' }).getAttribute('aria-valuenow')).toBe(
      '33'
    );
    expect(screen.getByText('2 von 6 Schritten (33 %)')).toBeTruthy();
    expect(screen.getByText('Restzeit')).toBeTruthy();
    expect(screen.getByText('Voraussichtliche Laufzeit')).toBeTruthy();
    expect(progressStatValue('Voraussichtliche Laufzeit')).toBe('ca. 55 s');
    expect(progressStatValue('Suchlaufzeit')).toBe('0 s');

    await waitFor(
      () => {
        expect(progressStatValue('Suchlaufzeit')).toBe('1 s');
      },
      { timeout: 1800 }
    );
    expect(progressStatValue('Voraussichtliche Laufzeit')).toBe('ca. 55 s');

    await waitFor(
      () => {
        expect(screen.getByText('Statusantwort kurz unterbrochen. Der Suchjob läuft weiter.')).toBeTruthy();
      },
      { timeout: 2500 }
    );

    await waitFor(
      () => {
        expect(screen.getByText('Originalseiten werden geladen und OCR wird vorbereitet')).toBeTruthy();
      },
      { timeout: 2500 }
    );
    expect(screen.getByText('4 von 6 Schritten (67 %)')).toBeTruthy();
    expect(progressStatValue('Voraussichtliche Laufzeit')).toBe('ca. 55 s');

    await waitFor(
      () => {
        expect(screen.getByText('Suche abgeschlossen')).toBeTruthy();
        expect(screen.getByText('6 von 6 Schritten (100 %)')).toBeTruthy();
      },
      { timeout: 4000 }
    );
  });

  it('bricht einen laufenden Suchjob aus dem Ladepanel ab', async () => {
    let cancelled = false;
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = String(input);
      if (url === '/api/settings') {
        return new Response(JSON.stringify(settingsResponse()), {
          status: 200,
          headers: { 'Content-Type': 'application/json' }
        });
      }
      if (url === '/api/search' && init?.method === 'POST') {
        return new Response(
          JSON.stringify(
            searchJob({
              id: 'job-cancel',
              status: 'searching_catalog',
              progress_current: 2,
              progress_total: 6,
              result_count: 0,
              completed_at: null
            })
          ),
          { status: 201, headers: { 'Content-Type': 'application/json' } }
        );
      }
      if (url === '/api/search/job-cancel/cancel' && init?.method === 'POST') {
        cancelled = true;
        return new Response(
          JSON.stringify(
            searchJob({
              id: 'job-cancel',
              status: 'cancelled',
              progress_current: 2,
              progress_total: 6,
              result_count: 0,
              completed_at: new Date().toISOString()
            })
          ),
          { status: 200, headers: { 'Content-Type': 'application/json' } }
        );
      }
      if (url === '/api/search/job-cancel') {
        return new Response(
          JSON.stringify(
            searchJob({
              id: 'job-cancel',
              status: cancelled ? 'cancelled' : 'searching_catalog',
              progress_current: 2,
              progress_total: 6,
              result_count: 0,
              completed_at: cancelled ? new Date().toISOString() : null
            })
          ),
          { status: 200, headers: { 'Content-Type': 'application/json' } }
        );
      }
      if (url === '/api/search') {
        return new Response(JSON.stringify([]), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      return new Response('{}', { status: 404 });
    });

    render(App);

    await fireEvent.click(screen.getByRole('link', { name: 'Neue Suche' }));
    await fireEvent.input(screen.getByLabelText('Nachname'), { target: { value: 'Schultze-Naumburg' } });
    await fireEvent.click(screen.getByRole('button', { name: 'Suchjob anlegen' }));

    await screen.findByRole('button', { name: 'Suchjob abbrechen' });
    await waitFor(() => {
      expect((screen.getByRole('button', { name: 'Suchjob abbrechen' }) as HTMLButtonElement).disabled).toBe(false);
    });
    await fireEvent.click(screen.getByRole('button', { name: 'Suchjob abbrechen' }));

    await waitFor(() => {
      expect(
        fetchMock.mock.calls.some(([url, init]) => String(url) === '/api/search/job-cancel/cancel' && init?.method === 'POST')
      ).toBe(true);
    });
    await waitFor(
      () => {
        expect(screen.getByText('Suchjob für "Schultze-Naumburg" wurde abgebrochen.')).toBeTruthy();
      },
      { timeout: 3000 }
    );
  });

  it('wartet bei laenger unterbrochenem Status weiter und zeigt danach Treffer', async () => {
    let stalledStatusCalls = 0;
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = String(input);
      if (url === '/api/settings') {
        return new Response(JSON.stringify(settingsResponse()), {
          status: 200,
          headers: { 'Content-Type': 'application/json' }
        });
      }
      if (url === '/api/search' && init?.method === 'POST') {
        return new Response(
          JSON.stringify(
            searchJob({
              id: 'job-stalled',
              status: 'downloading_pages_ocr',
              progress_current: 4,
              progress_total: 6,
              result_count: 0,
              completed_at: null
            })
          ),
          { status: 201, headers: { 'Content-Type': 'application/json' } }
        );
      }
      if (url === '/api/search/job-stalled') {
        stalledStatusCalls += 1;
        if (stalledStatusCalls <= 6) {
          return new Response(JSON.stringify({ detail: 'Status nicht erreichbar' }), {
            status: 503,
            headers: { 'Content-Type': 'application/json' }
          });
        }
        return new Response(
          JSON.stringify(searchJob({ id: 'job-stalled', progress_current: 6, progress_total: 6, result_count: 1 })),
          { status: 200, headers: { 'Content-Type': 'application/json' } }
        );
      }
      if (url === '/api/search/job-stalled/results') {
        return new Response(
          JSON.stringify([
            localResult({
              id: 12,
              job_id: 'job-stalled',
              naid: '123456',
              title: 'NARA-Ergebnis nach Statusunterbrechung',
              data_source: 'NARA',
              source_page_url: '/api/pages/12/image',
              source_page_label: 'NARA-Ergebnis nach Statusunterbrechung, Objekt/Seite 1',
              transcript_text: 'OCR Volltext nach Unterbrechung',
              transcript_source: 'NARA Extracted Text'
            })
          ]),
          { status: 200, headers: { 'Content-Type': 'application/json' } }
        );
      }
      return new Response('{}', { status: 404 });
    });

    render(App);

    await fireEvent.click(screen.getByRole('link', { name: 'Neue Suche' }));
    await fireEvent.input(screen.getByLabelText('Nachname'), { target: { value: 'Schultze-Naumburg' } });
    await fireEvent.click(screen.getByRole('button', { name: 'Suchjob anlegen' }));

    await waitFor(
      () => {
        expect(
          screen.getByText('Statusantwort seit 5 Versuchen unterbrochen. NARATrace wartet weiter auf den laufenden Suchjob.')
        ).toBeTruthy();
      },
      { timeout: 7000 }
    );
    expect(screen.queryByText(/Der Suchjob-Status konnte nach mehreren Versuchen/)).toBeNull();

    await waitFor(
      () => {
        expect(screen.getByRole('heading', { name: 'NARA-Ergebnis nach Statusunterbrechung, Objekt/Seite 1' })).toBeTruthy();
      },
      { timeout: 4000 }
    );
    expect(screen.getByText('Suche abgeschlossen')).toBeTruthy();
  }, 11000);

  it('zeigt Treffer einer neuen Suche direkt als Original-und-Transkript-Karte', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = String(input);
      if (url === '/api/settings') {
        return new Response(JSON.stringify(settingsResponse()), {
          status: 200,
          headers: { 'Content-Type': 'application/json' }
        });
      }
      if (url === '/api/search' && init?.method === 'POST') {
        return new Response(JSON.stringify(searchJob({ id: 'job-new', result_count: 1 })), {
          status: 201,
          headers: { 'Content-Type': 'application/json' }
        });
      }
      if (url === '/api/search/job-new/results') {
        return new Response(
          JSON.stringify([
            localResult({
              id: 9,
              job_id: 'job-new',
              naid: '123456',
              title: 'NARA-Testkarte',
              data_source: 'NARA',
              source_page_url: '/api/pages/9/image',
              source_page_label: 'NARA-Testkarte, Objekt/Seite 1',
              transcript_text: 'OCR Volltext der Karte',
              transcript_source: 'NARA Extracted Text'
            })
          ]),
          { status: 200, headers: { 'Content-Type': 'application/json' } }
        );
      }
      if (url === '/api/search') {
        return new Response(JSON.stringify([]), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      return new Response('{}', { status: 404 });
    });

    render(App);

    await fireEvent.click(screen.getByRole('link', { name: 'Neue Suche' }));
    await fireEvent.input(screen.getByLabelText('Nachname'), { target: { value: 'Schultze-Naumburg' } });
    await fireEvent.click(screen.getByRole('button', { name: 'Suchjob anlegen' }));

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'NARA-Testkarte, Objekt/Seite 1' })).toBeTruthy();
    });
    expect(screen.getByText('Originalseite')).toBeTruthy();
    expect(screen.getByText('Transkript')).toBeTruthy();
    expect((screen.getByLabelText('Transkription') as HTMLTextAreaElement).value).toBe('OCR Volltext der Karte');
  });

  it('zeigt fuer Metadaten-Treffer ohne Bildcache eine NARA-Catalog-Vorschau', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = String(input);
      if (url === '/api/settings') {
        return new Response(JSON.stringify(settingsResponse()), {
          status: 200,
          headers: { 'Content-Type': 'application/json' }
        });
      }
      if (url === '/api/search' && init?.method === 'POST') {
        return new Response(JSON.stringify(searchJob({ id: 'job-catalog', result_count: 1 })), {
          status: 201,
          headers: { 'Content-Type': 'application/json' }
        });
      }
      if (url === '/api/search/job-catalog/results') {
        return new Response(
          JSON.stringify([
            localResult({
              id: 11,
              job_id: 'job-catalog',
              naid: '270851699',
              title: 'Number 944 (Serial 944) (1 of 2)',
              data_source: 'NARA',
              match_score: 10,
              category: 'ausgeschlossen',
              original_url: 'https://catalog.archives.gov/id/270851699',
              source_page_id: null,
              source_page_url: null,
              source_page_label: null,
              transcript_text: null,
              transcript_source: null,
              text_origin: 'kein Text verfuegbar'
            })
          ]),
          { status: 200, headers: { 'Content-Type': 'application/json' } }
        );
      }
      if (url === '/api/search') {
        return new Response(JSON.stringify([]), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      return new Response('{}', { status: 404 });
    });

    render(App);

    await fireEvent.click(screen.getByRole('link', { name: 'Neue Suche' }));
    await fireEvent.input(screen.getByLabelText('Nachname'), { target: { value: 'Schultze-Naumburg' } });
    await fireEvent.click(screen.getByRole('button', { name: 'Suchjob anlegen' }));

    await waitFor(() => {
      expect(screen.getByTitle('NARA Catalog Datensatz 270851699')).toBeTruthy();
    });
    expect(screen.getByRole('link', { name: 'NARA-Datensatz öffnen' }).getAttribute('href')).toBe(
      'https://catalog.archives.gov/id/270851699'
    );
    expect(screen.queryByText('Kein lokales Originalbild')).toBeNull();
  });

  it('öffnet im Suchverlauf einen Job nach kurzem Ladefehler und sortiert Treffer nach Wahrscheinlichkeit', async () => {
    let historyCalls = 0;
    let historyResultCalls = 0;
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = String(input);
      if (url === '/api/search') {
        historyCalls += 1;
        if (historyCalls === 1) {
          return new Response(JSON.stringify({ detail: 'kurz nicht erreichbar' }), {
            status: 503,
            headers: { 'Content-Type': 'application/json' }
          });
        }
        return new Response(JSON.stringify([searchJob()]), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      if (url === '/api/search/job-1/results') {
        historyResultCalls += 1;
        if (historyResultCalls === 1) {
          return new Response(JSON.stringify({ detail: 'kurz nicht erreichbar' }), {
            status: 503,
            headers: { 'Content-Type': 'application/json' }
          });
        }
        return new Response(
          JSON.stringify([
            localResult({ id: 2, match_score: 34, suspected_person_name: 'Niedriger Treffer', title: 'Niedriger Treffer' }),
            localResult({ id: 1, match_score: 96, suspected_person_name: 'Hoher Treffer', title: 'Hoher Treffer' })
          ]),
          { status: 200, headers: { 'Content-Type': 'application/json' } }
        );
      }
      return new Response('{}', { status: 404 });
    });

    render(App);

    await fireEvent.click(screen.getByRole('link', { name: 'Suchverläufe' }));
    await waitFor(() => {
      expect(screen.getByText('Suchverläufe konnten kurz nicht geladen werden (2. Versuch).')).toBeTruthy();
    });
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /abgeschlossen · 2 Treffer/ })).toBeTruthy();
    });
    expect(screen.queryByText('Die Suchverläufe konnten nicht geladen werden.')).toBeNull();
    await fireEvent.click(screen.getByRole('button', { name: /abgeschlossen · 2 Treffer/ }));

    await waitFor(() => {
      expect(screen.getByText('Treffer konnten kurz nicht geladen werden (2. Versuch).')).toBeTruthy();
    });
    await waitFor(() => {
      expect(screen.getAllByText('Hoher Treffer').length).toBeGreaterThan(0);
    });
    expect(screen.getByText('Ausgewählter Suchlauf')).toBeTruthy();
    expect(screen.getByText('Nach Trefferwahrscheinlichkeit')).toBeTruthy();
    expect(screen.queryByText('Die Treffer konnten nicht geladen werden.')).toBeNull();

    const high = screen.getAllByText('Hoher Treffer')[0];
    const low = screen.getAllByText('Niedriger Treffer')[0];
    expect(Boolean(high.compareDocumentPosition(low) & Node.DOCUMENT_POSITION_FOLLOWING)).toBe(true);
  });

  it('exportiert einen Suchverlauf als Markdown-Recherchebericht', async () => {
    const createObjectURL = vi.fn(() => 'blob:naratrace-report');
    const revokeObjectURL = vi.fn();
    Object.defineProperty(window.URL, 'createObjectURL', { value: createObjectURL, configurable: true });
    Object.defineProperty(window.URL, 'revokeObjectURL', { value: revokeObjectURL, configurable: true });
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});

    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = String(input);
      if (url === '/api/settings') {
        return new Response(JSON.stringify(settingsResponse()), {
          status: 200,
          headers: { 'Content-Type': 'application/json' }
        });
      }
      if (url === '/api/search') {
        return new Response(JSON.stringify([searchJob({ result_count: 1 })]), {
          status: 200,
          headers: { 'Content-Type': 'application/json' }
        });
      }
      if (url === '/api/search/job-1/results') {
        return new Response(JSON.stringify([localResult({ id: 1, match_score: 96, title: 'Exportierbarer Treffer' })]), {
          status: 200,
          headers: { 'Content-Type': 'application/json' }
        });
      }
      if (url === '/api/search/job-1/export.md') {
        return new Response('# NARATrace Recherchebericht', {
          status: 200,
          headers: {
            'Content-Type': 'text/markdown',
            'Content-Disposition': 'attachment; filename="naratrace-recherchebericht.md"'
          }
        });
      }
      return new Response('{}', { status: 404 });
    });

    render(App);

    await fireEvent.click(screen.getByRole('link', { name: 'Suchverläufe' }));
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /abgeschlossen · 1 Treffer/ })).toBeTruthy();
    });
    await fireEvent.click(screen.getByRole('button', { name: /abgeschlossen · 1 Treffer/ }));
    await waitFor(() => {
      expect(screen.getByText('Exportierbarer Treffer')).toBeTruthy();
    });
    await fireEvent.click(screen.getByRole('button', { name: 'Recherchebericht exportieren' }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith('/api/search/job-1/export.md');
    });
    await waitFor(() => {
      expect(createObjectURL).toHaveBeenCalled();
    });
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:naratrace-report');
    expect(screen.getByText('Recherchebericht wurde erzeugt.')).toBeTruthy();
  });

  it('löscht im Suchverlauf einzelne Treffer und komplette Suchläufe', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = String(input);
      if (url === '/api/search' && !init) {
        return new Response(JSON.stringify([searchJob({ result_count: 1 })]), {
          status: 200,
          headers: { 'Content-Type': 'application/json' }
        });
      }
      if (url === '/api/search/job-1/results' && !init) {
        return new Response(JSON.stringify([localResult({ id: 1, match_score: 96, title: 'Löschbarer Treffer' })]), {
          status: 200,
          headers: { 'Content-Type': 'application/json' }
        });
      }
      if (url === '/api/search/job-1/results/1' && init?.method === 'DELETE') {
        return new Response(null, { status: 204 });
      }
      if (url === '/api/search/job-1' && init?.method === 'DELETE') {
        return new Response(null, { status: 204 });
      }
      return new Response('{}', { status: 404 });
    });
    vi.spyOn(window, 'confirm').mockReturnValue(true);

    render(App);

    await fireEvent.click(screen.getByRole('link', { name: 'Suchverläufe' }));
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /abgeschlossen · 1 Treffer/ })).toBeTruthy();
    });
    await fireEvent.click(screen.getByRole('button', { name: /abgeschlossen · 1 Treffer/ }));
    await waitFor(() => {
      expect(screen.getByText('Löschbarer Treffer')).toBeTruthy();
    });

    await fireEvent.click(screen.getByRole('button', { name: 'Treffer löschen' }));
    await waitFor(() => {
      expect(screen.queryByText('Löschbarer Treffer')).toBeNull();
    });
    await fireEvent.click(screen.getByRole('button', { name: 'Suchlauf löschen' }));

    expect(fetchMock).toHaveBeenCalledWith('/api/search/job-1/results/1', { method: 'DELETE' });
    expect(fetchMock).toHaveBeenCalledWith('/api/search/job-1', { method: 'DELETE' });
  });

  it('speichert bearbeitete Transkriptionen für Suchergebnisse', async () => {
    const result = localResult({
      id: 7,
      job_id: 'job-1',
      naid: '123456',
      title: 'NARA-Testkarte',
      data_source: 'NARA',
      suspected_person_name: 'Paul Schultze-Naumburg',
      source_page_id: 3,
      source_page_url: '/api/pages/3/image',
      source_page_label: 'NARA-Testkarte, Objekt/Seite 1',
      transcript_text: 'Raw OCR Schultze Naumburg',
      transcript_source: 'NARA Extracted Text',
      transcript_edited: false
    });
    const updatedResult = {
      ...result,
      transcript_text: 'Korrigierte Transkription',
      transcript_source: 'manuelle Korrektur',
      transcript_edited: true
    };
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = String(input);
      if (url === '/api/search') {
        return new Response(JSON.stringify([searchJob({ result_count: 1 })]), {
          status: 200,
          headers: { 'Content-Type': 'application/json' }
        });
      }
      if (url === '/api/search/job-1/results' && !init) {
        return new Response(JSON.stringify([result]), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      if (url === '/api/search/job-1/results/7/transcript' && init?.method === 'PATCH') {
        return new Response(JSON.stringify(updatedResult), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      return new Response('{}', { status: 404 });
    });

    render(App);

    await fireEvent.click(screen.getByRole('link', { name: 'Suchverläufe' }));
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /abgeschlossen · 1 Treffer/ })).toBeTruthy();
    });
    await fireEvent.click(screen.getByRole('button', { name: /abgeschlossen · 1 Treffer/ }));
    await waitFor(() => {
      expect(screen.getByText('NARA-Testkarte')).toBeTruthy();
    });
    await fireEvent.click(screen.getByRole('button', { name: /NARA-Testkarte/ }));

    const transcriptInput = screen.getByLabelText('Transkription') as HTMLTextAreaElement;
    expect(transcriptInput.value).toBe('Raw OCR Schultze Naumburg');
    await fireEvent.input(transcriptInput, { target: { value: 'Korrigierte Transkription' } });
    await fireEvent.click(screen.getByRole('button', { name: 'Transkription speichern' }));

    await waitFor(() => {
      expect(screen.getByText('Transkription gespeichert.')).toBeTruthy();
    });
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/search/job-1/results/7/transcript',
      expect.objectContaining({
        method: 'PATCH',
        body: JSON.stringify({ transcript_text: 'Korrigierte Transkription' })
      })
    );
    expect((screen.getByLabelText('Transkription') as HTMLTextAreaElement).value).toBe('Korrigierte Transkription');
    expect(screen.getByText('manuell korrigiert')).toBeTruthy();
  });
});
