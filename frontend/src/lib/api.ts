export type HealthResponse = {
  status: 'ok';
  app: string;
  version: string;
  mock_mode: boolean;
  bind_host: string;
  bind_port: number;
  data_dir: string;
  database_path: string;
};

export type SearchRequest = {
  first_name?: string;
  last_name: string;
  variants?: string;
  birth_date?: string;
  birth_year?: number;
  residence_places?: string;
  membership_number?: string;
  naid?: string;
  record_group?: string;
  max_candidates: number;
  demo_mode?: boolean;
};

export type SearchJobResponse = {
  id: string;
  status: string;
  mode: string;
  title: string | null;
  progress_current: number;
  progress_total: number;
  warnings: string[];
  error_message: string | null;
  created_at: string;
  completed_at: string | null;
  result_count: number;
  mock_mode: boolean;
};

export type MatchEvidenceResponse = {
  kind: string;
  label: string;
  detail: string | null;
  score_delta: number;
  source_type: string | null;
};

export type SearchResultResponse = {
  id: number;
  job_id: string;
  match_score: number;
  category: string;
  suspected_person_name: string | null;
  birth_date: string | null;
  birth_place: string | null;
  relevant_pages_count: number;
  naid: string;
  title: string | null;
  record_group: string | null;
  series: string | null;
  original_url: string | null;
  text_origin: string;
  data_source: 'NARA' | 'MOCK' | 'LOCAL';
  retrieved_at: string | null;
  source_page_id: number | null;
  source_page_url: string | null;
  source_page_label: string | null;
  transcript_text: string | null;
  transcript_source: string | null;
  transcript_edited: boolean;
  evidences: MatchEvidenceResponse[];
};

export type SettingsResponse = {
  mock_mode: boolean;
  data_dir: string;
  cache_dir: string;
  database_path: string;
  nara_api_key_configured: boolean;
  nara_api_key_source: 'keyring' | 'environment' | 'none';
  nara_api_usage: NaraApiUsageResponse;
};

export type NaraApiUsageResponse = {
  request_count: number;
  request_limit: number;
  percent_used: number;
  period: string;
  reset_at: string;
  counted_locally: boolean;
};

export type ApiKeyTestResponse = {
  ok: boolean;
  live_tested: boolean;
  message: string;
  nara_api_usage: NaraApiUsageResponse | null;
};

export async function fetchHealth(): Promise<HealthResponse> {
  const response = await fetch('/api/health');
  if (!response.ok) {
    throw new Error('Der Backend-Status konnte nicht geladen werden.');
  }
  return response.json() as Promise<HealthResponse>;
}

export async function startSearch(payload: SearchRequest): Promise<SearchJobResponse> {
  const response = await fetch('/api/search', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(payload)
  });
  if (!response.ok) {
    throw new Error('Der Suchjob konnte nicht angelegt werden.');
  }
  return response.json() as Promise<SearchJobResponse>;
}

export async function fetchSearchResults(jobId: string): Promise<SearchResultResponse[]> {
  const response = await fetch(`/api/search/${jobId}/results`);
  if (!response.ok) {
    throw new Error('Die Suchergebnisse konnten nicht geladen werden.');
  }
  return response.json() as Promise<SearchResultResponse[]>;
}

export async function fetchSearchJob(jobId: string): Promise<SearchJobResponse> {
  const response = await fetch(`/api/search/${jobId}`);
  if (!response.ok) {
    throw new Error('Der Suchjob-Status konnte nicht geladen werden.');
  }
  return response.json() as Promise<SearchJobResponse>;
}

export async function fetchSearchHistory(): Promise<SearchJobResponse[]> {
  const response = await fetch('/api/search');
  if (!response.ok) {
    throw new Error('Die Suchverläufe konnten nicht geladen werden.');
  }
  return response.json() as Promise<SearchJobResponse[]>;
}

export async function deleteSearchJob(jobId: string): Promise<void> {
  const response = await fetch(`/api/search/${jobId}`, { method: 'DELETE' });
  if (!response.ok) {
    throw new Error('Der Suchlauf konnte nicht gelöscht werden.');
  }
}

export async function deleteSearchResult(jobId: string, resultId: number): Promise<void> {
  const response = await fetch(`/api/search/${jobId}/results/${resultId}`, { method: 'DELETE' });
  if (!response.ok) {
    throw new Error('Der Treffer konnte nicht gelöscht werden.');
  }
}

export async function updateSearchResultTranscript(
  jobId: string,
  resultId: number,
  transcriptText: string
): Promise<SearchResultResponse> {
  const response = await fetch(`/api/search/${jobId}/results/${resultId}/transcript`, {
    method: 'PATCH',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({ transcript_text: transcriptText })
  });
  if (!response.ok) {
    throw new Error('Die Transkription konnte nicht gespeichert werden.');
  }
  return response.json() as Promise<SearchResultResponse>;
}

export async function fetchSettings(): Promise<SettingsResponse> {
  const response = await fetch('/api/settings');
  if (!response.ok) {
    throw new Error('Die Einstellungen konnten nicht geladen werden.');
  }
  return response.json() as Promise<SettingsResponse>;
}

export async function saveNaraApiKey(naraApiKey: string): Promise<SettingsResponse> {
  const response = await fetch('/api/settings', {
    method: 'PATCH',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({ nara_api_key: naraApiKey })
  });
  if (!response.ok) {
    throw new Error('Der NARA API-Schlüssel konnte nicht gespeichert werden.');
  }
  return response.json() as Promise<SettingsResponse>;
}

export async function testNaraApiKey(): Promise<ApiKeyTestResponse> {
  const response = await fetch('/api/settings/test-nara-key', { method: 'POST' });
  if (!response.ok) {
    throw new Error('Der NARA API-Schlüssel konnte nicht getestet werden.');
  }
  return response.json() as Promise<ApiKeyTestResponse>;
}

export async function deleteNaraApiKey(): Promise<SettingsResponse> {
  const response = await fetch('/api/settings/nara-key', { method: 'DELETE' });
  if (!response.ok) {
    throw new Error('Der NARA API-Schlüssel konnte nicht gelöscht werden.');
  }
  return response.json() as Promise<SettingsResponse>;
}
