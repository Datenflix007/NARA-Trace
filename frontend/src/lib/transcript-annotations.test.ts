import { describe, expect, it } from 'vitest';
import { createTranscriptAnnotationDocument } from './transcript-annotations';

describe('createTranscriptAnnotationDocument', () => {
  it('creates a valid, deterministic document from searchable transcript terms', () => {
    const document = createTranscriptAnnotationDocument({
      id: 'result-7',
      title: 'Karte 7',
      text: 'Paul Schultze-Naumburg. Mitgliedsnummer 347541.',
      source: 'NARA Extracted Text',
      terms: ['Paul', '347541', 'Paul', ' ']
    });

    expect(document.document).toMatchObject({ id: 'result-7', type: 'txt' });
    expect(document.labels).toHaveLength(1);
    expect(document.annotations).toEqual([
      expect.objectContaining({ id: 'search-1-1', quote: 'Paul', start: 0, end: 4 }),
      expect.objectContaining({ id: 'search-2-1', quote: '347541' })
    ]);
  });

  it('does not create a dangling label when no usable search term exists', () => {
    const document = createTranscriptAnnotationDocument({ id: 'empty', title: 'Leer', text: 'OCR', terms: [' '] });

    expect(document.labels).toEqual([]);
    expect(document.annotations).toEqual([]);
  });
});
