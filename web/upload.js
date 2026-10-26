// @ts-check
// Subida por trozos reanudable, pensada para enlaces lentos o inestables:
//  - trozos pequeños (4 MB): cada petición dura poco y un corte cuesta poco;
//  - XMLHttpRequest para tener progreso real por bytes (fetch no lo da);
//  - detección de bloqueos (sin bytes durante `stallMs` → se aborta y se reintenta);
//  - reintentos con espera creciente; reanuda por el servidor (qué trozos tiene ya).
import { ApiError, api } from './api.js';

const BASE = '/api/v1';
export const CHUNK_BYTES = 4 * 1024 * 1024;

const hex = (/** @type {ArrayBuffer} */ b) => [...new Uint8Array(b)].map((x) => x.toString(16).padStart(2, '0')).join('');
const sleep = (/** @type {number} */ ms, /** @type {AbortSignal|undefined} */ signal) =>
  new Promise((resolve, reject) => {
    const t = setTimeout(resolve, ms);
    signal?.addEventListener('abort', () => { clearTimeout(t); reject(new DOMException('Cancelado', 'AbortError')); }, { once: true });
  });

export class NetworkError extends Error {}

/**
 * Una petición PUT con progreso y vigilancia de bloqueo.
 * @param {string} url @param {Blob} body @param {Record<string,string>} headers
 * @param {{signal?:AbortSignal, onBytes:(n:number)=>void, stallMs:number, XHR?:typeof XMLHttpRequest}} o
 */
export function putChunk(url, body, headers, o) {
  return new Promise((resolve, reject) => {
    const xhr = new (o.XHR || XMLHttpRequest)();
    xhr.open('PUT', url);
    xhr.withCredentials = true;
    for (const [k, v] of Object.entries(headers)) xhr.setRequestHeader(k, v);
    let lastProgress = Date.now();
    const watchdog = setInterval(() => {
      if (Date.now() - lastProgress > o.stallMs) { xhr.abort(); finish(new NetworkError('Sin avance en la subida (bloqueada); reintentando')); }
    }, Math.min(1000, o.stallMs / 2));
    let done = false;
    /** @param {Error|null} err @param {any} [val] */
    function finish(err, val) {
      if (done) return;
      done = true;
      clearInterval(watchdog);
      if (err) reject(err); else resolve(val);
    }
    xhr.upload.onprogress = (e) => { lastProgress = Date.now(); o.onBytes(e.loaded); };
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try { finish(null, JSON.parse(xhr.responseText)); } catch { finish(null, {}); }
      } else {
        let detail = xhr.statusText || `HTTP ${xhr.status}`;
        try { detail = JSON.parse(xhr.responseText).detail || detail; } catch { /* sin JSON */ }
        finish(new ApiError(xhr.status, String(detail)));
      }
    };
    xhr.onerror = () => finish(new NetworkError('Se perdió la conexión con el servidor'));
    xhr.ontimeout = () => finish(new NetworkError('La petición tardó demasiado'));
    xhr.onabort = () => finish(o.signal?.aborted ? new DOMException('Cancelado', 'AbortError') : new NetworkError('Subida interrumpida'));
    o.signal?.addEventListener('abort', () => xhr.abort(), { once: true });
    xhr.send(body);
  });
}

/**
 * @typedef {{bytes:number,total:number,phase:string,retries:number,message?:string}} UploadState
 * @param {File} file
 * @param {{onState:(s:UploadState)=>void, signal:AbortSignal, chunkBytes?:number, concurrency?:number,
 *          stallMs?:number, maxAttempts?:number, backoffMs?:number, XHR?:typeof XMLHttpRequest, storage?:Storage}} o
 */
export async function uploadFile(file, o) {
  const { onState, signal } = o;
  const store = o.storage ?? (typeof localStorage !== 'undefined' ? localStorage : undefined);
  const key = `cf-upload:${file.name}:${file.size}:${file.lastModified}`;
  const state = /** @type {UploadState} */ ({ bytes: 0, total: file.size, phase: 'preparando', retries: 0 });
  const emit = (/** @type {Partial<UploadState>} */ p = {}) => onState(Object.assign(state, p));
  emit();

  // ¿hay una subida a medias de este mismo archivo? → reanudar
  let up = null;
  try {
    const id = store?.getItem(key);
    if (id) up = await api.get(`/uploads/${id}`);
  } catch { up = null; }
  if (!up || up.status !== 'uploading') {
    up = await api.post('/uploads', { json: { filename: file.name, size: file.size, chunk_size: o.chunkBytes ?? CHUNK_BYTES } });
    try { store?.setItem(key, up.upload_id); } catch { /* modo privado */ }
  }
  const { upload_id: id, chunk_size: cs, total_chunks: total } = up;
  const sizeOf = (/** @type {number} */ n) => (n < total - 1 ? cs : file.size - n * cs);
  const done = new Set(/** @type {number[]} */ (up.received));
  let completed = [...done].reduce((a, n) => a + sizeOf(n), 0);
  const inflight = new Map(); // trozo → bytes ya enviados de ese trozo
  const refresh = () => emit({ bytes: Math.min(file.size, completed + [...inflight.values()].reduce((a, b) => a + b, 0)), phase: 'subiendo' });
  refresh();
  const pending = [...Array(total).keys()].filter((n) => !done.has(n));
  const maxAttempts = o.maxAttempts ?? 8;

  async function sendChunk(/** @type {number} */ n) {
    const blob = file.slice(n * cs, n * cs + sizeOf(n));
    /** @type {Record<string,string>} */
    const headers = {};
    try {
      if (globalThis.crypto?.subtle) headers['X-Chunk-SHA256'] = hex(await crypto.subtle.digest('SHA-256', await blob.arrayBuffer()));
    } catch { /* sin huella: el servidor igualmente comprueba el tamaño */ }
    for (let attempt = 1; ; attempt++) {
      inflight.set(n, 0);
      try {
        await putChunk(`${BASE}/uploads/${id}/chunks/${n}`, blob, headers, {
          signal, stallMs: o.stallMs ?? 25000, XHR: o.XHR,
          onBytes: (b) => { inflight.set(n, Math.min(b, sizeOf(n))); refresh(); },
        });
        inflight.delete(n);
        completed += sizeOf(n);
        refresh();
        return;
      } catch (e) {
        inflight.delete(n);
        refresh();
        if (signal.aborted) throw e;
        const fatal = e instanceof ApiError && [401, 403, 404, 409, 413].includes(e.status);
        if (fatal || attempt >= maxAttempts) throw e;
        state.retries++;
        emit({ message: `Reintentando el trozo ${n + 1}/${total} (intento ${attempt + 1}/${maxAttempts}): ${/** @type {Error} */ (e).message}` });
        await sleep((o.backoffMs ?? 1000) * Math.min(2 ** (attempt - 1), 15) + Math.random() * 300, signal);
      }
    }
  }

  const workers = Array.from({ length: Math.min(o.concurrency ?? 3, pending.length) }, async () => {
    while (pending.length && !signal.aborted) await sendChunk(/** @type {number} */ (pending.shift()));
  });
  try {
    await Promise.all(workers);
  } catch (e) {
    pending.length = 0; // que el resto de hilos termine
    throw e;
  }
  if (signal.aborted) throw new DOMException('Cancelado', 'AbortError');
  emit({ phase: 'finalizando', message: undefined });
  const res = await api.post(`/uploads/${id}/complete`);
  try { store?.removeItem(key); } catch { /* nada */ }
  emit({ phase: 'hecho', bytes: file.size });
  return res;
}
