import { Injectable } from '@angular/core';
import { Example, PipelineEvent } from './models';

@Injectable({ providedIn: 'root' })
export class Api {
  private base = '';

  async examples(): Promise<Example[]> {
    const r = await fetch(`${this.base}/api/examples`);
    return r.ok ? r.json() : [];
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

  /** Server-Sent Events; returns a function that closes the stream. */
  stream(id: string, onEvent: (e: PipelineEvent) => void, onEnd: () => void): () => void {
    const es = new EventSource(`${this.base}/api/check/${encodeURIComponent(id)}/events`);
    es.onmessage = (m) => onEvent(JSON.parse(m.data));
    es.addEventListener('end', () => { es.close(); onEnd(); });
    es.onerror = () => { es.close(); onEnd(); };
    return () => es.close();
  }

  async report(id: string): Promise<{ id: string; text: string; events: PipelineEvent[] } | null> {
    const r = await fetch(`${this.base}/api/reports/${encodeURIComponent(id)}`);
    return r.ok ? r.json() : null;
  }
}
