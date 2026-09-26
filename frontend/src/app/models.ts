// Mirrors backend/app/models.py
export type Verdict = 'supported' | 'contradicted' | 'not_in_source' | 'source_missing' | 'unverifiable' | 'pending';
export type SourceStatus = 'exists' | 'mismatch' | 'not_found' | 'unreachable' | 'unchecked';

export interface Citation {
  id: string; raw: string; kind: string; url?: string | null; doi?: string | null;
  title?: string | null; authors: string[]; year?: number | null; venue?: string | null;
}

export interface MatchedRecord { title?: string | null; authors: string[]; year?: number | null; venue?: string | null; url?: string | null; }

export interface SourceCheck {
  citation_id: string; status: SourceStatus; method: string; detail: string;
  matched?: MatchedRecord | null; text_scope: 'full' | 'abstract' | 'none'; differences: string[];
}

export interface Replacement {
  title: string; authors: string[]; year?: number | null; venue?: string | null; doi?: string | null; url?: string | null;
  abstract: string; cited_by_count: number; volume?: string | null; issue?: string | null; pages?: string | null;
  confirmed: boolean; quote?: string | null;
}

export interface Claim {
  id: string; text: string; span: string; start: number; end: number; citation_ids: string[];
  certainty: 'hedged' | 'neutral' | 'assertive'; certainty_markers: string[]; queries: string[];
}

export interface Evidence {
  source_label: string; url?: string | null; citation_id?: string | null; quote: string;
  quote_verified: boolean; stance: 'supports' | 'contradicts' | 'neutral'; tier?: string | null;
}

export interface ClaimResult {
  claim_id: string; verdict: Verdict; mode: 'cited' | 'attack'; reason: string; evidence: Evidence[];
  numbers?: { claim_numbers: string[]; source_numbers: string[]; mismatch: boolean } | null; notes: string[];
  search?: { provider: string; queries: string[]; pages: number; domains: string[] } | null;
}

export interface Summary {
  headline: string; counts: Record<string, number>; sources_total: number; sources_missing: number;
  sources_mismatch: number; danger_zone: number; duration_ms: number;
}

export type PipelineEvent =
  | { type: 'stage'; stage: string; message: string }
  | { type: 'extracted'; claims: Claim[]; citations: Citation[] }
  | { type: 'source'; check: SourceCheck }
  | { type: 'claim'; result: ClaimResult }
  | { type: 'replacements'; citation_id: string; claim_id?: string | null; works: Replacement[] }
  | { type: 'done'; summary: Summary }
  | { type: 'cached' }
  | { type: 'error'; message: string };

export interface Example { id: string; title: string; subtitle: string; text: string; }

export const VERDICT: Record<Verdict, { label: string; short: string; tone: string }> = {
  source_missing: { label: 'Источник не существует', short: 'Нет источника', tone: 'red' },
  contradicted: { label: 'Источник говорит другое', short: 'Противоречит', tone: 'orange' },
  not_in_source: { label: 'В источнике этого нет', short: 'Нет в источнике', tone: 'yellow' },
  unverifiable: { label: 'Не удалось проверить', short: 'Не подтверждено', tone: 'grey' },
  supported: { label: 'Подтверждено цитатой', short: 'Подтверждено', tone: 'green' },
  pending: { label: 'Проверяем…', short: 'Проверяем', tone: 'pending' },
};

export const SOURCE_STATUS: Record<SourceStatus, { label: string; tone: string }> = {
  exists: { label: 'Существует', tone: 'green' },
  mismatch: { label: 'Данные искажены', tone: 'orange' },
  not_found: { label: 'Не существует', tone: 'red' },
  unreachable: { label: 'Нет доступа', tone: 'grey' },
  unchecked: { label: 'Не проверить', tone: 'grey' },
};

export const TIER: Record<string, string> = {
  official: 'официальный или научный источник', reference: 'справочник', media: 'СМИ', other: 'прочий сайт',
};
