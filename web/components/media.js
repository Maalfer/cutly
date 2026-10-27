// @ts-check
import { useCallback, useEffect, useRef, useState } from 'preact/hooks';
import { html } from '../html.js';
import { api, ApiError } from '../api.js';
import { navigate, toast, useStore } from '../store.js';
import { JOB_LABEL, fmtBytes, fmtTime } from '../util.js';
import { Waveform } from '../canvas/waveform.js';
import { Transcript } from './transcript.js';

export function MediaPage({ id }) {
  const user = useStore((s) => s.user);
  const canWrite = !!user?.can_write;
  const [media, setMedia] = useState(/** @type {any} */ (null));
  const [jobs, setJobs] = useState(/** @type {any[]} */ ([]));
  const [segments, setSegments] = useState(/** @type {any[]|null} */ (null));
  const [lang, setLang] = useState('es');
  const video = useRef(/** @type {HTMLVideoElement|null} */ (null));

  const loadTranscript = useCallback(async () => {
    try { setSegments((await api.get(`/media/${id}/transcript?words=false`)).segments); }
    catch (e) { if (e instanceof ApiError && e.status === 404) setSegments(null); }
  }, [id]);
  const refresh = useCallback(async () => {
    try {
      const [m, js] = await Promise.all([api.get(`/media/${id}`), api.get('/jobs?limit=30')]);
      setMedia(m); setJobs(js.filter((/** @type {any} */ j) => j.params?.media_id === id));
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) { toast('Ese vídeo ya no existe', 'error'); navigate('/'); }
    }
  }, [id]);

  useEffect(() => { refresh(); loadTranscript(); }, [id]);
  const running = jobs.filter((j) => j.status === 'queued' || j.status === 'running');
  useEffect(() => {
    if (!running.length) return;
    const t = setInterval(refresh, 2000);
    return () => clearInterval(t);
  }, [running.length]);
  // Cuando termina una transcripción, recarga el texto.
  const doneTranscribe = jobs.filter((j) => j.type === 'transcribe' && j.status === 'done').length;
  useEffect(() => { if (doneTranscribe) loadTranscript(); }, [doneTranscribe]);

  async function act(/** @type {()=>Promise<any>} */ fn, /** @type {string} */ ok) {
    try { await fn(); if (ok) toast(ok, 'ok'); refresh(); } catch (e) { toast(/** @type {Error} */ (e).message, 'error'); }
  }
  async function remove() {
    if (!confirm(`¿Borrar «${media.filename}» y todo lo asociado? No se puede deshacer.`)) return;
    await act(() => api.del(`/media/${id}`), 'Vídeo borrado');
    navigate('/');
  }

  if (!media) return html`<p class="muted">Cargando…</p>`;
  const transcribing = running.some((j) => j.type === 'transcribe');

  return html`
    <div class="back-row"><a href="#/" class="link">← Volver</a></div>
    <h2 class="page-title" title=${media.filename}>${media.filename}</h2>
    <p class="muted small">${fmtTime(media.duration)} · ${fmtBytes(media.size_bytes)} · ${media.metadata.width}×${media.metadata.height} · ${media.metadata.fps} fps</p>

    <div class="media-layout">
      <section class="left">
        <div class="player card">
          ${media.has_proxy
            ? html`<video ref=${video} src=${`/api/v1/media/${id}/proxy.mp4`} controls playsinline preload="metadata"></video>`
            : html`<div class="placeholder"><p>Generando vista previa…</p></div>`}
        </div>
        ${media.has_proxy && media.has_peaks && html`<div class="card"><${Waveform} mediaId=${id} duration=${media.duration} video=${video} /></div>`}
        ${running.length > 0 && html`<div class="card jobs" aria-live="polite">
          ${running.map((j) => html`<div key=${j.id}>
            <div class="row"><span>${JOB_LABEL[j.type] || j.type}</span><span class="muted small">${j.status === 'queued' ? 'en cola' : Math.round(j.progress * 100) + ' %'}</span></div>
            <progress max="100" value=${j.progress * 100}></progress>
            ${canWrite && html`<button class="link small" onClick=${() => act(() => api.post(`/jobs/${j.id}/cancel`), 'Cancelado')}>Cancelar</button>`}
          </div>`)}
        </div>`}
        ${jobs.filter((j) => j.status === 'failed').slice(0, 2).map((j) => html`<div class="card error-card" key=${j.id}><strong>${JOB_LABEL[j.type] || j.type} falló</strong><p class="small">${j.error}</p></div>`)}
        <div class="actions"><a class="linkbtn primary-link" href=${`#/editor/${id}`}>✂ Abrir en el editor</a></div>
        ${canWrite && html`<div class="actions">
          <button onClick=${() => act(() => api.post(`/media/${id}/proxy`), 'Regenerando vista previa')}>Regenerar vista previa</button>
          <button class="danger" onClick=${remove}>Borrar vídeo</button>
        </div>`}
      </section>

      <section class="right">
        <h3>Transcripción</h3>
        ${segments
          ? html`<${Transcript} mediaId=${id} segments=${segments} video=${video} canWrite=${canWrite} onChange=${setSegments} />`
          : html`<div class="card">
              <p class="muted">${transcribing ? 'Transcribiendo… puede tardar bastante en directos largos.' : 'Este vídeo aún no tiene transcripción.'}</p>
              ${canWrite && !transcribing && html`<div class="row gap">
                <label class="inline">Idioma
                  <select value=${lang} onChange=${(/** @type {Event} */ e) => setLang(/** @type {HTMLSelectElement} */ (e.target).value)}>
                    <option value="es">Español</option><option value="en">Inglés</option><option value="auto">Autodetectar</option>
                  </select></label>
                <button class="primary" onClick=${() => act(() => api.post(`/media/${id}/transcribe`, { json: { language: lang === 'auto' ? null : lang } }), 'Transcripción en marcha')}>Transcribir</button>
              </div>`}
            </div>`}
      </section>
    </div>`;
}
