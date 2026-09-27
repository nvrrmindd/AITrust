import { Component, computed, OnDestroy, OnInit, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Api } from './api';
import QRCode from 'qrcode';
import { apa, gost } from './cite';
import {
  Citation, Claim, ClaimResult, Example, PipelineEvent, Replacement, SOURCE_STATUS, SourceCheck, Summary, TIER, VERDICT, Verdict, BibItem, DocumentMeta, FILE_FORMATS, Score,
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
  readonly TIER = TIER;
  readonly legend: Verdict[] = ['source_missing', 'contradicted', 'not_in_source', 'unverifiable', 'supported'];

  // input
  input = signal('');
  examples = signal<Example[]>([]);
  error = signal<string | null>(null);
  searchProvider = signal<string>('tavily');
  supportEmail = signal<string | null>(null);
  notices = signal<string[]>([]);
  openFaq = signal<number | null>(0);
  readonly year = new Date().getFullYear();
  readonly WHO: Record<string, string> = { ai: 'Нейросеть', code: 'Код', registry: 'Реестры', web: 'Веб-поиск', you: 'Вы' };
  readonly stairs = [
    { who: 'ai', title: 'Разбор', text: 'Нейросеть делит ответ на отдельные утверждения и находит, на какой источник ссылается каждое. Ссылки и DOI код дополнительно находит сам.' },
    { who: 'registry', title: 'Существует ли источник', text: 'DOI сверяем с мировым реестром doi.org, статьи ищем в Crossref и OpenAlex, ссылки открываем.', out: 'Источник не существует', tone: 'red' },
    { who: 'code', title: 'Чтение источника', text: 'Скачиваем страницу, PDF или аннотацию статьи и выбираем фрагменты, где сказано о том же. Пейвол — честное «нет доступа».', out: 'Нет доступа', tone: 'grey' },
    { who: 'ai', title: 'Поиск нужного места', text: 'Нейросеть читает фрагменты и приносит дословную цитату. Это предложение, а не приговор.' },
    { who: 'code', title: 'Сверка', text: 'Код ищет цитату в тексте источника и сравнивает числа. Цитаты нет дословно — вердикт выбрасывается.', out: 'В тексте 40% → в источнике 60%', tone: 'orange' },
    { who: 'web', title: 'Если источника нет', text: 'Ищем в интернете и подтверждения, и опровержения. Официальные сайты и справочники весят больше блогов.' },
    { who: 'you', title: 'Решение за вами', text: 'Вердикт, объяснение, цитата и ссылка на экране — проверить нас можно за пять секунд. Отчёт — в PDF с QR-кодом.', out: 'Подтверждено цитатой', tone: 'green' },
  ];
  readonly survey = {
    n: 11,
    rows: [
      { label: 'Используют ИИ для учёбы', value: 11, key: false },
      { label: 'Просили у ИИ источники', value: 10, key: false },
      { label: 'Находили выдуманную ссылку или цифру', value: 8, key: false },
      { label: 'Знают случаи наказания за выдуманные источники', value: 11, key: false },
      { label: 'Всегда проверяют источники', value: 1, key: true },
    ],
  };
  readonly bench = [
    { label: 'Настоящие', total: 34, ok: 31, skip: 1, bad: 2 },
    { label: 'Выдуманные', total: 23, ok: 17, skip: 6, bad: 0 },
    { label: 'Искажённые', total: 15, ok: 15, skip: 0, bad: 0 },
  ];
  readonly faq = [
    { q: 'Это ещё один ИИ-детектор?',
      a: 'Нет. Мы не угадываем, написан ли текст нейросетью. Мы проверяем, правда ли то, что в нём написано: существуют ли источники, говорят ли они то, что им приписали, и совпадают ли цифры.' },
    { q: 'Почему проверке можно доверять, если в ней тоже есть нейросеть?',
      a: 'Нейросеть только находит нужное место в источнике. Существует ли источник, решают реестры публикаций; совпадают ли цитата и числа — код. Если цитаты нет в источнике дословно, вердикт выбрасывается. А сама цитата всегда перед глазами — проверить нас можно за пять секунд.' },
    { q: 'Какие тексты можно проверить?',
      a: 'Любые на русском и английском: ответ нейросети, статью, новость, пост, реферат. Документы — .docx, .pdf, .txt, .md до 10 МБ. Если в документе есть список литературы, проверим каждый источник из него.' },
    { q: 'Что значит «нет доступа»?',
      a: 'Источник закрыт пейволом или защитой от ботов, либо научная база временно не ответила. Такой источник мы не называем выдуманным: повторите проверку позже или откройте ссылку сами.' },
    { q: 'Что происходит с моим текстом?',
      a: 'Для разбора текст передаётся провайдеру языковой модели, а отчёт хранится на сервере, чтобы открываться по ссылке. Мы не публикуем тексты и сами не используем их для обучения.' },
  ];
  showHow = signal(false);
  mode = signal<'answer' | 'file'>('answer');
  dragging = signal(false);
  uploading = signal(false);
  readonly FILE_FORMATS = FILE_FORMATS;

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
  replacements = signal<Record<string, Replacement[]>>({});
  copiedRef = signal<string | null>(null);
  summary = signal<Summary | null>(null);
  selectedId = signal<string | null>(null);
  copied = signal(false);

  // «Работа целиком»
  doc = signal<DocumentMeta | null>(null);
  bib = signal<BibItem[]>([]);
  score = signal<Score | null>(null);
  qr = signal<string>('');

  private closeStream: (() => void) | null = null;

  constructor(private api: Api) {}

  async ngOnInit() {
    this.api.health().then((h) => {
      if (!h) return;
      this.searchProvider.set(h.search);
      this.supportEmail.set(h.support_email || null);
    });
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

  /** Live source score while checks arrive; the server's final `score` event wins. */
  liveScore = computed<Score>(() => {
    const s = this.score();
    if (s) return s;
    const st = this.bib().map((b) => b.check?.status);
    const n = (x: string) => st.filter((v) => v === x).length;
    return { verified: n('exists'), total: st.length, fabricated: n('not_found'), distorted: n('mismatch'),
             unreachable: n('unreachable') + n('unchecked') };
  });

  bibChecked = computed(() => this.bib().filter((b) => b.check).length);

  reportUrl = computed(() => (this.reportId() ? `${location.origin}/r/${this.reportId()}` : ''));

  /** A suggested replacement only counts in the bibliography table if its abstract confirms the claim. */
  confirmedWork(cid: string): Replacement | null {
    return (this.replacements()[cid] ?? []).find((w) => w.confirmed) ?? null;
  }

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

  // ------------------------------------------------------------ «Работа целиком»

  onDrop(ev: DragEvent) {
    ev.preventDefault();
    this.dragging.set(false);
    const f = ev.dataTransfer?.files?.[0];
    if (f) this.runFile(f);
  }

  onPick(ev: Event) {
    const input = ev.target as HTMLInputElement;
    const f = input.files?.[0];
    input.value = '';
    if (f) this.runFile(f);
  }

  async runSample() {
    this.error.set(null);
    try {
      await this.runFile(await this.api.sampleDocx());
    } catch (e) {
      this.error.set((e as Error).message);
    }
  }

  async runFile(file: File) {
    this.error.set(null);
    const ext = file.name.toLowerCase().match(/\.[a-z]+$/)?.[0] ?? '';
    if (!FILE_FORMATS.split(',').includes(ext)) {
      this.error.set('Неподдерживаемый формат. Загрузите .docx, .pdf, .txt или .md.');
      return;
    }
    if (file.size > 10 * 1024 * 1024) {
      this.error.set('Файл больше 10 МБ.');
      return;
    }
    this.uploading.set(true);
    try {
      const { id, cached } = await this.api.checkFile(file);
      this.begin(id, '', cached);
      this.stage.set(`Читаю «${file.name}»…`);
      history.pushState({}, '', `/r/${id}`);
      this.listen(id);
    } catch (e) {
      this.error.set((e as Error).message);
    } finally {
      this.uploading.set(false);
    }
  }

  goCheck(mode: 'answer' | 'file') {
    if (this.view() !== 'input') this.reset();
    this.mode.set(mode);
    setTimeout(() => this.scrollToId('check'));
  }

  toggleFaq(i: number) {
    this.openFaq.set(this.openFaq() === i ? null : i);
  }

  scrollToId(id: string) {
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  printReport() {
    window.print();
  }

  private async makeQr() {
    const url = this.reportUrl();
    if (!url) return;
    try {
      this.qr.set(await QRCode.toDataURL(url, { margin: 1, width: 240 }));
    } catch {
      this.qr.set('');
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
    this.replacements.set({});
    this.doc.set(null);
    this.notices.set([]);
    this.bib.set([]);
    this.score.set(null);
    this.qr.set('');
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
      case 'document':
        this.doc.set({ filename: e.filename, chars: e.chars, checked_at: e.checked_at });
        this.reportText.set(e.text);
        this.makeQr();
        break;
      case 'bibliography': {
        const byId = new Map(this.bib().map((b) => [b.id, b]));
        for (const it of e.items) byId.set(it.id, { ...byId.get(it.id), ...it });
        this.bib.set([...byId.values()].sort((a, b) => a.n - b.n));
        const withCheck = e.items.filter((it) => it.check);
        if (withCheck.length) this.checks.update((m) => ({ ...m, ...Object.fromEntries(withCheck.map((it) => [it.id, it.check!])) }));
        if (!this.citations().length) this.citations.set(e.items.map((it) => it.citation));
        this.stage.set(`Список литературы: проверено ${this.bibChecked()} из ${this.bib().length}…`);
        break;
      }
      case 'score':
        this.score.set(e.score);
        break;
      case 'notice':
        this.notices.update((n) => [...n, e.message]);
        break;
      case 'source':
        this.checks.update((m) => ({ ...m, [e.check.citation_id]: e.check }));
        break;
      case 'replacements':
        this.replacements.update((m) => ({ ...m, [e.citation_id]: e.works }));
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

  async copyRef(r: Replacement, style: 'gost' | 'apa', key: string) {
    const text = style === 'gost' ? gost(r) : apa(r);
    try {
      await navigator.clipboard.writeText(text);
      this.copiedRef.set(key);
      setTimeout(() => this.copiedRef() === key && this.copiedRef.set(null), 2000);
    } catch {
      prompt('Ссылка на работу:', text);
    }
  }

  // ------------------------------------------------------------ formatting helpers

  authorsShort(authors: string[]): string {
    return authors.length > 3 ? `${authors.slice(0, 3).join(', ')} и др.` : authors.join(', ');
  }

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

  checkedAt(iso: string): string {
    try {
      return new Date(iso).toLocaleString('ru-RU', { dateStyle: 'long', timeStyle: 'short' });
    } catch { return iso; }
  }

  seconds(ms: number): string { return (ms / 1000).toFixed(ms < 10000 ? 1 : 0).replace('.', ','); }
}
