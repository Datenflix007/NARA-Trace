import { afterEach, describe, expect, it, vi } from 'vitest';
import { fetchPageHitRegions } from './api';

describe('fetchPageHitRegions', () => {
  afterEach(() => vi.restoreAllMocks());

  it('returns OCR regions for the requested terms', async () => {
    const regions = [{ term: 'Paul', occurrence: 1, x: 25, y: 31, width: 8, height: 3 }];
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      json: async () => regions
    } as Response);

    await expect(fetchPageHitRegions(42, ['Paul', '347541'])).resolves.toEqual(regions);
    expect(fetchMock).toHaveBeenCalledWith('/api/pages/42/highlights?terms=Paul&terms=347541');
  });
});
