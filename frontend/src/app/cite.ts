// Reference formatting for suggested replacement works (GOST R 7.0.100-2018 and APA 7), done on the client.
import type { Replacement } from './models';

interface Name { family: string; initials: string[]; }

const CYR = /[а-яё]/i;

/** OpenAlex display names: "Anna Petrova", "В.И. Казаренков", "Petrova, Anna". */
export function parseName(display: string): Name {
  const s = display.trim();
  if (s.includes(',')) {
    const [family, given] = s.split(',', 2);
    return { family: family.trim(), initials: initialsOf(given) };
  }
  const parts = s.replace(/\./g, '. ').split(/\s+/).filter(Boolean);
  const family = parts.pop() ?? '';
  return { family, initials: initialsOf(parts.join(' ')) };
}

function initialsOf(given: string): string[] {
  return given.split(/[\s.]+/).filter(Boolean).map((p) =>
    p.split('-').map((h) => h.charAt(0).toUpperCase() + '.').join('-'));
}

const stripDot = (s: string) => s.trim().replace(/\.+$/, '');
const sentence = (s: string) => (/[?!]$/.test(stripDot(s)) ? stripDot(s) : `${stripDot(s)}.`);

// ---------------------------------------------------------------- GOST

export function gost(r: Replacement): string {
  const ru = CYR.test(r.title + (r.venue ?? ''));
  const names = r.authors.map(parseName);
  const short = (n: Name) => `${n.initials.join(' ')} ${n.family}`.trim();
  const shown = names.slice(0, 3).map(short).join(', ') + (names.length > 3 ? (ru ? ' [и др.]' : ' [et al.]') : '');
  const first = names[0];
  const head = first && names.length <= 3 ? (first.initials.length ? `${first.family}, ${first.initials.join(' ')} ` : `${first.family}. `) : '';
  let out = `${head}${stripDot(r.title)}`;
  if (names.length) out += ` / ${shown}`;
  if (r.venue) out += ` // ${stripDot(r.venue)}`;
  const parts: string[] = [];
  if (r.year) parts.push(String(r.year));
  const vol = [r.volume ? `${ru ? 'Т.' : 'Vol.'} ${r.volume}` : '', r.issue ? `${ru ? '№' : 'No.'} ${r.issue}` : '']
    .filter(Boolean).join(', ');
  if (vol) parts.push(vol);
  if (r.pages) parts.push(`${ru ? 'С.' : 'P.'} ${r.pages}`);
  if (r.doi) parts.push(`DOI ${r.doi}`);
  return (parts.length ? `${out}. – ${parts.join('. – ')}` : out) + '.';
}

// ---------------------------------------------------------------- APA 7

export function apa(r: Replacement): string {
  const names = r.authors.map(parseName).map((n) => `${n.family}, ${n.initials.join(' ')}`.replace(/, $/, ''));
  let who = '';
  if (names.length === 1) who = names[0];
  else if (names.length === 2) who = `${names[0]}, & ${names[1]}`;
  else if (names.length <= 20) who = `${names.slice(0, -1).join(', ')}, & ${names[names.length - 1]}`;
  else who = `${names.slice(0, 19).join(', ')}, . . . ${names[names.length - 1]}`;
  const year = `(${r.year ?? 'n.d.'}).`;
  let out = who ? `${who} ${year} ${sentence(r.title)}` : `${sentence(r.title)} ${year}`;
  if (r.venue) {
    out += ` ${stripDot(r.venue)}`;
    if (r.volume) out += `, ${r.volume}${r.issue ? `(${r.issue})` : ''}`;
    if (r.pages) out += `, ${r.pages}`;
    out += '.';
  }
  if (r.doi) out += ` https://doi.org/${r.doi}`;
  return out;
}
