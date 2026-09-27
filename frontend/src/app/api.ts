import { Injectable } from '@angular/core';
import { Example, PipelineEvent } from './models';

@Injectable({ providedIn: 'root' })
export class Api {
  private base = '';
  lang: 'ru' | 'en' | 'kk' = 'ru';
  private readonly MSG = {
    ru: { server: 'Ошибка сервера', short: 'Текст слишком короткий: вставьте его целиком.', sample: 'Пример не найден на сервере.' },
    en: { server: 'Server error', short: 'The text is too short: paste all of it.', sample: 'Example not found on the server.' },
    kk: { server: 'Сервер қатесі', short: 'Мәтін тым қысқа: толығымен қойыңыз.', sample: 'Мысал серверден табылмады.' },
  };

  async examples(): Promise<Example[]> {
    const r = await fetch(`${this.base}/api/examples`);
    return r.ok ? r.json() : [];
  }

  async health(): Promise<{ ok: boolean; llm_configured: boolean; llm: string; search: string; support_email?: string | null } | null> {
    try {
      const r = await fetch(`${this.base}/api/health`);
      return r.ok ? r.json() : null;
    } catch {
      return null;
    }
  }

  async start(text: string): Promise<{ id: string; cached: boolean }> {
    const r = await fetch(`${this.base}/api/check`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, lang: this.lang }),
    });
    if (!r.ok) {
      let msg = `${this.MSG[this.lang].server} (${r.status})`;
      try {
        const body = await r.json();
        if (typeof body.detail === 'string') msg = body.detail;
        else if (r.status === 422) msg = this.MSG[this.lang].short;
      } catch { /* keep default */ }
      throw new Error(msg);
    }
    return r.json();
  }

  /** «Работа целиком»: upload a .docx / .pdf / .txt / .md paper. */
  async checkFile(file: File): Promise<{ id: string; cached: boolean; filename: string }> {
    const form = new FormData();
    form.append('file', file, file.name);
    form.append('lang', this.lang);
    const r = await fetch(`${this.base}/api/check-file`, { method: 'POST', body: form });
    if (!r.ok) {
      let msg = `${this.MSG[this.lang].server} (${r.status})`;
      try {
        const body = await r.json();
        if (typeof body.detail === 'string') msg = body.detail;
      } catch { /* keep default */ }
      throw new Error(msg);
    }
    return r.json();
  }

  async sampleDocx(): Promise<File> {
    const r = await fetch(`${this.base}/api/sample-docx`);
    if (!r.ok) throw new Error(this.MSG[this.lang].sample);
    return new File([await r.blob()], 'sample_coursework.docx', {
      type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    });
  }

  /** Server-Sent Events; returns a function that closes the stream. */
  stream(id: string, onEvent: (e: PipelineEvent) => void, onEnd: () => void): () => void {
    const es = new EventSource(`${this.base}/api/check/${encodeURIComponent(id)}/events`);
    es.onmessage = (m) => onEvent(JSON.parse(m.data));
    es.addEventListener('end', () => { es.close(); onEnd(); });
    es.onerror = () => { es.close(); onEnd(); };
    return () => es.close();
  }

  async report(id: string): Promise<{ id: string; text: string; events: PipelineEvent[]; filename?: string | null; lang?: string } | null> {
    const r = await fetch(`${this.base}/api/reports/${encodeURIComponent(id)}`);
    return r.ok ? r.json() : null;
  }
}
