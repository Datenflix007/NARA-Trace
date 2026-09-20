import { findTextOccurrences, type AnnotationDocument } from '@datenflix007/ts-text-marker-core';

export type TranscriptAnnotationInput = {
  id: string;
  title: string;
  text: string;
  source?: string;
  terms?: readonly string[];
};

const SEARCH_LABEL = {
  id: 'search-match',
  name: 'Suchbegriff',
  color: '#d0a200',
  description: 'Begriff aus dem aktuellen Suchprofil'
} as const;

/**
 * Maps NARATrace's read-only search terms to the public TextMarker document
 * format. The transcript stays the source of truth; annotations are rebuilt
 * whenever its text or search profile changes.
 */
export function createTranscriptAnnotationDocument(input: TranscriptAnnotationInput): AnnotationDocument {
  const terms = [...new Set((input.terms ?? []).map((term) => term.trim()).filter((term) => term.length >= 2))];

  return {
    version: '1.0',
    document: {
      id: input.id,
      title: input.title,
      source: input.source,
      type: 'txt',
      language: 'de'
    },
    labels: terms.length > 0 ? [SEARCH_LABEL] : [],
    annotations: terms.flatMap((term, termIndex) =>
      findTextOccurrences(input.text, term).map((match) => ({
        id: `search-${termIndex + 1}-${match.occurrence}`,
        labelId: SEARCH_LABEL.id,
        quote: match.quote,
        start: match.start,
        end: match.end,
        occurrence: match.occurrence,
        metadata: { query: term }
      }))
    )
  };
}
