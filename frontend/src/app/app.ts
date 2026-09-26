import { Component, computed, OnDestroy, OnInit, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Api } from './api';
import {
  Citation, Claim, ClaimResult, Example, PipelineEvent, SOURCE_STATUS, SourceCheck, Summary, VERDICT, Verdict,
} from './models';

interface Segment { text: string; claim?: Claim; }
interface Part { t: string; num: boolean; bad: boolean; }

const SEVERITY: Verdict[] = ['source_missing', 'contradicted', 'not_in_source', 'unverifiable', 'supported', 'pending'];
const NUM_RE = /(\d{1,3}(?:[  ]\d{3})+|\d+(?:[.,]\d+)?)\s?(%|процент\w*|percent|млн|млрд|million|billion)?/gi;

@Component({
  selector: 'app-root',
  imports: [FormsModule],
  templateUrl: './app.html',
})
export class App implements OnInit, OnDestroy {
  readonly VERDICT = VERDICT;
  readonly SOURCE_STATUS = SOURCE_STATUS;
  readonly legend: Verdict[] = ['source_missing', 'contradicted', 'not_in_source', 'unverifiable', 'supported'];

  // input
  input = signal('');
  examples = signal<Example[]>([]);
  error = signal<string | null>(null);
  showHow = signal(false);

  // report
  view = signal<'input' | 'result'>('input');
  reportId = signal<string | null>(null);
  reportText = signal('');
  cached = signal(false);
  running = signal(false);
  stage = signal('');
  claims = signal<Claim[]>([]);
  citations = signal<Citation[]>([]);
  checks = signal<Record<string, SourceCheck>>({});
  results = signal<Record<string, ClaimResult>>({});
  summary = signal<Summary | null>(null);
  selectedId = signal<string | null>(null);
  copied = signal(false);

  private closeStream: (() => void) | null = null;

  constructor(private api: Api) {}

  async ngOnInit() {
    this.examples.set(await this.api.examples().catch(() => []));
    const m = location.pathname.match(/^\/r\/([\w-]+)/);
    if (m) await this.openReport(m[1]);
    window.addEventListener('popstate', () => {
      if (!location.pathname.startsWith('/r/')) this.reset(false);
    });
  }

  ngOnDestroy() { this.closeStream?.(); }

  // ------------------------------------------------------------ derived state

  verdictOf(id: string): Verdict { return this.results()[id]?.verdict ?? 'pending'; }

  segments = computed<Segment[]>(() => {
    const text = this.reportText();
    const spans = this.claims().filter((c) => c.start >= 0 && c.end > c.start).sort((a, b) => a.start - b.start);
    const out: Segment[] = [];
    let pos = 0;
    for (const c of spans) {
      if (c.start < pos) continue; // overlapping span: skip, the claim is still listed below
      if (c.start > pos) out.push({ text: text.slice(pos, c.start) });
      out.push({ text: text.slice(c.start, c.end), claim: c });
      pos = c.end;
    }
    if (pos < text.length) out.push({ text: text.slice(pos) });
    return out;
  });

  unplacedClaims = computed(() => this.claims().filter((c) => c.start < 0));

  selected = computed(() => {
    const id = this.selectedId();
    const claim = this.claims().find((c) => c.id === id);
    return claim ? { claim, result: this.results()[claim.id] } : null;
  });

  progress = computed(() => {
    const total = this.claims().length;
    const done = Object.keys(this.results()).length;
    return { total, done, pct: total ? Math.round((100 * done) / total) : 0 };
  });

  liveCounts = computed(() => {
    const c: Record<string, number> = {};
    for (const r of Object.values(this.results())) c[r.verdict] = (c[r.verdict] ?? 0) + 1;
    return c;
  });

  matrix = computed(() => {
    const cells = { dangerous: [] as Claim[], safe: [] as Claim[], cautiousOk: [] as Claim[], cautiousWeak: [] as Claim[] };
    for (const c of this.claims()) {
      const v = this.verdictOf(c.id);
      if (v === 'pending') continue;
      const confident = c.certainty !== 'hedged';
      const ok = v === 'supported';
      if (confident && !ok) cells.dangerous.push(c);
      else if (confident && ok) cells.safe.push(c);
      else if (!confident && ok) cells.cautiousOk.push(c);
      else cells.cautiousWeak.push(c);
    }
    return cells;
  });

  sortedCitations = computed(() => {
    const order = ['not_found', 'mismatch', 'unreachable', 'unchecked', 'exists'];
    const ch = this.checks();
    return [...this.citations()].sort(
      (a, b) => order.indexOf(ch[a.id]?.status ?? 'exists') - order.indexOf(ch[b.id]?.status ?? 'exists'),
    );
  });

  claimsForCitation(cid: string): Claim[] { return this.claims().filter((c) => c.citation_ids.includes(cid)); }

  citationLabel(cid: string | null | undefined): string {
    const c = this.citations().find((x) => x.id === cid);
    if (!c) return '';
    return c.title || c.raw || c.url || c.doi || c.id;
  }

  // ------------------------------------------------------------ actions

  useExample(e: Example) {
    this.input.set(e.text);
    this.run();
  }

  async run() {
    const text = this.input().trim();
    this.error.set(null);
    if (text.length < 20) {
      this.error.set('Вставьте ответ ИИ целиком — хотя бы пару предложений.');
      return;
    }
    try {
      const { id, cached } = await this.api.start(text);
      this.begin(id, text, cached);
      history.pushState({}, '', `/r/${id}`);
      this.listen(id);
    } catch (e) {
      this.error.set((e as Error).message);
    }
  }

  private begin(id: string, text: string, cached: boolean) {
    this.closeStream?.();
    this.reportId.set(id);
    this.reportText.set(text);
    this.cached.set(cached);
    this.claims.set([]);
    this.citations.set([]);
    this.checks.set({});
    this.results.set({});
    this.summary.set(null);
    this.selectedId.set(null);
    this.stage.set('Отправляю ответ на проверку…');
    this.running.set(true);
    this.view.set('result');
    window.scrollTo({ top: 0 });
  }

  private listen(id: string) {
    this.closeStream = this.api.stream(id, (e) => this.apply(e), () => this.running.set(false));
  }

  private async openReport(id: string) {
    const rep = await this.api.report(id);
    if (!rep) {
      this.error.set('Отчёт не найден: возможно, сервер перезапускался. Запустите проверку заново.');
      history.replaceState({}, '', '/');
      return;
    }
    this.input.set(rep.text);
    this.begin(id, rep.text, false);
    for (const e of rep.events) this.apply(e);
    this.running.set(false);
  }

  apply(e: PipelineEvent) {
    switch (e.type) {
      case 'stage':
        this.stage.set(e.message);
        break;
      case 'cached':
        this.cached.set(true);
        break;
      case 'extracted':
        this.claims.set(e.claims);
        this.citations.set(e.citations);
        this.stage.set(`Нашли ${e.claims.length} утверждений и ${e.citations.length} источников. Проверяем…`);
        break;
      case 'source':
        this.checks.update((m) => ({ ...m, [e.check.citation_id]: e.check }));
        break;
      case 'claim': {
        this.results.update((m) => ({ ...m, [e.result.claim_id]: e.result }));
        const cur = this.selectedId();
        const rank = (id: string | null) => (id ? SEVERITY.indexOf(this.verdictOf(id)) : 99);
        if (!cur || rank(e.result.claim_id) < rank(cur)) this.selectedId.set(e.result.claim_id);
        break;
      }
      case 'done':
        this.summary.set(e.summary);
        this.running.set(false);
        break;
      case 'error':
        this.error.set(e.message);
        this.running.set(false);
        break;
    }
  }

  select(id: string) {
    this.selectedId.set(id);
    if (window.innerWidth < 960) {
      setTimeout(() => document.getElementById('evidence')?.scrollIntoView({ behavior: 'smooth', block: 'start' }));
    }
  }

  reset(push = true) {
    this.closeStream?.();
    this.view.set('input');
    this.running.set(false);
    this.error.set(null);
    this.reportId.set(null);
    if (push) history.pushState({}, '', '/');
  }

  async share() {
    const url = `${location.origin}/r/${this.reportId()}`;
    try {
      await navigator.clipboard.writeText(url);
      this.copied.set(true);
      setTimeout(() => this.copied.set(false), 2000);
    } catch {
      prompt('Ссылка на отчёт:', url);
    }
  }

  // ------------------------------------------------------------ formatting helpers

  /** Split text into parts, marking numbers; numbers absent from `other` are flagged. */
  numberParts(text: string, flagAgainst?: string[]): Part[] {
    const bare = (s: string) => s.replace(/[^\d.,]/g, '').replace(',', '.').replace(/^0+(?=\d)/, '');
    const other = new Set((flagAgainst ?? []).map((n) => bare(n)));
    const parts: Part[] = [];
    let last = 0;
    for (const m of text.matchAll(NUM_RE)) {
      const idx = m.index ?? 0;
      const val = bare(m[1].replace(/[  ]/g, ''));
      if (/^(19|20)\d\d$/.test(val) && !m[2]) continue; // years are not the point
      if (idx > last) parts.push({ t: text.slice(last, idx), num: false, bad: false });
      parts.push({ t: m[0], num: true, bad: !!flagAgainst && !other.has(val) });
      last = idx + m[0].length;
    }
    if (last < text.length) parts.push({ t: text.slice(last), num: false, bad: false });
    return parts;
  }

  host(url?: string | null): string {
    if (!url) return '';
    try { return new URL(url).hostname.replace(/^www\./, ''); } catch { return url; }
  }

  seconds(ms: number): string { return (ms / 1000).toFixed(ms < 10000 ? 1 : 0).replace('.', ','); }
}
