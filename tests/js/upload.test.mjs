// Prueba de la lógica de subida del navegador con un XMLHttpRequest y un servidor simulados.
import assert from 'node:assert/strict';
import { uploadFile, putChunk, NetworkError } from '../../web/upload.js';
import { ApiError } from '../../web/api.js';

const MB = 1024 * 1024;
const mkFile = (size, name = 'directo.mp4') => new File([new Uint8Array(size)], name, { lastModified: 1 });
const mkStorage = () => { const m = new Map(); return { getItem: (k) => m.get(k) ?? null, setItem: (k, v) => m.set(k, v), removeItem: (k) => m.delete(k), m }; };

/** Servidor simulado: responde a fetch (API JSON) y guarda los trozos que llegan por XHR. */
function server({ received = [], chunk = 4 * MB, total = 3, behavior = {} } = {}) {
  const st = { received: new Set(received), calls: [], created: 0, completed: 0, attempts: {} };
  globalThis.fetch = async (url, opts = {}) => {
    const path = String(url).replace('/api/v1', '');
    const json = (o, status = 200) => new Response(JSON.stringify(o), { status, headers: { 'content-type': 'application/json' } });
    st.calls.push(`${opts.method} ${path}`);
    if (opts.method === 'POST' && path === '/uploads') { st.created++; st.chunk = JSON.parse(opts.body).chunk_size; return json({ upload_id: 'up_1', chunk_size: chunk, total_chunks: total, received: [...st.received], status: 'uploading' }); }
    if (opts.method === 'GET' && path.startsWith('/uploads/')) return json({ upload_id: 'up_1', chunk_size: chunk, total_chunks: total, received: [...st.received], status: 'uploading' });
    if (opts.method === 'POST' && path.endsWith('/complete')) { st.completed++; return json({ media_id: 'm_1', jobs: [] }); }
    return json({ detail: 'ruta desconocida' }, 404);
  };
  class XHR {
    constructor() { this.upload = {}; this.headers = {}; }
    open(m, u) { this.method = m; this.url = u; }
    setRequestHeader(k, v) { this.headers[k] = v; }
    abort() { this.aborted = true; clearTimeout(this.t); this.onabort?.(); }
    send(body) {
      const n = Number(this.url.split('/').pop());
      st.attempts[n] = (st.attempts[n] || 0) + 1;
      const b = (behavior[n] || [])[st.attempts[n] - 1] || 'ok';
      const size = body.size;
      const respond = (status, obj) => { this.status = status; this.responseText = JSON.stringify(obj); this.onload?.(); };
      this.t = setTimeout(() => {
        if (b === 'ok') { this.upload.onprogress?.({ loaded: Math.floor(size / 2) }); this.t = setTimeout(() => { this.upload.onprogress?.({ loaded: size }); st.received.add(n); respond(200, { n }); }, 5); }
        else if (b === 'net') this.onerror?.();
        else if (b === 'stall') { this.upload.onprogress?.({ loaded: 10 }); /* y no vuelve a avanzar */ }
        else if (b === '404') respond(404, { detail: 'Subida no encontrada' });
        else if (b === 'slow') { this.upload.onprogress?.({ loaded: 1 }); this.t = setTimeout(() => { st.received.add(n); respond(200, { n }); }, 400); }
      }, 5);
    }
  }
  st.XHR = XHR;
  return st;
}

const run = (file, st, extra = {}) => {
  const states = [];
  const ctl = new AbortController();
  const p = uploadFile(file, { onState: (s) => states.push({ ...s }), signal: ctl.signal, XHR: st.XHR, storage: mkStorage(), backoffMs: 1, stallMs: 80, ...extra });
  return { p, states, ctl };
};

const tests = {
  async 'ruta feliz: pide trozos de 4 MB, progreso creciente y completa'() {
    const st = server();
    const { p, states } = run(mkFile(10 * MB), st);
    const res = await p;
    assert.equal(res.media_id, 'm_1');
    assert.equal(st.chunk, 4 * MB);
    const bytes = states.map((s) => s.bytes);
    assert.ok(bytes.every((b, i) => i === 0 || b >= bytes[i - 1] - 1), 'el progreso no retrocede: ' + bytes);
    assert.ok(bytes.some((b) => b > 0 && b < 10 * MB), 'hay progreso intermedio por bytes (no solo por trozo completo)');
    assert.equal(states.at(-1).phase, 'hecho');
    assert.equal(states.at(-1).bytes, 10 * MB);
  },
  async 'reanuda: solo sube los trozos que faltan'() {
    const st = server({ received: [0, 2] });
    const { p } = run(mkFile(10 * MB), st);
    await p;
    assert.deepEqual(Object.keys(st.attempts), ['1']);
  },
  async 'un corte de red se reintenta y termina'() {
    const st = server({ behavior: { 1: ['net', 'net'] } });
    const { p, states } = run(mkFile(10 * MB), st);
    await p;
    assert.equal(st.attempts[1], 3);
    assert.equal(states.at(-1).retries, 2);
    assert.ok(states.some((s) => /Reintentando el trozo 2\/3/.test(s.message || '')));
  },
  async 'un bloqueo sin avance se detecta, se aborta y se reintenta'() {
    const st = server({ behavior: { 0: ['stall'] } });
    const { p } = run(mkFile(10 * MB), st);
    await p;
    assert.equal(st.attempts[0], 2);
  },
  async 'se rinde tras el máximo de intentos con un error legible'() {
    const st = server({ behavior: { 0: ['net', 'net', 'net'] } });
    const { p } = run(mkFile(10 * MB), st, { maxAttempts: 3 });
    await assert.rejects(p, (e) => e instanceof NetworkError && /conexión/.test(e.message));
    assert.equal(st.completed, 0);
  },
  async 'un 404 (subida caducada) es fatal y no se reintenta'() {
    const st = server({ behavior: { 0: ['404'] } });
    const { p } = run(mkFile(10 * MB), st);
    await assert.rejects(p, (e) => e instanceof ApiError && e.status === 404);
    assert.equal(st.attempts[0], 1);
  },
  async 'cancelar aborta y lanza AbortError'() {
    const st = server({ behavior: { 0: ['slow'], 1: ['slow'], 2: ['slow'] } });
    const { p, ctl } = run(mkFile(10 * MB), st);
    setTimeout(() => ctl.abort(), 60);
    await assert.rejects(p, (e) => e.name === 'AbortError');
    assert.equal(st.completed, 0);
  },
  async 'putChunk reporta errores HTTP con el detalle del servidor'() {
    const st = server({ behavior: { 0: ['404'] } });
    await assert.rejects(putChunk('/api/v1/uploads/up_1/chunks/0', new Blob(['x']), {}, { onBytes() {}, stallMs: 1000, XHR: st.XHR }), (e) => e.message === 'Subida no encontrada');
  },
};

let failed = 0;
for (const [name, fn] of Object.entries(tests)) {
  try { await fn(); console.log('ok   ', name); } catch (e) { failed++; console.log('FALLO', name, '\n     ', e.message); }
}
process.exit(failed ? 1 : 0);
