// @ts-check
// Transcripción dentro del editor: frases del tramo editado, clic para saltar, corrección de texto y búsqueda.
import { useEffect, useMemo, useRef, useState } from 'preact/hooks';
import { html } from '../html.js';
import { api } from '../api.js';
import { toast } from '../store.js';
import { rt } from './preview.js';
import { ed, useEd } from './state.js';
import { clipDuration, fmtClock, timelineStarts } from './time.js';

/** fuente → salida; null si ese instante no está en ningún clip */
function sourceToOutput(/** @type {any[]} */ tl, /** @type {number} */ s) {
  const st = timelineStarts(tl);
  for (let i = 0; i < tl.length; i++) if (s >= tl[i].source_in - 1e-6 && s < tl[i].source_out) return st[i] + (s - tl[i].source_in) / (tl[i].speed || 1);
  return null;
}

export function TranscriptPanel() {
  const media = useEd((s) => s.media);
  const doc = useEd((s) => s.doc);
  const t = useEd((s) => s.t);
  const [segs, setSegs] = useState(/** @type {any[]|null} */ (null));
  const [q, setQ] = useState('');
  const [editing, setEditing] = useState(/** @type {number|null} */ (null));
  const [onlyClip, setOnlyClip] = useState(true);
  const list = useRef(/** @type {HTMLDivElement|null} */ (null));

  useEffect(() => { api.get(`/media/${media.id}/transcript?words=true`).then((r) => setSegs(r.segments)).catch(() => setSegs([])); }, [media.id]);

  const rows = useMemo(() => {
    if (!segs || !doc) return [];
    const ql = q.trim().toLowerCase();
    return segs.map((s) => ({ s, out: sourceToOutput(doc.timeline, s.start) }))
      .filter((r) => (!onlyClip || r.out != null || doc.timeline.some((/** @type {any} */ c) => s_in(r.s, c))) && (!ql || r.s.text.toLowerCase().includes(ql)));
  }, [segs, doc?.timeline, q, onlyClip]);
  const active = rows.find((r) => r.out != null && t >= r.out && t < r.out + (r.s.end - r.s.start)) || null;
  useEffect(() => { if (active && editing == null) list.current?.querySelector(`[data-id="${active.s.id}"]`)?.scrollIntoView({ block: 'nearest' }); }, [active?.s.id]);

  async function save(/** @type {any} */ seg, /** @type {string} */ text) {
    setEditing(null);
    if (!text.trim() || text.trim() === seg.text) return;
    try {
      const upd = await api.patch(`/media/${media.id}/transcript/segments/${seg.id}`, { json: { text } });
      const next = /** @type {any[]} */ (segs).map((x) => (x.id === seg.id ? upd : x));
      setSegs(next);
      ed.set({ words: next.flatMap((x) => (x.words || []).map((/** @type {any} */ w) => ({ w: w.w, start: w.start, end: w.end }))) });
    } catch (e) { toast(/** @type {Error} */ (e).message, 'error'); }
  }

  if (segs == null) return html`<p class="muted pad">Cargando transcripción…</p>`;
  if (!segs.length) return html`<div class="pad"><p class="muted">Este vídeo aún no está transcrito.</p><a class="small-btn linkbtn" href=${`#/media/${media.id}`}>Transcribir…</a></div>`;
  return html`<div class="panel-body transcript-ed">
    <input type="search" class="search" placeholder="Buscar en la transcripción…" value=${q} onInput=${(/** @type {Event} */ e) => setQ(/** @type {HTMLInputElement} */ (e.target).value)} aria-label="Buscar" />
    <label class="inline small pad"><input type="checkbox" checked=${onlyClip} onChange=${(/** @type {Event} */ e) => setOnlyClip(/** @type {HTMLInputElement} */ (e.target).checked)} /> Solo el tramo del proyecto</label>
    <div class="seg-list" ref=${list}>${rows.map(({ s, out }) => html`<div key=${s.id} data-id=${s.id} class=${'seg' + (active?.s.id === s.id ? ' active' : '')}>
      <button class="seg-time" disabled=${out == null} title=${out == null ? 'Fuera del tramo' : 'Ir a este punto'} onClick=${() => out != null && rt.player?.seek(out)}>${out != null ? fmtClock(out) : '—'}</button>
      ${editing === s.id
        ? html`<textarea autofocus rows="2" onBlur=${(/** @type {Event} */ e) => save(s, /** @type {HTMLTextAreaElement} */ (e.target).value)} onKeyDown=${(/** @type {KeyboardEvent} */ e) => { if (e.key === 'Escape') setEditing(null); if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); /** @type {HTMLElement} */ (e.target).blur(); } e.stopPropagation(); }}>${s.text}</textarea>`
        : html`<span class="seg-text" tabindex="0" title="Doble clic para corregir el texto" onDblClick=${() => setEditing(s.id)} onKeyDown=${(/** @type {KeyboardEvent} */ e) => { if (e.key === 'Enter') setEditing(s.id); }}>${s.text}</span>`}
    </div>`)}</div>
    <p class="muted tiny pad">Doble clic en una frase para corregirla; los subtítulos se actualizan al instante.</p>
  </div>`;
}
const s_in = (/** @type {any} */ s, /** @type {any} */ c) => s.end > c.source_in && s.start < c.source_out;
void clipDuration;
