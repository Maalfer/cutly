// @ts-check
import { useCallback, useEffect, useState } from 'preact/hooks';
import { html } from '../html.js';
import { api } from '../api.js';
import { navigate, toast, useStore } from '../store.js';
import { fmtBytes, fmtTime } from '../util.js';
import { Uploader } from './upload.js';

export function Library() {
  const user = useStore((s) => s.user);
  const canWrite = !!user?.can_write;
  const [media, setMedia] = useState(/** @type {any[]|null} */ (null));
  const [deleting, setDeleting] = useState(/** @type {string|null} */ (null));
  const load = useCallback(async () => {
    try { setMedia(await api.get('/media')); } catch (e) { toast(/** @type {Error} */ (e).message, 'error'); }
  }, []);
  useEffect(() => { load(); }, []);
  // Mientras algún medio se procesa, refresca cada 3 s.
  useEffect(() => {
    if (!media?.some((m) => m.status !== 'ready')) return;
    const t = setInterval(load, 3000);
    return () => clearInterval(t);
  }, [media]);

  /** @param {Event} e @param {any} m */
  async function remove(e, m) {
    e.preventDefault();
    e.stopPropagation();
    if (!confirm(`¿Borrar «${m.filename}» y todo lo asociado (transcripción, proyectos)? No se puede deshacer.`)) return;
    setDeleting(m.id);
    try {
      const res = await api.del(`/media/${m.id}`);
      const mb = res?.freed_bytes ? ` (${(res.freed_bytes / 1048576).toFixed(1)} MB liberados)` : '';
      toast('Vídeo borrado' + mb, 'ok');
      setMedia((prev) => (prev ? prev.filter((x) => x.id !== m.id) : prev));
    } catch (err) {
      toast(/** @type {Error} */ (err).message, 'error');
    } finally {
      setDeleting(null);
    }
  }

  return html`
    <${Uploader} onDone=${load} />
    <h2>Tus vídeos</h2>
    ${media === null ? html`<p class="muted">Cargando…</p>`
      : media.length === 0 ? html`<p class="muted empty">Aún no hay vídeos. Sube el primero arriba.</p>`
      : html`<div class="grid">${media.map((m) => html`
        <div class="card media-card" key=${m.id} role="link" tabindex="0"
          onClick=${() => navigate('/editor/' + m.id)}
          onKeyDown=${(/** @type {KeyboardEvent} */ e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); navigate('/editor/' + m.id); } }}>
          <div class="thumb" aria-hidden="true">
            <span class="dur">${fmtTime(m.duration)}</span>
            ${canWrite && html`<button class="media-del icon-btn" type="button" title="Borrar vídeo"
              aria-label=${'Borrar ' + m.filename} disabled=${deleting === m.id}
              onClick=${(/** @type {Event} */ e) => remove(e, m)}>${deleting === m.id ? '…' : '🗑'}</button>`}
          </div>
          <div class="meta">
            <strong class="name" title=${m.filename}>${m.filename}</strong>
            <span class="muted small">${fmtBytes(m.size_bytes)} · ${m.metadata?.width}×${m.metadata?.height}</span>
            <span class=${'badge ' + m.status}>${m.status === 'ready' ? 'Listo' : 'Procesando…'}</span>
          </div>
        </div>`)}</div>`}`;
}
