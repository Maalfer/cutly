// @ts-check
// Estado del editor: proyecto, selección, cola de operaciones con actualización optimista, undo/redo, catálogos.
import { useEffect, useState } from 'preact/hooks';
import { api } from '../api.js';
import { createStore, toast } from '../store.js';
import { timelineDuration } from './time.js';

export const ed = createStore({
  /** @type {any} */ media: null,
  /** @type {any[]} */ projects: [],
  /** @type {any} */ project: null, // respuesta del servidor: {id,name,version,duration,can_undo,can_redo,warnings,project}
  /** @type {any} */ doc: null, // documento de trabajo (con cambios optimistas)
  /** @type {{kind:'none'|'layer'|'clip', id:string|null}} */ selection: { kind: 'none', id: null },
  t: 0,
  playing: false,
  zoom: 80, // píxeles por segundo en la línea de tiempo
  scroll: 0, // segundo que ocupa el borde izquierdo
  timelineH: 270,
  saving: false,
  /** @type {{w:string,start:number,end:number}[]} */ words: [],
  /** @type {any[]} */ effects: [],
  /** @type {any[]} */ assets: [],
  /** @type {any[]} */ presets: [],
  /** @type {any[]} */ issues: [],
  checking: false,
  /** @type {any} */ render: null,
  left: 'layers',
  mtab: 'timeline', // móvil: panel inferior visible (timeline | left | right)
  stageBig: false, // móvil: vista previa ampliada
  loading: true,
  /** @type {string|null} */ error: null,
});

export const get = ed.get;
export function useEd(/** @type {(s:any)=>any} */ selector) {
  const [v, setV] = useState(() => selector(ed.get()));
  useEffect(() => ed.subscribe((s) => setV(() => selector(s))), []);
  return v;
}

/** RFC 7386 (merge patch): los objetos se fusionan, null borra la clave, el resto se reemplaza. */
export function mergePatch(/** @type {any} */ target, /** @type {any} */ patch) {
  if (patch === null || typeof patch !== 'object' || Array.isArray(patch)) return patch;
  const out = target && typeof target === 'object' && !Array.isArray(target) ? { ...target } : {};
  for (const [k, v] of Object.entries(patch)) {
    if (v === null) delete out[k];
    else out[k] = mergePatch(out[k], v);
  }
  return out;
}

// --- carga ----------------------------------------------------------------------------------------------------------------

export async function openMedia(/** @type {string} */ mediaId, /** @type {string|null} */ projectId = null) {
  ed.set({ loading: true, error: null, project: null, doc: null, selection: { kind: 'none', id: null }, t: 0, playing: false, issues: [], render: null });
  try {
    const [media, projects] = await Promise.all([api.get(`/media/${mediaId}`), api.get(`/projects?media_id=${mediaId}`)]);
    let pid = projectId || projects[0]?.id;
    if (!pid) {
      const created = await api.post('/projects', { json: { media_id: mediaId, source_in: 0, source_out: Math.min(media.duration, media.duration <= 300 ? media.duration : 60), name: `Proyecto de ${media.filename}` } });
      pid = created.id;
      projects.unshift({ id: pid, name: created.name, media_id: mediaId, duration: created.duration, version: created.version });
    }
    ed.set({ media, projects });
    await loadProject(pid);
    loadCatalogs(mediaId);
  } catch (e) {
    ed.set({ error: /** @type {Error} */ (e).message });
  } finally {
    ed.set({ loading: false });
  }
}

export async function loadProject(/** @type {string} */ pid) {
  const p = await api.get(`/projects/${pid}`);
  ed.set({ project: p, doc: p.project, selection: { kind: 'none', id: null }, scroll: 0, issues: [], render: null });
}

async function loadCatalogs(/** @type {string} */ mediaId) {
  const [fx, assets, presets, tr] = await Promise.allSettled([
    api.get('/effects'), api.get('/assets?limit=500'), api.get('/presets'), api.get(`/media/${mediaId}/transcript?words=true`),
  ]);
  ed.set({
    effects: fx.status === 'fulfilled' ? fx.value.effects : [],
    assets: assets.status === 'fulfilled' ? assets.value.assets : [],
    presets: presets.status === 'fulfilled' ? presets.value.presets : [],
    words: tr.status === 'fulfilled' ? tr.value.segments.flatMap((/** @type {any} */ s) => (s.words || []).map((/** @type {any} */ w) => ({ w: w.w, start: w.start, end: w.end }))) : [],
  });
}

export async function refreshProjectList() {
  const m = get().media;
  if (m) ed.set({ projects: await api.get(`/projects?media_id=${m.id}`) });
}

// --- operaciones ----------------------------------------------------------------------------------------------------------

let chain = Promise.resolve();
const pending = new Map(); // layer_id → {patch, timer}

function setProject(/** @type {any} */ p) {
  // si hay cambios locales sin enviar, se conserva el documento de trabajo y solo se actualizan los metadatos
  ed.set({ project: p, doc: pending.size ? get().doc : p.project });
}

/** Envía un lote de operaciones en cola (una a una, para no pisar versiones). Devuelve la respuesta o null si falla. */
export function applyOps(/** @type {any[]} */ ops, label = '') {
  const run = async () => {
    const pj = get().project;
    if (!pj) return null;
    ed.set({ saving: true });
    try {
      const r = await api.post(`/projects/${pj.id}/ops`, { json: { ops, label: label || undefined, base_version: pj.version } });
      setProject(r);
      return r;
    } catch (e) {
      toast(/** @type {Error} */ (e).message, 'error');
      await reload();
      return null;
    } finally {
      ed.set({ saving: false });
    }
  };
  const next = chain.then(run, run);
  chain = next.then(() => {}, () => {});
  return next;
}

export async function reload() {
  const pj = get().project;
  if (pj) {
    pending.forEach((p) => clearTimeout(p.timer));
    pending.clear();
    await loadProject(pj.id).catch(() => {});
  }
}

export async function undoRedo(/** @type {'undo'|'redo'} */ which) {
  const pj = get().project;
  if (!pj) return;
  await chain;
  try {
    const r = await api.post(`/projects/${pj.id}/${which}`, { json: { base_version: get().project.version } });
    ed.set({ project: r, doc: r.project });
  } catch (e) { toast(/** @type {Error} */ (e).message, 'error'); }
}

/** Cambia una layer al instante en pantalla y envía un único `update_layer` cuando se deja de tocar (anti-rebote). */
export function patchLayer(/** @type {string} */ id, /** @type {any} */ patch, /** @type {boolean} */ immediate = false) {
  const doc = get().doc;
  if (!doc) return;
  ed.set({ doc: { ...doc, layers: doc.layers.map((/** @type {any} */ l) => (l.id === id ? mergePatch(l, patch) : l)) } });
  const prev = pending.get(id);
  if (prev) clearTimeout(prev.timer);
  const merged = prev ? mergePatch(prev.patch, patch) : patch;
  const flush = () => {
    pending.delete(id);
    applyOps([{ op: 'update_layer', layer_id: id, patch: merged }]);
  };
  pending.set(id, { patch: merged, timer: setTimeout(flush, immediate ? 0 : 300) });
}

export function patchClip(/** @type {string} */ id, /** @type {any} */ patch) {
  const ops = [];
  if ('source_in' in patch || 'source_out' in patch) ops.push({ op: 'set_clip_range', clip_id: id, source_in: patch.source_in, source_out: patch.source_out });
  if ('speed' in patch) ops.push({ op: 'set_clip_speed', clip_id: id, speed: patch.speed });
  if ('transition_in' in patch) ops.push({ op: 'set_transition', clip_id: id, transition: patch.transition_in });
  return applyOps(ops);
}

export const select = (/** @type {'none'|'layer'|'clip'} */ kind, /** @type {string|null} */ id = null) => ed.set({ selection: { kind, id } });
export const layerById = (/** @type {string|null} */ id) => get().doc?.layers.find((/** @type {any} */ l) => l.id === id) || null;
export const clipById = (/** @type {string|null} */ id) => get().doc?.timeline.find((/** @type {any} */ c) => c.id === id) || null;
export const duration = () => (get().doc ? timelineDuration(get().doc.timeline) : 0);

// --- comprobaciones y render ----------------------------------------------------------------------------------------

export async function runChecks() {
  const pj = get().project;
  if (!pj) return;
  ed.set({ checking: true });
  try {
    const r = await api.get(`/projects/${pj.id}/checks?wait=100`);
    ed.set({ issues: r.issues || [] });
    toast(r.issues?.some((/** @type {any} */ i) => i.severity !== 'info') ? `${r.counts.error} errores, ${r.counts.warning} avisos` : 'Sin problemas detectados', r.ok ? 'ok' : 'error');
  } catch (e) { toast(/** @type {Error} */ (e).message, 'error'); } finally { ed.set({ checking: false }); }
}

/** Dispara la descarga de un render sin salir de la SPA (mismo endpoint que el enlace «⬇ Descargar»). */
function downloadRender(/** @type {string} */ jobId) {
  const a = document.createElement('a');
  a.href = `/api/v1/renders/${jobId}/download`;
  a.download = '';
  document.body.appendChild(a);
  a.click();
  a.remove();
}

export async function startRender(/** @type {'draft'|'final'} */ quality, /** @type {{start?:number,end?:number}} */ range = {}) {
  const pj = get().project;
  if (!pj) return;
  try {
    const { job_id } = await api.post(`/projects/${pj.id}/render`, { json: { quality, ...range } });
    ed.set({ render: { job: job_id, quality, status: 'queued', progress: 0 } });
    for (;;) {
      await new Promise((r) => setTimeout(r, 2000));
      // el proyecto pudo cambiar mientras tanto (otro render, otra pestaña): no pises un estado más reciente
      if (get().render?.job !== job_id) return;
      const j = await api.get(`/jobs/${job_id}`);
      ed.set({ render: { job: job_id, quality, status: j.status, progress: j.progress, error: j.error, result: j.result } });
      if (['done', 'failed', 'cancelled'].includes(j.status)) {
        if (j.status === 'done') { toast('Render listo: descargando…', 'ok'); downloadRender(job_id); }
        break;
      }
    }
  } catch (e) { toast(/** @type {Error} */ (e).message, 'error'); ed.set({ render: null }); }
}
