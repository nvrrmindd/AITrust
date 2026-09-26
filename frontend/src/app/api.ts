import { Injectable } from '@angular/core';
import { Example, PipelineEvent } from './models';

@Injectable({ providedIn: 'root' })
export class Api {
  private base = '';

  async examples(): Promise<Example[]> {
    const r = await fetch(`${this.base}/api/examples`);
    return r.ok ? r.json() : [];
  }

  async health(): Promise<{ ok: boolean; llm_configured: boolean; llm: string; search: string } | null> {
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
      body: JSON.stringify({ text }),
    });
    if (!r.ok) {
      let msg = `Ошибка сервера (${r.status})`;
      try {
        const body = await r.json();
        if (typeof body.detail === 'string') msg = body.detail;
        else if (r.status === 422) msg = 'Текст слишком короткий: вставьте ответ ИИ целиком.';
      } catch { /* keep default */ }
      throw new Error(msg);
    }
    return r.json();
  }

  /** «Работа целиком»: upload a .docx / .pdf / .txt / .md paper. */
  async checkFile(file: File): Promise<{ id: string; cached: boolean; filename: string }> {
    const form = new FormData();
    form.append('file', file, file.name);
    const r = await fetch(`${this.base}/api/check-file`, { method: 'POST', body: form });
    if (!r.ok) {
      let msg = `Ошибка сервера (${r.status})`;
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
    if (!r.ok) throw new Error('Пример курсовой не найден на сервере.');
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

  async report(id: string): Promise<{ id: string; text: string; events: PipelineEvent[]; filename?: string | null } | null> {
    const r = await fetch(`${this.base}/api/reports/${encodeURIComponent(id)}`);
    return r.ok ? r.json() : null;
  }
}
