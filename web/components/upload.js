// @ts-check
import { useEffect, useRef, useState } from 'preact/hooks';
import { html } from '../html.js';
import { uploadFile } from '../upload.js';
import { toast } from '../store.js';
import { fmtBytes, fmtTime } from '../util.js';

/** Zona de subida: arrastrar o elegir archivos; sube uno a uno con progreso real, velocidad, ETA y reintento. */
export function Uploader({ onDone }) {
  const [items, setItems] = useState(/** @type {any[]} */ ([]));
  const [drag, setDrag] = useState(false);
  const input = useRef(/** @type {HTMLInputElement|null} */ (null));
  const busy = useRef(false);
  const queue = useRef(/** @type {any[]} */ ([]));
  const active = items.some((i) => i.status === 'subiendo' || i.status === 'en cola');

  // Avisa antes de cerrar la pestaña con una subida en curso.
  useEffect(() => {
    if (!active) return;
    const h = (/** @type {BeforeUnloadEvent} */ e) => { e.preventDefault(); e.returnValue = ''; };
    addEventListener('beforeunload', h);
    return () => removeEventListener('beforeunload', h);
  }, [active]);

  const patch = (/** @type {any} */ it, /** @type {any} */ p) => {
    Object.assign(it, p);
    setItems((l) => [...l]);
  };

  async function pump() {
    if (busy.current) return;
    busy.current = true;
    while (queue.current.length) {
      const it = queue.current.shift();
      if (it.status === 'cancelado') continue;
      it.ctl = new AbortController();
      patch(it, { status: 'subiendo', error: '', message: '', started: performance.now(), sample: [] });
      try {
        await uploadFile(it.file, {
          signal: it.ctl.signal,
          onState: (s) => {
            const now = performance.now();
            const sample = [...it.sample, [now, s.bytes]].filter((x) => now - x[0] < 8000); // ventana de 8 s para la velocidad
            const speed = sample.length > 1 ? (s.bytes - sample[0][1]) / ((now - sample[0][0]) / 1000) : 0;
            patch(it, { bytes: s.bytes, total: s.total, phase: s.phase, retries: s.retries, message: s.message || '', sample, speed });
          },
        });
        patch(it, { status: 'procesando', message: '' });
        toast(`«${it.file.name}» subido. Generando vista previa…`, 'ok');
        onDone();
      } catch (e) {
        const err = /** @type {Error} */ (e);
        if (err.name === 'AbortError') patch(it, { status: 'cancelado' });
        else { patch(it, { status: 'error', error: err.message }); toast(`No se pudo subir «${it.file.name}»: ${err.message}`, 'error'); }
      }
    }
    busy.current = false;
  }

  function add(/** @type {FileList|File[]} */ files) {
    const fresh = [...files].map((file) => ({ file, status: 'en cola', bytes: 0, total: file.size, speed: 0, phase: 'preparando', retries: 0, id: Math.random() }));
    queue.current.push(...fresh);
    setItems((l) => [...fresh, ...l].slice(0, 8));
    pump();
  }
  function retry(/** @type {any} */ it) {
    patch(it, { status: 'en cola', error: '' });
    queue.current.push(it);
    pump(); // reanuda por el último trozo recibido
  }
  const eta = (/** @type {any} */ it) => (it.speed > 1000 ? fmtTime((it.total - it.bytes) / it.speed) : '');

  return html`
    <section class="card">
      <div class=${'drop' + (drag ? ' over' : '')}
           onDragOver=${(/** @type {DragEvent} */ e) => { e.preventDefault(); setDrag(true); }}
           onDragLeave=${() => setDrag(false)}
           onDrop=${(/** @type {DragEvent} */ e) => { e.preventDefault(); setDrag(false); if (e.dataTransfer) add(e.dataTransfer.files); }}>
        <p><strong>Sube un directo</strong></p>
        <p class="muted">Arrastra el vídeo aquí o elígelo. Se sube por trozos y, si se corta, se reanuda donde se quedó.</p>
        <button class="primary" onClick=${() => input.current?.click()}>Elegir vídeo</button>
        <input ref=${input} type="file" accept="video/*,.mkv,.ts,.flv" multiple hidden
               onChange=${(/** @type {Event} */ e) => { const t = /** @type {HTMLInputElement} */ (e.target); if (t.files) add(t.files); t.value = ''; }} />
      </div>
      ${items.length > 0 && html`<ul class="uploads">
        ${items.map((it) => html`<li key=${it.id}>
          <div class="row"><span class="name">${it.file.name}</span><span class=${'badge ' + it.status.replace(' ', '-')}>${it.status}</span></div>
          <progress max="100" value=${it.total ? (it.bytes / it.total) * 100 : 0}></progress>
          <div class="row muted small">
            <span>${it.total ? Math.floor((it.bytes / it.total) * 100) : 0} % · ${fmtBytes(it.bytes)} / ${fmtBytes(it.total)}${it.speed > 0 ? ` · ${fmtBytes(it.speed)}/s` : ''}${eta(it) ? ` · quedan ${eta(it)}` : ''}</span>
            ${it.status === 'subiendo' || it.status === 'en cola'
              ? html`<button class="link" onClick=${() => { it.ctl?.abort(); patch(it, { status: 'cancelado' }); }}>Cancelar</button>`
              : it.status === 'error' || it.status === 'cancelado' ? html`<button class="link" onClick=${() => retry(it)}>Reintentar</button>` : ''}
          </div>
          ${it.status === 'subiendo' && it.phase === 'preparando' && html`<p class="muted small">Preparando la subida…</p>`}
          ${it.message && html`<p class="warn small" role="status">${it.message}</p>`}
          ${it.error && html`<p class="error small" role="alert">${it.error}</p>`}
        </li>`)}
      </ul>`}
    </section>`;
}
