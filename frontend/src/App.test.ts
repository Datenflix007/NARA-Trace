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
    expect(screen.getByText('LOCAL-PDF-SCHULTZE-NAUMBURG-1931')).toBeTruthy();
    expect(screen.getByText('Wohnort: Naumburg; später Weimar')).toBeTruthy();
    expect(screen.queryByText(/Ulm|Münsterplatz/)).toBeNull();
    expect(
      screen.getByText(/U.S. National Archives and Records Administration - National Archives Catalog/)
    ).toBeTruthy();
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
  });

  it('legt aus dem Suchformular einen Backend-Suchjob ohne Demo-Flag an', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = String(input);
      if (url === '/api/search' && init?.method === 'POST') {
        return new Response(JSON.stringify(searchJob({ id: 'job-new', status: 'partial', result_count: 0 })), {
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

  it('öffnet im Suchverlauf einen Job und sortiert Treffer nach Wahrscheinlichkeit', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = String(input);
      if (url === '/api/search') {
        return new Response(JSON.stringify([searchJob()]), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      if (url === '/api/search/job-1/results') {
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
      expect(screen.getByRole('button', { name: /complete · 2 Treffer/ })).toBeTruthy();
    });
    await fireEvent.click(screen.getByRole('button', { name: /complete · 2 Treffer/ }));

    await waitFor(() => {
      expect(screen.getAllByText('Hoher Treffer').length).toBeGreaterThan(0);
    });

    const high = screen.getAllByText('Hoher Treffer')[0];
    const low = screen.getAllByText('Niedriger Treffer')[0];
    expect(Boolean(high.compareDocumentPosition(low) & Node.DOCUMENT_POSITION_FOLLOWING)).toBe(true);
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
      expect(screen.getByRole('button', { name: /complete · 1 Treffer/ })).toBeTruthy();
    });
    await fireEvent.click(screen.getByRole('button', { name: /complete · 1 Treffer/ }));
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
});
