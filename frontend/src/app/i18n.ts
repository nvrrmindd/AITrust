// UI strings in Russian, English and Kazakh. Kazakh should be proofread by a native speaker before release.
import type { SourceStatus, Summary, Verdict } from './models';

export type Lang = 'ru' | 'en' | 'kk';
export const LANGS: { id: Lang; label: string; name: string }[] = [
  { id: 'ru', label: 'RU', name: 'Русский' },
  { id: 'en', label: 'EN', name: 'English' },
  { id: 'kk', label: 'KZ', name: 'Қазақша' },
];

interface Step { who: 'ai' | 'code' | 'registry' | 'web' | 'you'; title: string; text: string; out?: string; tone?: string }

export interface Dict {
  locale: string;
  decimal: string;
  nav: { newCheck: string; how: string; toLight: string; toDark: string; lang: string };
  hero: { kicker: string; lede: string; points: string[]; cta: string };
  art: { p1: string; m1: string; p2: string; m2: string; p3: string; m3: string; quoteOk: string; noDoi: string };
  trust: { label: string; web: string; primary: string; aria: string };
  check: {
    title: string; tabText: string; tabDoc: string; dzTitle: string; dzBusy: string; dzSub: string; dzPick: string;
    dzHint: string; sample: string; textLabel: string; placeholder: string; chars: string; run: string;
    wikiNotice: string; examples: string;
  };
  stairs: { title: string; sub: string; who: Record<Step['who'], string>; steps: Step[] };
  numbers: {
    title: string; surveyTitle: string; surveySub: (n: number) => string; surveyRows: string[]; of: string;
    surveyNote: string; benchTitle: string; benchSub: string; ok: string; skip: string; bad: string;
    benchRows: string[]; benchNote: string; showTable: string; labelledAs: string;
  };
  audience: { title: string; rows: { who: string; text: string; go: string; mode: 'answer' | 'file' }[] };
  cta: { title: string; text: string; button: string };
  faq: { title: string; items: { q: string; a: string }[] };
  report: {
    printBrand: string; printFile: string; printDate: string; printReport: string; printCaption: string; qrAlt: string;
    scoreTitle: string; fabricated: string; distorted: string; unreachable: string; checkedOf: (a: number, b: number) => string;
    tallyAria: string; meta: (claims: number, sources: number, secs: string, cached: boolean) => string;
    share: string; copied: string; pdf: string; progress: (a: number, b: number) => string;
    bibTitle: string; bibCols: string[]; checking: string; confirmedWork: string; gost: string; copiedShort: string;
    docTitle: string; textTitle: string; hint: string; more: string; markedAria: string;
    attackUnverified: string; attackMode: string; inText: string; inSource: string; quoteVerified: string;
    refutes: string; supports: string; source: string; linkInText: string;
    searched: (q: number, p: number) => string; sites: string; assertive: (m: string) => string;
    emptyRunning: string; emptyIdle: string;
    sourcesTitle: string; open: string; how: string; byAbstract: string; byFull: string; searching: string;
    noRepl: string; replTitle: string; replConfirmed: string; replSimilar: string; copyGost: string; copyApa: string;
    replCaption: string;
    matrixTitle: string; matrixSub: string; sure: string; cautious: string; dangerous: string; safe: string;
    cautiousWeak: string; cautiousOk: string; notConfirmed: string; confirmedByQuote: string;
  };
  modal: { title: string; close: string; steps: { b: string; t: string }[]; note: string };
  footer: { tagline: string; product: string; checkText: string; checkDoc: string; how: string; dev: string; support: string; bug: string; motto: string };
  verdict: Record<Verdict, { label: string; short: string }>;
  status: Record<SourceStatus, string>;
  tier: Record<string, string>;
  headline: (s: Summary) => string;
  recheck: { note: string; button: string };
  msg: {
    tooShort: string; format: string; tooBig: string; reportMissing: string; sending: string;
    reading: (f: string) => string; found: (c: number, s: number) => string; bibProgress: (a: number, b: number) => string;
    server: (s: number) => string; short422: string; sampleMissing: string;
  };
}


const ruPlural = (n: number, one: string, few: string, many: string) => {
  const m = Math.abs(n) % 100, d = m % 10;
  return m > 10 && m < 20 ? many : d === 1 ? one : d >= 2 && d <= 4 ? few : many;
};

function parts(s: Summary) {
  const c = s.counts;
  const total = Object.entries(c).filter(([k]) => k !== 'pending').reduce((a, [, v]) => a + v, 0);
  return { total, ok: c['supported'] || 0, bad: c['contradicted'] || 0, weak: (c['unverifiable'] || 0) + (c['not_in_source'] || 0) };
}
const cap = (x: string) => x.charAt(0).toUpperCase() + x.slice(1);

function headlineRu(s: Summary): string {
  const { total, ok, bad, weak } = parts(s);
  const p: string[] = [];
  if (s.sources_total && s.sources_missing) p.push(`${s.sources_missing} из ${s.sources_total} ${ruPlural(s.sources_total, 'источника', 'источников', 'источников')} не существуют`);
  if (s.sources_mismatch) p.push(`${s.sources_mismatch} ${ruPlural(s.sources_mismatch, 'источник искажён', 'источника искажены', 'источников искажены')}`);
  if (bad) p.push(`${bad} ${ruPlural(bad, 'утверждение противоречит', 'утверждения противоречат', 'утверждений противоречат')} источникам`);
  if (!p.length) return (total ? `Подтверждено ${ok} из ${total} утверждений` : 'Проверяемых утверждений не найдено') + (weak ? `, ${weak} — без доказательств.` : '.');
  return cap(p.join('; ')) + '.';
}

function headlineEn(s: Summary): string {
  const { total, ok, bad, weak } = parts(s);
  const p: string[] = [];
  if (s.sources_total && s.sources_missing) p.push(`${s.sources_missing} of ${s.sources_total} sources do not exist`);
  if (s.sources_mismatch) p.push(`${s.sources_mismatch} source${s.sources_mismatch === 1 ? ' is' : 's are'} distorted`);
  if (bad) p.push(`${bad} claim${bad === 1 ? ' contradicts' : 's contradict'} the sources`);
  if (!p.length) return (total ? `Confirmed ${ok} of ${total} claims` : 'No checkable claims found') + (weak ? `, ${weak} without evidence.` : '.');
  return cap(p.join('; ')) + '.';
}

function headlineKk(s: Summary): string {
  const { total, ok, bad, weak } = parts(s);
  const p: string[] = [];
  if (s.sources_total && s.sources_missing) p.push(`жоқ дереккөздер: ${s.sources_missing} / ${s.sources_total}`);
  if (s.sources_mismatch) p.push(`бұрмаланған дереккөздер: ${s.sources_mismatch}`);
  if (bad) p.push(`дереккөздерге қайшы тұжырымдар: ${bad}`);
  if (!p.length) return (total ? `Расталған тұжырымдар: ${ok} / ${total}` : 'Тексерілетін тұжырымдар табылмады') + (weak ? `, дәлелсіз: ${weak}.` : '.');
  return cap(p.join('; ')) + '.';
}

const ru: Dict = {
  locale: 'ru-RU', decimal: ',',
  nav: { newCheck: 'Новая проверка', how: 'Как мы проверяем', toLight: 'Светлая тема', toDark: 'Тёмная тема', lang: 'Язык' },
  hero: {
    kicker: 'Можно ли верить ответу ИИ?',
    lede: 'Вставьте ответ ChatGPT, Gemini, Claude или любой другой нейросети. Trustable? разберёт его на утверждения, откроет каждый источник и покажет, что там написано на самом деле, — дословной цитатой.',
    points: ['Существует ли источник, проверяют реестры публикаций и сам сайт — не нейросеть', 'Цифры сравнивает код', 'Нет источника? Ищем и подтверждения, и опровержения'],
    cta: 'Проверить текст',
  },
  art: {
    p1: 'Нейросети регулярно ошибаются в ссылках:', m1: 'GPT-4 выдумывает 18% источников', p2: 'ИИ-поисковики',
    m2: 'ошибаются в 40% запросов', p3: ', а в Казахстане', m3: '68% студентов не проверяют ссылки (Ахметова, 2024)',
    quoteOk: '✓ цитата найдена дословно', noDoi: 'DOI не зарегистрирован в реестре doi.org',
  },
  trust: { label: 'Проверяем по', web: 'веб-поиск', primary: 'сайт первоисточника', aria: 'Источники проверки' },
  check: {
    title: 'Что проверяем?', tabText: 'Текст', tabDoc: 'Документ', dzTitle: 'Перетащите документ сюда', dzBusy: 'Загружаю…',
    dzSub: 'курсовая, статья, эссе, отчёт, любой документ · .docx, .pdf, .txt, .md · до 10 МБ', dzPick: 'или выберите файл',
    dzHint: 'Проверим каждый источник из списка литературы, утверждения со ссылками и главные факты в тексте без ссылок.', sample: 'Попробовать на примере (DOCX)',
    textLabel: 'Текст для проверки',
    placeholder: 'Вставьте любой текст: ответ нейросети, статью, новость, абзац из реферата. Если у текста есть список источников — вставьте и его.',
    chars: 'символов', run: 'Проверить',
    wikiNotice: 'Веб-поиск не подключён: утверждения без источников проверяются только по Википедии.',
    examples: 'Или посмотрите на примерах',
  },
  stairs: {
    title: 'Путь одного утверждения',
    sub: 'Каждое утверждение поднимается по этой лестнице. Нейросеть на ней дважды: разбирает текст и предлагает вердикт с цитатой. Всё остальное — реестры и код, и у кода право вето.',
    who: { ai: 'Нейросеть', code: 'Код', registry: 'Реестры', web: 'Веб-поиск', you: 'Вы' },
    steps: [
      { who: 'ai', title: 'Разбор', text: 'Нейросеть делит ответ на отдельные утверждения и находит, на какой источник ссылается каждое. Ссылки и DOI код дополнительно находит сам.' },
      { who: 'registry', title: 'Существует ли источник', text: 'DOI сверяем с мировым реестром doi.org, статьи ищем в Crossref и OpenAlex, веб-ссылки открываем напрямую. Нейросеть в этом не участвует.', out: 'Источник не существует', tone: 'red' },
      { who: 'code', title: 'Чтение источника', text: 'Скачиваем страницу, PDF или аннотацию статьи и выбираем фрагменты, где сказано о том же. Сайт закрыт от ботов — читаем его копию через Jina Reader или веб-архив, пейвол — честное «нет доступа».', out: 'Нет доступа', tone: 'grey' },
      { who: 'ai', title: 'Вердикт с цитатой', text: 'Нейросеть читает фрагменты и предлагает вердикт — обязательно с дословной цитатой из источника. Это предложение, а не приговор.' },
      { who: 'code', title: 'Право вето', text: 'Код ищет цитату в тексте источника и сравнивает числа. Цитаты нет дословно — вердикт выбрасывается; числа не сходятся — «источник говорит другое», даже если нейросеть сказала «подтверждено».', out: 'В тексте 40% → в источнике 60%', tone: 'orange' },
      { who: 'web', title: 'Если источника нет', text: 'Ищем в интернете и подтверждения, и опровержения. «Подтверждено» — только по официальному, научному или справочному сайту либо по двум независимым.' },
      { who: 'you', title: 'Решение за вами', text: 'Вердикт, объяснение, цитата и ссылка на экране — проверить нас можно за пять секунд. Отчёт отправляется ссылкой, для документа — ещё и PDF с QR-кодом.', out: 'Подтверждено цитатой', tone: 'green' },
    ],
  },
  numbers: {
    title: 'Проблема и результат', surveyTitle: 'Опрос студентов', surveySub: (n) => `${n} студентов, сентябрь 2026`,
    surveyRows: ['Используют ИИ для учёбы хотя бы раз в неделю', 'Воспользовались бы сервисом проверки', 'Знают случаи наказания за выдуманные источники', 'Просили у ИИ источники или статистику', 'Ни разу не проверяли ответ ИИ на выдумки', 'Всегда проверяют, что источник существует'],
    of: 'из', surveyNote: 'Источники у ИИ просят 49 из 56, но всегда проверяют их только 10. А о наказаниях за выдуманные ссылки знают 51.',
    benchTitle: 'Проверка на 72 размеченных ссылках', benchSub: 'Что Trustable? сказал о ссылках, которые команда разметила вручную',
    ok: 'Верно', skip: 'Не удалось проверить', bad: 'Ошибка', benchRows: ['Настоящие', 'Выдуманные', 'Искажённые'],
    benchNote: 'Ни один настоящий источник не назван выдуманным: две ошибки — настоящие ссылки, названные искажёнными. «Не удалось проверить» — база временно не ответила, и вместо догадки мы честно говорим «не знаем».',
    showTable: 'Показать таблицей', labelledAs: 'Размечено как',
  },
  audience: {
    title: 'Кому пригодится',
    rows: [
      { who: 'Студентам', text: 'Проверить реферат или курсовую до сдачи, а вместо выдуманной ссылки получить реальные работы по теме в формате ГОСТ или APA.', go: 'Проверить документ →', mode: 'file' },
      { who: 'Преподавателям', text: 'Загрузить работу и увидеть, сколько источников из списка литературы настоящие. PDF-отчёт с QR-кодом — к проверке.', go: 'Загрузить работу →', mode: 'file' },
      { who: 'Всем, кто читает', text: 'Проверить ответ нейросети, статью или пост перед тем, как поверить или поделиться.', go: 'Проверить текст →', mode: 'answer' },
    ],
  },
  cta: { title: 'Прежде чем поверить — проверьте.', text: 'Вставьте текст или загрузите документ. Утверждения подсветятся через несколько секунд, вердикты — по мере проверки.', button: 'Проверить текст' },
  faq: {
    title: 'Частые вопросы',
    items: [
      { q: 'Это ещё один ИИ-детектор?', a: 'Нет. Мы не угадываем, написан ли текст нейросетью. Мы проверяем, правда ли то, что в нём написано: существуют ли источники, говорят ли они то, что им приписали, и совпадают ли цифры.' },
      { q: 'Почему проверке можно доверять, если в ней тоже есть нейросеть?', a: 'Нейросеть разбирает текст и предлагает вердикт, но обязана подкрепить его дословной цитатой. Существует ли источник, решают реестры публикаций; есть ли цитата в источнике и совпадают ли числа — код, и он может отменить вердикт нейросети. А сама цитата всегда перед глазами — проверить нас можно за пять секунд.' },
      { q: 'Какие тексты можно проверить?', a: 'Лучше всего — ответы нейросетей со ссылками, а также статьи, новости, рефераты. Документы — .docx, .pdf, .txt, .md до 10 МБ: если в документе есть список литературы, проверим каждый источник из него; фактические утверждения из текста проверим в любом случае, а если источник закрыт — по открытым источникам в интернете. Мнения, личные данные и советы не проверяем.' },
      { q: 'Что значит «нет доступа»?', a: 'Источник закрыт пейволом или защитой от ботов, либо научная база временно не ответила. Такой источник мы не называем выдуманным: повторите проверку позже или откройте ссылку сами.' },
      { q: 'Что происходит с моим текстом?', a: 'Для разбора текст передаётся провайдеру языковой модели (Gemini или Groq), а поисковые запросы — поисковому сервису. Отчёт хранится на сервере, чтобы открываться по ссылке. Мы не публикуем тексты и сами не используем их для обучения.' },
    ],
  },
  report: {
    printBrand: 'Trustable? — проверка по источникам', printFile: 'Файл:', printDate: 'Дата проверки:', printReport: 'Отчёт:',
    printCaption: 'Отчёт можно проверить по ссылке', qrAlt: 'QR-код ссылки на отчёт',
    scoreTitle: 'Достоверность источников:', fabricated: 'Выдумано', distorted: 'искажено', unreachable: 'нет доступа',
    checkedOf: (a, b) => `проверено ${a} из ${b}`, tallyAria: 'Итоги по утверждениям',
    meta: (c, s, secs, cached) => `${c} утверждений, ${s} источников, ${secs} с${cached ? ' (сохранённая проверка)' : ''}`,
    share: 'Поделиться отчётом', copied: 'Ссылка скопирована', pdf: 'Скачать отчёт PDF', progress: (a, b) => `Проверено ${a} из ${b}`,
    bibTitle: 'Список литературы', bibCols: ['№', 'Ссылка в работе', 'Статус', 'Объяснение', 'Найденная работа'],
    checking: 'Проверяем', confirmedWork: 'Реальная работа, которая подтверждает это утверждение:', gost: 'ГОСТ', copiedShort: 'Скопировано',
    docTitle: 'Утверждения со ссылками в тексте работы', textTitle: 'Текст', hint: 'Нажмите на подсвеченное утверждение',
    more: 'Ещё утверждения', markedAria: 'Текст с разметкой',
    attackUnverified: 'Не подтверждено: доказательств не нашли', attackMode: 'Источник не указан — искали сами',
    inText: 'В тексте', inSource: 'В источнике', quoteVerified: 'Цитата найдена в тексте дословно',
    refutes: 'Опровергает', supports: 'Подтверждает', source: 'Источник', linkInText: 'Ссылка в тексте:',
    searched: (q, p) => `Что искали: запросов ${q}, прочитано страниц ${p}`, sites: 'Сайты:',
    assertive: (m) => `Это сказано уверенно${m}, но доказательств нет.`,
    emptyRunning: 'Результаты появятся здесь, как только первое утверждение будет проверено.',
    emptyIdle: 'Выберите утверждение слева, чтобы увидеть доказательства.',
    sourcesTitle: 'Источники из текста', open: 'Открыть:', how: 'Как проверено:', byAbstract: ', по аннотации', byFull: ', по полному тексту',
    searching: 'Ищем реальные работы по этой теме…', noRepl: 'Такой работы нет. Реальных работ по этой теме в OpenAlex не нашли.',
    replTitle: 'Такой работы нет. Реальные работы по этой теме:', replConfirmed: 'Аннотация подтверждает утверждение',
    replSimilar: 'Тема похожа, проверьте сами', copyGost: 'Скопировать ссылку в формате ГОСТ', copyApa: 'в формате APA',
    replCaption: 'Прежде чем ссылаться, откройте работу и убедитесь, что она подходит.',
    matrixTitle: 'Уверенный тон ≠ доказательства',
    matrixSub: 'Мы не угадываем «уверенность модели». Мы смотрим, насколько уверенно звучит фраза, и сравниваем с тем, что нашлось в источниках.',
    sure: 'Звучит уверенно', cautious: 'Звучит осторожно', dangerous: 'Уверенно, но без доказательств', safe: 'Уверенно и подтверждено',
    cautiousWeak: 'Осторожно и без доказательств', cautiousOk: 'Осторожно и подтверждено', notConfirmed: 'Не подтверждено', confirmedByQuote: 'Подтверждено цитатой',
  },
  modal: {
    title: 'Как мы проверяем', close: 'Закрыть',
    steps: [
      { b: 'Разбор.', t: 'Языковая модель делит текст на проверяемые утверждения и находит, на какой источник ссылается каждое. Ссылки, DOI и маркеры [n] код дополнительно находит сам.' },
      { b: 'Существование источника — без нейросети.', t: 'DOI проверяется в мировом реестре doi.org, научные работы — в Crossref и OpenAlex, ссылки — прямым запросом. Пейвол или защита от ботов — это «нет доступа», а не «фейк».' },
      { b: 'Чтение источника.', t: 'Скачиваем текст страницы, открытый PDF или аннотацию статьи; если сайт закрыт от ботов — читаем его копию через Jina Reader или веб-архив. Выбираем самые релевантные фрагменты (BM25 + числа).' },
      { b: 'Вердикт с цитатой.', t: 'Модель-судья предлагает вердикт и обязана привести дословную цитату. Код ищет её в тексте источника: не нашлась — вердикт отбрасывается. Так мы проверяем собственную нейросеть.' },
      { b: 'Цифры — детерминированно.', t: 'Числа из утверждения сравниваются с числами из источника без участия модели.' },
      { b: 'Нет источника — атакуем.', t: 'Ищем не только подтверждения, но и опровержения, и показываем найденное цитатами. «Подтверждено» — только если цитата с официального, научного или справочного сайта либо с двух независимых сайтов.' },
    ],
    note: 'Мы не ставим «процент доверия». Честное «не удалось проверить» лучше ложной уверенности.',
  },
  footer: {
    tagline: 'Проверка текстов по источникам: цитата вместо «доверьтесь нам».', product: 'Продукт', checkText: 'Проверить текст',
    checkDoc: 'Проверить документ', how: 'Как мы проверяем', dev: 'Разработчикам', support: 'Поддержка', bug: 'Сообщить об ошибке',
    motto: 'Вердикт — с доказательством. Последнее слово — за вами.',
  },
  verdict: {
    source_missing: { label: 'Источник не существует', short: 'Нет источника' },
    contradicted: { label: 'Источник говорит другое', short: 'Противоречит' },
    not_in_source: { label: 'В источнике этого нет', short: 'Нет в источнике' },
    unverifiable: { label: 'Не удалось проверить', short: 'Не подтверждено' },
    supported: { label: 'Подтверждено цитатой', short: 'Подтверждено' },
    pending: { label: 'Проверяем…', short: 'Проверяем' },
  },
  status: { exists: 'Существует', mismatch: 'Данные искажены', not_found: 'Не существует', unreachable: 'Нет доступа', unchecked: 'Не проверить' },
  tier: { official: 'официальный или научный источник', reference: 'справочник', media: 'СМИ', other: 'прочий сайт' },
  headline: headlineRu,
  recheck: { note: 'Пояснения ниже — на языке исходной проверки.', button: 'Перепроверить на русском' },
  msg: {
    tooShort: 'Вставьте текст целиком — хотя бы пару предложений.', format: 'Неподдерживаемый формат. Загрузите .docx, .pdf, .txt или .md.',
    tooBig: 'Файл больше 10 МБ.', reportMissing: 'Отчёт не найден: возможно, сервер перезапускался. Запустите проверку заново.',
    sending: 'Отправляю текст на проверку…', reading: (f) => `Читаю «${f}»…`,
    found: (c, s) => `Нашли ${c} утверждений и ${s} источников. Проверяем…`,
    bibProgress: (a, b) => `Список литературы: проверено ${a} из ${b}…`, server: (s) => `Ошибка сервера (${s})`,
    short422: 'Текст слишком короткий: вставьте его целиком.', sampleMissing: 'Пример не найден на сервере.',
  },
};

const en: Dict = {
  locale: 'en-GB', decimal: '.',
  nav: { newCheck: 'New check', how: 'How we check', toLight: 'Light theme', toDark: 'Dark theme', lang: 'Language' },
  hero: {
    kicker: 'Can you trust an AI answer?',
    lede: 'Paste an answer from ChatGPT, Gemini, Claude or any other AI. Trustable? splits it into claims, opens every source and shows what it actually says — as a verbatim quote.',
    points: ['Whether a source exists is checked by publication registries and the website itself — not by an AI', 'Numbers are compared by code', 'No source? We look for both confirmation and refutation'],
    cta: 'Check a text',
  },
  art: {
    p1: 'AI models regularly get references wrong:', m1: 'GPT-4 makes up 18% of its sources', p2: 'AI search engines',
    m2: 'are wrong in 40% of queries', p3: ', and in Kazakhstan', m3: '68% of students never check links (Akhmetova, 2024)',
    quoteOk: '✓ quote found verbatim', noDoi: 'The DOI is not registered at doi.org',
  },
  trust: { label: 'We check against', web: 'web search', primary: 'the original website', aria: 'Sources we check against' },
  check: {
    title: 'What are we checking?', tabText: 'Text', tabDoc: 'Document', dzTitle: 'Drop a document here', dzBusy: 'Uploading…',
    dzSub: 'coursework, article, essay, report, any document · .docx, .pdf, .txt, .md · up to 10 MB', dzPick: 'or choose a file',
    dzHint: 'We check every source in the reference list, the claims that cite them and the key uncited facts in the text.', sample: 'Try an example (DOCX)',
    textLabel: 'Text to check',
    placeholder: 'Paste any text: an AI answer, an article, a news story, a paragraph from an essay. If it has a list of sources, paste that too.',
    chars: 'characters', run: 'Check',
    wikiNotice: 'Web search is not connected: claims without sources are checked against Wikipedia only.',
    examples: 'Or try an example',
  },
  stairs: {
    title: 'The path of a single claim',
    sub: 'Every claim climbs this staircase. The AI appears on it twice: it parses the text and proposes a verdict with a quote. Everything else is registries and code — and the code has a veto.',
    who: { ai: 'AI', code: 'Code', registry: 'Registries', web: 'Web search', you: 'You' },
    steps: [
      { who: 'ai', title: 'Parsing', text: 'The AI splits the answer into separate claims and finds which source each one cites. The code also finds links and DOIs on its own.' },
      { who: 'registry', title: 'Does the source exist?', text: 'DOIs are checked against the global doi.org registry, papers are looked up in Crossref and OpenAlex, web links are opened directly. The AI plays no part in this.', out: 'The source does not exist', tone: 'red' },
      { who: 'code', title: 'Reading the source', text: 'We download the page, PDF or abstract and pick the passages about the same thing. Site blocks bots — we read a copy via Jina Reader or a web archive; paywall — an honest “no access”.', out: 'No access', tone: 'grey' },
      { who: 'ai', title: 'Verdict with a quote', text: 'The AI reads the passages and proposes a verdict — always with a verbatim quote from the source. It is a proposal, not a sentence.' },
      { who: 'code', title: 'The veto', text: 'Code looks for the quote in the source text and compares the numbers. No verbatim quote — the verdict is thrown out; numbers differ — “the source says otherwise”, even if the AI said “confirmed”.', out: 'Text 40% → source 60%', tone: 'orange' },
      { who: 'web', title: 'If there is no source', text: 'We search the web for both confirmation and refutation. “Confirmed” only on an official, scholarly or reference website, or on two independent ones.' },
      { who: 'you', title: 'You decide', text: 'The verdict, explanation, quote and link are on screen — you can check us in five seconds. Share the report as a link; documents also get a PDF with a QR code.', out: 'Confirmed by a quote', tone: 'green' },
    ],
  },
  numbers: {
    title: 'The problem and the result', surveyTitle: 'Student survey', surveySub: (n) => `${n} students, September 2026`,
    surveyRows: ['Use AI for studying at least weekly', 'Would use a checking service', 'Know of students penalised for fake sources', 'Have asked AI for sources or statistics', 'Have never checked an AI answer for fabrications', 'Always check that a source exists'],
    of: 'of', surveyNote: '49 of 56 ask AI for sources, but only 10 always check them. And 51 know of penalties for fake references.',
    benchTitle: 'Tested on 72 labelled references', benchSub: 'What Trustable? said about references our team labelled by hand',
    ok: 'Correct', skip: 'Could not check', bad: 'Error', benchRows: ['Real', 'Fabricated', 'Distorted'],
    benchNote: 'Not a single real source was called fake: the two errors are real references labelled as distorted. “Could not check” means a database did not respond — instead of guessing, we honestly say “we don’t know”.',
    showTable: 'Show as a table', labelledAs: 'Labelled as',
  },
  audience: {
    title: 'Who it is for',
    rows: [
      { who: 'Students', text: 'Check an essay or coursework before handing it in, and get real papers on the topic in GOST or APA style instead of a fabricated reference.', go: 'Check a document →', mode: 'file' },
      { who: 'Teachers', text: 'Upload a paper and see how many sources in its reference list are real. A PDF report with a QR code comes with it.', go: 'Upload a paper →', mode: 'file' },
      { who: 'Everyone who reads', text: 'Check an AI answer, an article or a post before believing or sharing it.', go: 'Check a text →', mode: 'answer' },
    ],
  },
  cta: { title: 'Before you believe it — check it.', text: 'Paste a text or upload a document. Claims are highlighted within seconds; verdicts arrive as the check runs.', button: 'Check a text' },
  faq: {
    title: 'FAQ',
    items: [
      { q: 'Is this another AI detector?', a: 'No. We do not guess whether a text was written by an AI. We check whether what it says is true: whether the sources exist, whether they say what is attributed to them, and whether the numbers match.' },
      { q: 'Why trust the check if it also uses an AI?', a: 'The AI parses the text and proposes a verdict, but must back it with a verbatim quote. Whether a source exists is decided by publication registries; whether the quote is in the source and the numbers match is decided by code, which can overrule the AI. And the quote is always on screen — you can check us in five seconds.' },
      { q: 'What texts can I check?', a: 'Best of all, AI answers with references, as well as articles, news and essays. Documents — .docx, .pdf, .txt, .md up to 10 MB: if a document has a reference list, we check every source in it; the factual claims in the text are checked either way, and if a source is closed — against open sources on the web. We do not check opinions, personal data or advice.' },
      { q: 'What does “no access” mean?', a: 'The source is behind a paywall or bot protection, or a scholarly database did not respond. We do not call such a source fake: retry later or open the link yourself.' },
      { q: 'What happens to my text?', a: 'For parsing, the text is sent to the language-model provider (Gemini or Groq), and search queries go to the search service. The report is stored on the server so it opens by link. We do not publish texts and do not use them for training ourselves.' },
    ],
  },
  report: {
    printBrand: 'Trustable? — source-based checking', printFile: 'File:', printDate: 'Checked on:', printReport: 'Report:',
    printCaption: 'The report can be verified at the link', qrAlt: 'QR code linking to the report',
    scoreTitle: 'Source reliability:', fabricated: 'Fabricated', distorted: 'distorted', unreachable: 'no access',
    checkedOf: (a, b) => `${a} of ${b} checked`, tallyAria: 'Claim results',
    meta: (c, s, secs, cached) => `${c} claims, ${s} sources, ${secs} s${cached ? ' (saved check)' : ''}`,
    share: 'Share the report', copied: 'Link copied', pdf: 'Download PDF report', progress: (a, b) => `${a} of ${b} checked`,
    bibTitle: 'Reference list', bibCols: ['#', 'Reference in the paper', 'Status', 'Explanation', 'Work found'],
    checking: 'Checking', confirmedWork: 'A real paper that supports this claim:', gost: 'GOST', copiedShort: 'Copied',
    docTitle: 'Claims with references in the paper', textTitle: 'Text', hint: 'Click a highlighted claim',
    more: 'More claims', markedAria: 'Annotated text',
    attackUnverified: 'Not confirmed: no evidence found', attackMode: 'No source given — we searched ourselves',
    inText: 'In the text', inSource: 'In the source', quoteVerified: 'Quote found verbatim in the text',
    refutes: 'Refutes', supports: 'Supports', source: 'Source', linkInText: 'Reference in the text:',
    searched: (q, p) => `What we searched: ${q} queries, ${p} pages read`, sites: 'Websites:',
    assertive: (m) => `This is stated confidently${m}, but there is no evidence.`,
    emptyRunning: 'Results will appear here as soon as the first claim is checked.',
    emptyIdle: 'Select a claim on the left to see the evidence.',
    sourcesTitle: 'Sources in the text', open: 'Open:', how: 'How it was checked:', byAbstract: ', by abstract', byFull: ', by full text',
    searching: 'Looking for real papers on this topic…', noRepl: 'This work does not exist. No real papers on the topic were found in OpenAlex.',
    replTitle: 'This work does not exist. Real papers on the topic:', replConfirmed: 'The abstract supports the claim',
    replSimilar: 'Similar topic — check it yourself', copyGost: 'Copy reference in GOST style', copyApa: 'in APA style',
    replCaption: 'Before citing, open the paper and make sure it fits.',
    matrixTitle: 'Confident tone ≠ evidence',
    matrixSub: 'We do not guess the “model’s confidence”. We look at how confident a sentence sounds and compare it with what was found in the sources.',
    sure: 'Sounds confident', cautious: 'Sounds cautious', dangerous: 'Confident, no evidence', safe: 'Confident and confirmed',
    cautiousWeak: 'Cautious, no evidence', cautiousOk: 'Cautious and confirmed', notConfirmed: 'Not confirmed', confirmedByQuote: 'Confirmed by a quote',
  },
  modal: {
    title: 'How we check', close: 'Close',
    steps: [
      { b: 'Parsing.', t: 'A language model splits the text into checkable claims and finds which source each one cites. Code also finds links, DOIs and [n] markers on its own.' },
      { b: 'Whether a source exists — without AI.', t: 'DOIs are checked in the global doi.org registry, papers in Crossref and OpenAlex, links by a direct request. A paywall or bot protection means “no access”, not “fake”.' },
      { b: 'Reading the source.', t: 'We download the page text, open-access PDF or abstract; if a site blocks bots, we read its copy via Jina Reader or a web archive. We pick the most relevant passages (BM25 + numbers).' },
      { b: 'Verdict with a quote.', t: 'The judge model proposes a verdict and must give a verbatim quote. Code looks for it in the source text: not found — the verdict is discarded. This is how we check our own AI.' },
      { b: 'Numbers — deterministically.', t: 'Numbers in the claim are compared with numbers in the source without the model.' },
      { b: 'No source — we attack.', t: 'We look not only for confirmation but also for refutation, and show what we found as quotes. “Confirmed” only with a quote from an official, scholarly or reference website, or from two independent websites.' },
    ],
    note: 'We do not give a “trust percentage”. An honest “could not check” beats false confidence.',
  },
  footer: {
    tagline: 'Checking texts against sources: a quote instead of “trust us”.', product: 'Product', checkText: 'Check a text',
    checkDoc: 'Check a document', how: 'How we check', dev: 'Developers', support: 'Support', bug: 'Report a bug',
    motto: 'Every verdict comes with evidence. The last word is yours.',
  },
  verdict: {
    source_missing: { label: 'The source does not exist', short: 'No source' },
    contradicted: { label: 'The source says otherwise', short: 'Contradicts' },
    not_in_source: { label: 'Not in the source', short: 'Not in source' },
    unverifiable: { label: 'Could not check', short: 'Not confirmed' },
    supported: { label: 'Confirmed by a quote', short: 'Confirmed' },
    pending: { label: 'Checking…', short: 'Checking' },
  },
  status: { exists: 'Exists', mismatch: 'Details distorted', not_found: 'Does not exist', unreachable: 'No access', unchecked: 'Cannot check' },
  tier: { official: 'official or scholarly source', reference: 'reference work', media: 'news media', other: 'other website' },
  headline: headlineEn,
  recheck: { note: 'The explanations below are in the language of the original check.', button: 'Re-check in English' },
  msg: {
    tooShort: 'Paste the whole text — at least a couple of sentences.', format: 'Unsupported format. Upload a .docx, .pdf, .txt or .md file.',
    tooBig: 'The file is larger than 10 MB.', reportMissing: 'Report not found: the server may have restarted. Run the check again.',
    sending: 'Sending the text for checking…', reading: (f) => `Reading “${f}”…`,
    found: (c, s) => `Found ${c} claims and ${s} sources. Checking…`,
    bibProgress: (a, b) => `Reference list: ${a} of ${b} checked…`, server: (s) => `Server error (${s})`,
    short422: 'The text is too short: paste all of it.', sampleMissing: 'Example not found on the server.',
  },
};

const kk: Dict = {
  locale: 'kk-KZ', decimal: ',',
  nav: { newCheck: 'Жаңа тексеру', how: 'Қалай тексереміз', toLight: 'Жарық тақырып', toDark: 'Қараңғы тақырып', lang: 'Тіл' },
  hero: {
    kicker: 'ЖИ жауабына сенуге бола ма?',
    lede: 'ChatGPT, Gemini, Claude немесе кез келген басқа нейрожелінің жауабын қойыңыз. Trustable? оны тұжырымдарға бөліп, әр дереккөзді ашады және онда шын мәнінде не жазылғанын сөзбе-сөз дәйексөзбен көрсетеді.',
    points: ['Дереккөздің бар-жоғын нейрожелі емес, басылымдар тізілімдері мен сайттың өзі тексереді', 'Сандарды код салыстырады', 'Дереккөз жоқ па? Растауды да, теріске шығаруды да іздейміз'],
    cta: 'Мәтінді тексеру',
  },
  art: {
    p1: 'Нейрожелілер сілтемелерде жиі қателеседі:', m1: 'GPT-4 дереккөздердің 18%-ын ойдан шығарады', p2: 'ЖИ іздеу жүйелері',
    m2: 'сұраулардың 40%-ында қателеседі', p3: ', ал Қазақстанда', m3: 'студенттердің 68%-ы сілтемелерді тексермейді (Ахметова, 2024)',
    quoteOk: '✓ дәйексөз сөзбе-сөз табылды', noDoi: 'DOI doi.org тізілімінде тіркелмеген',
  },
  trust: { label: 'Тексеретін дереккөздер', web: 'веб-іздеу', primary: 'бастапқы дереккөз сайты', aria: 'Тексеру дереккөздері' },
  check: {
    title: 'Нені тексереміз?', tabText: 'Мәтін', tabDoc: 'Құжат', dzTitle: 'Құжатты осында сүйреп әкеліңіз', dzBusy: 'Жүктеліп жатыр…',
    dzSub: 'курстық жұмыс, мақала, эссе, есеп, кез келген құжат · .docx, .pdf, .txt, .md · 10 МБ-қа дейін', dzPick: 'немесе файлды таңдаңыз',
    dzHint: 'Әдебиеттер тізіміндегі әр дереккөзді, сілтемесі бар тұжырымдарды және мәтіндегі сілтемесіз негізгі фактілерді тексереміз.', sample: 'Мысалмен көру (DOCX)',
    textLabel: 'Тексерілетін мәтін',
    placeholder: 'Кез келген мәтінді қойыңыз: нейрожелі жауабы, мақала, жаңалық, рефераттан үзінді. Мәтіннің дереккөздер тізімі болса, оны да қойыңыз.',
    chars: 'таңба', run: 'Тексеру',
    wikiNotice: 'Веб-іздеу қосылмаған: дереккөзсіз тұжырымдар тек Уикипедия бойынша тексеріледі.',
    examples: 'Немесе мысалдарды қараңыз',
  },
  stairs: {
    title: 'Бір тұжырымның жолы',
    sub: 'Әр тұжырым осы баспалдақпен көтеріледі. Нейрожелі онда екі рет кездеседі: мәтінді талдайды және дәйексөзбен қорытынды ұсынады. Қалғанының бәрі — тізілімдер мен код, ал кодта вето құқығы бар.',
    who: { ai: 'Нейрожелі', code: 'Код', registry: 'Тізілімдер', web: 'Веб-іздеу', you: 'Сіз' },
    steps: [
      { who: 'ai', title: 'Талдау', text: 'Нейрожелі жауапты жеке тұжырымдарға бөліп, әрқайсысы қай дереккөзге сілтейтінін табады. Сілтемелер мен DOI-ды код та өз бетінше табады.' },
      { who: 'registry', title: 'Дереккөз бар ма', text: 'DOI әлемдік doi.org тізілімімен салыстырылады, мақалалар Crossref пен OpenAlex-тен ізделеді, веб-сілтемелер тікелей ашылады. Бұған нейрожелі қатыспайды.', out: 'Дереккөз жоқ', tone: 'red' },
      { who: 'code', title: 'Дереккөзді оқу', text: 'Бетті, PDF-ті немесе мақала аннотациясын жүктеп, сол туралы айтылған үзінділерді таңдаймыз. Сайт боттарды кіргізбесе — көшірмесін Jina Reader немесе веб-мұрағат арқылы оқимыз, ақылы болса — адал «қолжетімсіз».', out: 'Қолжетімсіз', tone: 'grey' },
      { who: 'ai', title: 'Дәйексөзбен қорытынды', text: 'Нейрожелі үзінділерді оқып, қорытынды ұсынады — міндетті түрде дереккөзден сөзбе-сөз дәйексөзбен. Бұл үкім емес, ұсыныс.' },
      { who: 'code', title: 'Вето құқығы', text: 'Код дәйексөзді дереккөз мәтінінен іздейді және сандарды салыстырады. Дәйексөз сөзбе-сөз жоқ болса — қорытынды алынып тасталады; сандар сәйкес келмесе — нейрожелі «расталды» десе де, «дереккөз басқаша айтады».', out: 'Мәтінде 40% → дереккөзде 60%', tone: 'orange' },
      { who: 'web', title: 'Дереккөз жоқ болса', text: 'Интернеттен растауды да, теріске шығаруды да іздейміз. «Расталды» — тек ресми, ғылыми немесе анықтамалық сайт бойынша не екі тәуелсіз сайт бойынша.' },
      { who: 'you', title: 'Шешім сізде', text: 'Қорытынды, түсіндірме, дәйексөз және сілтеме экранда — бізді бес секундта тексере аласыз. Есеп сілтемемен жіберіледі, құжат үшін — QR-коды бар PDF те бар.', out: 'Дәйексөзбен расталды', tone: 'green' },
    ],
  },
  numbers: {
    title: 'Мәселе мен нәтиже', surveyTitle: 'Студенттер сауалнамасы', surveySub: (n) => `${n} студент, 2026 жылғы қыркүйек`,
    surveyRows: ['Оқу үшін ЖИ-ды аптасына кемінде бір рет қолданады', 'Тексеру сервисін пайдаланар еді', 'Ойдан шығарылған дереккөздер үшін жазаланған жағдайларды біледі', 'ЖИ-дан дереккөз немесе статистика сұраған', 'ЖИ жауабын ойдан шығарылғанға бір рет те тексермеген', 'Дереккөздің бар-жоғын әрдайым тексереді'],
    of: '/', surveyNote: '56 студенттің 49-ы ЖИ-дан дереккөз сұрайды, бірақ тек 10-ы оларды әрдайым тексереді. Ал ойдан шығарылған сілтемелер үшін жазалау жағдайларын 51-і біледі.',
    benchTitle: '72 белгіленген сілтемедегі тексеру', benchSub: 'Команда қолмен белгілеген сілтемелер туралы Trustable? не айтты',
    ok: 'Дұрыс', skip: 'Тексеру мүмкін болмады', bad: 'Қате', benchRows: ['Нақты', 'Ойдан шығарылған', 'Бұрмаланған'],
    benchNote: 'Бірде-бір нақты дереккөз жалған деп аталмады: екі қате — бұрмаланған деп аталған нақты сілтемелер. «Тексеру мүмкін болмады» — база уақытша жауап бермеді, біз болжаудың орнына адал түрде «білмейміз» дейміз.',
    showTable: 'Кесте түрінде көрсету', labelledAs: 'Белгіленгені',
  },
  audience: {
    title: 'Кімге пайдалы',
    rows: [
      { who: 'Студенттерге', text: 'Реферат немесе курстық жұмысты тапсырмас бұрын тексеру, ал ойдан шығарылған сілтеменің орнына тақырып бойынша нақты жұмыстарды МЕМСТ немесе APA форматында алу.', go: 'Құжатты тексеру →', mode: 'file' },
      { who: 'Оқытушыларға', text: 'Жұмысты жүктеп, әдебиеттер тізіміндегі қанша дереккөздің нақты екенін көру. QR-коды бар PDF-есеп — тексеруге.', go: 'Жұмысты жүктеу →', mode: 'file' },
      { who: 'Барлық оқырмандарға', text: 'Нейрожелі жауабын, мақаланы немесе жазбаны сенбес не бөліспес бұрын тексеру.', go: 'Мәтінді тексеру →', mode: 'answer' },
    ],
  },
  cta: { title: 'Сенбес бұрын — тексеріңіз.', text: 'Мәтінді қойыңыз немесе құжатты жүктеңіз. Тұжырымдар бірнеше секундта белгіленеді, қорытындылар тексеру барысында шығады.', button: 'Мәтінді тексеру' },
  faq: {
    title: 'Жиі қойылатын сұрақтар',
    items: [
      { q: 'Бұл тағы бір ЖИ-детектор ма?', a: 'Жоқ. Біз мәтінді нейрожелі жазғанын болжамаймыз. Онда жазылғанның шындығын тексереміз: дереккөздер бар ма, оларға телінген нәрсені айта ма және сандар сәйкес келе ме.' },
      { q: 'Тексеруде де нейрожелі болса, неге оған сенуге болады?', a: 'Нейрожелі мәтінді талдап, қорытынды ұсынады, бірақ оны сөзбе-сөз дәйексөзбен дәлелдеуге міндетті. Дереккөздің бар-жоғын басылымдар тізілімдері шешеді; дәйексөздің дереккөзде бар-жоғын және сандардың сәйкестігін код шешеді, ол нейрожелінің қорытындысын жоя алады. Ал дәйексөздің өзі әрдайым көз алдыңызда — бізді бес секундта тексере аласыз.' },
      { q: 'Қандай мәтіндерді тексеруге болады?', a: 'Ең жақсысы — сілтемелері бар нейрожелі жауаптары, сондай-ақ мақалалар, жаңалықтар, рефераттар. Құжаттар — .docx, .pdf, .txt, .md, 10 МБ-қа дейін: құжатта әдебиеттер тізімі болса, ондағы әр дереккөзді тексереміз; мәтіндегі фактілік тұжырымдарды кез келген жағдайда тексереміз, ал дереккөз жабық болса — интернеттегі ашық дереккөздер бойынша. Пікірлерді, жеке деректерді және кеңестерді тексермейміз.' },
      { q: '«Қолжетімсіз» нені білдіреді?', a: 'Дереккөз ақылы немесе боттардан қорғалған, не ғылыми база уақытша жауап бермеді. Мұндай дереккөзді жалған деп атамаймыз: кейінірек қайта тексеріңіз немесе сілтемені өзіңіз ашыңыз.' },
      { q: 'Менің мәтінім не болады?', a: 'Талдау үшін мәтін тілдік модель провайдеріне (Gemini немесе Groq), ал іздеу сұраулары іздеу сервисіне жіберіледі. Есеп сілтеме арқылы ашылуы үшін серверде сақталады. Біз мәтіндерді жарияламаймыз және оларды өзіміз оқыту үшін қолданбаймыз.' },
    ],
  },
  report: {
    printBrand: 'Trustable? — дереккөздер бойынша тексеру', printFile: 'Файл:', printDate: 'Тексерілген күні:', printReport: 'Есеп:',
    printCaption: 'Есепті сілтеме арқылы тексеруге болады', qrAlt: 'Есепке сілтеменің QR-коды',
    scoreTitle: 'Дереккөздердің сенімділігі:', fabricated: 'Ойдан шығарылған', distorted: 'бұрмаланған', unreachable: 'қолжетімсіз',
    checkedOf: (a, b) => `тексерілді: ${a} / ${b}`, tallyAria: 'Тұжырымдар бойынша қорытынды',
    meta: (c, s, secs, cached) => `тұжырым: ${c}, дереккөз: ${s}, ${secs} с${cached ? ' (сақталған тексеру)' : ''}`,
    share: 'Есеппен бөлісу', copied: 'Сілтеме көшірілді', pdf: 'PDF есепті жүктеу', progress: (a, b) => `Тексерілді: ${a} / ${b}`,
    bibTitle: 'Әдебиеттер тізімі', bibCols: ['№', 'Жұмыстағы сілтеме', 'Мәртебе', 'Түсіндірме', 'Табылған жұмыс'],
    checking: 'Тексерілуде', confirmedWork: 'Бұл тұжырымды растайтын нақты жұмыс:', gost: 'МЕМСТ', copiedShort: 'Көшірілді',
    docTitle: 'Жұмыс мәтініндегі сілтемелері бар тұжырымдар', textTitle: 'Мәтін', hint: 'Белгіленген тұжырымды басыңыз',
    more: 'Басқа тұжырымдар', markedAria: 'Белгіленген мәтін',
    attackUnverified: 'Расталмады: дәлел табылмады', attackMode: 'Дереккөз көрсетілмеген — өзіміз іздедік',
    inText: 'Мәтінде', inSource: 'Дереккөзде', quoteVerified: 'Дәйексөз мәтіннен сөзбе-сөз табылды',
    refutes: 'Теріске шығарады', supports: 'Растайды', source: 'Дереккөз', linkInText: 'Мәтіндегі сілтеме:',
    searched: (q, p) => `Не іздедік: сұраулар — ${q}, оқылған беттер — ${p}`, sites: 'Сайттар:',
    assertive: (m) => `Бұл сенімді айтылған${m}, бірақ дәлел жоқ.`,
    emptyRunning: 'Алғашқы тұжырым тексерілген бойда нәтижелер осында шығады.',
    emptyIdle: 'Дәлелдерді көру үшін сол жақтан тұжырымды таңдаңыз.',
    sourcesTitle: 'Мәтіндегі дереккөздер', open: 'Ашу:', how: 'Қалай тексерілді:', byAbstract: ', аннотация бойынша', byFull: ', толық мәтін бойынша',
    searching: 'Осы тақырып бойынша нақты жұмыстарды іздеп жатырмыз…', noRepl: 'Мұндай жұмыс жоқ. OpenAlex-тен осы тақырып бойынша нақты жұмыстар табылмады.',
    replTitle: 'Мұндай жұмыс жоқ. Осы тақырып бойынша нақты жұмыстар:', replConfirmed: 'Аннотация тұжырымды растайды',
    replSimilar: 'Тақырыбы ұқсас, өзіңіз тексеріңіз', copyGost: 'Сілтемені МЕМСТ форматында көшіру', copyApa: 'APA форматында',
    replCaption: 'Сілтеме жасамас бұрын жұмысты ашып, оның сәйкес келетініне көз жеткізіңіз.',
    matrixTitle: 'Сенімді үн ≠ дәлел',
    matrixSub: 'Біз «модельдің сенімділігін» болжамаймыз. Сөйлемнің қаншалықты сенімді естілетінін қарап, дереккөздерден табылғанмен салыстырамыз.',
    sure: 'Сенімді естіледі', cautious: 'Сақ естіледі', dangerous: 'Сенімді, бірақ дәлелсіз', safe: 'Сенімді және расталған',
    cautiousWeak: 'Сақ және дәлелсіз', cautiousOk: 'Сақ және расталған', notConfirmed: 'Расталмаған', confirmedByQuote: 'Дәйексөзбен расталған',
  },
  modal: {
    title: 'Қалай тексереміз', close: 'Жабу',
    steps: [
      { b: 'Талдау.', t: 'Тілдік модель мәтінді тексерілетін тұжырымдарға бөліп, әрқайсысы қай дереккөзге сілтейтінін табады. Сілтемелерді, DOI мен [n] белгілерін код та өз бетінше табады.' },
      { b: 'Дереккөздің бар-жоғы — нейрожелісіз.', t: 'DOI әлемдік doi.org тізілімінде, ғылыми жұмыстар Crossref пен OpenAlex-те, сілтемелер тікелей сұраумен тексеріледі. Ақылы қолжетімділік немесе боттардан қорғаныс — «қолжетімсіз», «жалған» емес.' },
      { b: 'Дереккөзді оқу.', t: 'Бет мәтінін, ашық PDF-ті немесе мақала аннотациясын жүктейміз; сайт боттарды кіргізбесе — көшірмесін Jina Reader немесе веб-мұрағат арқылы оқимыз. Ең өзекті үзінділерді таңдаймыз (BM25 + сандар).' },
      { b: 'Дәйексөзбен қорытынды.', t: 'Төреші модель қорытынды ұсынады және сөзбе-сөз дәйексөз келтіруге міндетті. Код оны дереккөз мәтінінен іздейді: табылмаса — қорытынды алынып тасталады. Өз нейрожелімізді осылай тексереміз.' },
      { b: 'Сандар — детерминирленген түрде.', t: 'Тұжырымдағы сандар дереккөздегі сандармен модельсіз салыстырылады.' },
      { b: 'Дереккөз жоқ — шабуылдаймыз.', t: 'Растауды ғана емес, теріске шығаруды да іздеп, табылғанын дәйексөздермен көрсетеміз. «Расталды» — тек ресми, ғылыми немесе анықтамалық сайттан не екі тәуелсіз сайттан дәйексөз болса.' },
    ],
    note: 'Біз «сенім пайызын» қоймаймыз. Адал «тексеру мүмкін болмады» жалған сенімділіктен жақсы.',
  },
  footer: {
    tagline: 'Мәтіндерді дереккөздер бойынша тексеру: «бізге сеніңіз» орнына — дәйексөз.', product: 'Өнім', checkText: 'Мәтінді тексеру',
    checkDoc: 'Құжатты тексеру', how: 'Қалай тексереміз', dev: 'Әзірлеушілерге', support: 'Қолдау', bug: 'Қате туралы хабарлау',
    motto: 'Қорытынды — дәлелмен. Соңғы сөз — сізде.',
  },
  verdict: {
    source_missing: { label: 'Дереккөз жоқ', short: 'Дереккөз жоқ' },
    contradicted: { label: 'Дереккөз басқаша айтады', short: 'Қайшы' },
    not_in_source: { label: 'Дереккөзде бұл жоқ', short: 'Дереккөзде жоқ' },
    unverifiable: { label: 'Тексеру мүмкін болмады', short: 'Расталмады' },
    supported: { label: 'Дәйексөзбен расталды', short: 'Расталды' },
    pending: { label: 'Тексерілуде…', short: 'Тексерілуде' },
  },
  status: { exists: 'Бар', mismatch: 'Деректер бұрмаланған', not_found: 'Жоқ', unreachable: 'Қолжетімсіз', unchecked: 'Тексеру мүмкін емес' },
  tier: { official: 'ресми немесе ғылыми дереккөз', reference: 'анықтамалық', media: 'БАҚ', other: 'басқа сайт' },
  headline: headlineKk,
  recheck: { note: 'Төмендегі түсіндірмелер бастапқы тексеру тілінде.', button: 'Қазақ тілінде қайта тексеру' },
  msg: {
    tooShort: 'Мәтінді толығымен қойыңыз — кемінде екі-үш сөйлем.', format: 'Қолдау көрсетілмейтін формат. .docx, .pdf, .txt немесе .md файлын жүктеңіз.',
    tooBig: 'Файл 10 МБ-тан үлкен.', reportMissing: 'Есеп табылмады: сервер қайта іске қосылған болуы мүмкін. Тексеруді қайта бастаңыз.',
    sending: 'Мәтін тексеруге жіберілуде…', reading: (f) => `«${f}» оқылуда…`,
    found: (c, s) => `Табылды: ${c} тұжырым, ${s} дереккөз. Тексеріп жатырмыз…`,
    bibProgress: (a, b) => `Әдебиеттер тізімі: тексерілді ${a} / ${b}…`, server: (s) => `Сервер қатесі (${s})`,
    short422: 'Мәтін тым қысқа: толығымен қойыңыз.', sampleMissing: 'Мысал серверден табылмады.',
  },
};

export const DICTS: Record<Lang, Dict> = { ru, en, kk };

export function detectLang(): Lang {
  const q = new URLSearchParams(location.search).get('lang');
  if (q === 'ru' || q === 'en' || q === 'kk') return q;
  try {
    const saved = localStorage.getItem('trustable.lang');
    if (saved === 'ru' || saved === 'en' || saved === 'kk') return saved;
  } catch { /* storage unavailable */ }
  const nav = (navigator.language || 'ru').slice(0, 2).toLowerCase();
  return nav === 'kk' ? 'kk' : nav === 'en' ? 'en' : 'ru';
}
