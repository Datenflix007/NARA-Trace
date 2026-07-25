import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { afterEach, describe, expect, it, vi } from 'vitest';

import App from './App.svelte';

describe('App', () => {
  afterEach(() => {
    window.location.hash = '';
    vi.restoreAllMocks();
    cleanup();
  });

  it('zeigt Projekttitel und NARA-Quellenkennzeichnung', () => {
    render(App);

    expect(screen.getByRole('heading', { name: 'NARATrace' })).toBeTruthy();
    expect(screen.getByText('NARA Catalog')).toBeTruthy();
    expect(
      screen.getByText(/U.S. National Archives and Records Administration - National Archives Catalog/)
    ).toBeTruthy();
  });

  it('wechselt per Hauptnavigation zur neuen Suche', async () => {
    render(App);

    await fireEvent.click(screen.getByRole('link', { name: 'Neue Suche' }));

    expect(screen.getByRole('heading', { name: 'Neue Suche' })).toBeTruthy();
    expect(screen.getByLabelText('Nachname')).toBeTruthy();
    expect(screen.getByLabelText('Geburtsdatum')).toBeTruthy();
    expect(screen.getByLabelText('Wohnorte')).toBeTruthy();
    expect(screen.getByLabelText('Mitgliedsnummer')).toBeTruthy();
  });

  it('wechselt per Hauptnavigation zu den Einstellungen', async () => {
    render(App);

    await fireEvent.click(screen.getByRole('link', { name: 'Einstellungen' }));

    expect(screen.getByRole('heading', { name: 'Einstellungen' })).toBeTruthy();
    expect(screen.getByText('NARA API-Schlüssel')).toBeTruthy();
  });

  it('legt aus dem Suchformular einen Backend-Suchjob an', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = String(input);
      if (url === '/api/search' && init?.method === 'POST') {
        return new Response(
          JSON.stringify({
            id: 'job-1',
            status: 'partial',
            mode: 'quick',
            title: 'Paul Schultze-Naumburg',
            progress_current: 2,
            progress_total: 6,
            warnings: ['Suchprofil wurde lokal gespeichert.'],
            error_message: null,
            created_at: new Date().toISOString(),
            completed_at: new Date().toISOString(),
            result_count: 0,
            mock_mode: false
          }),
          { status: 201, headers: { 'Content-Type': 'application/json' } }
        );
      }
      if (url === '/api/search/job-1/results') {
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
    expect(screen.getByText('job-1')).toBeTruthy();
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/search',
      expect.objectContaining({
        method: 'POST',
        body: expect.stringContaining('membership_number')
      })
    );
  });
});
