// @ts-check
import { useEffect, useMemo, useRef, useState } from 'preact/hooks';
import { html } from '../html.js';
import { api } from '../api.js';
import { toast } from '../store.js';
import { fmtTime } from '../util.js';

/**
 * Lista de segmentos. Se renderiza una vez; el resaltado del segmento activo se hace tocando
 * solo la clase del nodo (sin re-render) y `content-visibility:auto` evita pintar lo que no se ve.
 * @param {{mediaId:string, segments:any[], video:{current:HTMLVideoElement|null}, canWrite:boolean, onChange:(s:any[])=>void}} p
 */
export function Transcript({ mediaId, segments, video, canWrite, onChange }) {
  const [query, setQuery] = useState('');
  const [follow, setFollow] = useState(true);
  const [editing, setEditing] = useState(/** @type {number|null} */ (null));
  const list = useRef(/** @type {HTMLOListElement|null} */ (null));
  const active = useRef(/** @type {HTMLElement|null} */ (null));
  const followRef = useRef(follow);
  followRef.current = follow;

  const shown = useMemo(() => {
    const q = query.trim().toLowerCase();
    return q ? segments.filter((s) => s.text.toLowerCase().includes(q)) : segments;
  }, [segments, query]);

  useEffect(() => {
    const v = video.current;
    if (!v) return;
    const starts = segments.map((s) => s.start);
    function onTime() {
      const t = /** @type {HTMLVideoElement} */ (v).currentTime;
      let lo = 0, hi = starts.length - 1, idx = -1; // búsqueda binaria del último inicio <= t
      while (lo <= hi) { const m = (lo + hi) >> 1; if (starts[m] <= t) { idx = m; lo = m + 1; } else hi = m - 1; }
      const el = idx >= 0 ? list.current?.querySelector(`[data-id="${segments[idx].id}"]`) : null;
      if (el === active.current) return;
      active.current?.classList.remove('active');
      active.current = /** @type {HTMLElement|null} */ (el);
      if (el) {
        el.classList.add('active');
        if (followRef.current && !list.current?.contains(document.activeElement?.closest('textarea') ?? null)) el.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
      }
    }
    v.addEventListener('timeupdate', onTime);
    return () => v.removeEventListener('timeupdate', onTime);
  }, [segments]);

  async function save(/** @type {any} */ seg, /** @type {string} */ text) {
    if (text.trim() === seg.text) return setEditing(null);
    try {
      const upd = await api.patch(`/media/${mediaId}/transcript/segments/${seg.id}`, { json: { text } });
      onChange(segments.map((s) => (s.id === seg.id ? { ...s, text: upd.text } : s)));
      setEditing(null);
    } catch (e) { toast(/** @type {Error} */ (e).message, 'error'); }
  }

  return html`
    <div class="transcript">
      <div class="toolbar">
        <input type="search" placeholder="Buscar en la transcripción…" value=${query} onInput=${(/** @type {Event} */ e) => setQuery(/** @type {HTMLInputElement} */ (e.target).value)} aria-label="Buscar" />
        <label class="check"><input type="checkbox" checked=${follow} onChange=${(/** @type {Event} */ e) => setFollow(/** @type {HTMLInputElement} */ (e.target).checked)} /> Seguir</label>
      </div>
      <p class="muted small">${shown.length} de ${segments.length} segmentos</p>
      <ol ref=${list} class="segments">
        ${shown.map((s) => html`<li key=${s.id} data-id=${s.id}>
          <button class="ts" onClick=${() => { if (video.current) { video.current.currentTime = s.start; video.current.play().catch(() => {}); } }}>${fmtTime(s.start)}</button>
          ${editing === s.id
            ? html`<form class="edit" onSubmit=${(/** @type {SubmitEvent} */ e) => { e.preventDefault(); save(s, /** @type {HTMLTextAreaElement} */ (/** @type {HTMLFormElement} */ (e.target).elements.namedItem('t')).value); }}>
                <textarea name="t" rows="3" autofocus>${s.text}</textarea>
                <div class="row"><button class="primary small-btn">Guardar</button><button type="button" class="link" onClick=${() => setEditing(null)}>Cancelar</button></div>
              </form>`
            : html`<span class="text" onDblClick=${() => canWrite && setEditing(s.id)}>${s.text}</span>
                ${canWrite && html`<button class="icon-btn" aria-label="Editar segmento" title="Editar" onClick=${() => setEditing(s.id)}>✎</button>`}`}
        </li>`)}
      </ol>
    </div>`;
}
