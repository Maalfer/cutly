// @ts-check
// Cliente de la API /api/v1. La web usa exactamente los mismos endpoints que Claude (MCP).
const BASE = '/api/v1';

/** main.js conecta aquí lo que ocurre ante un 401 (sesión caducada). */
export const hooks = { onUnauthorized: () => {} };

export class ApiError extends Error {
  /** @param {number} status @param {string} detail */
  constructor(status, detail) { super(detail); this.status = status; }
}

/** @param {string} method @param {string} path @param {{json?:any, body?:BodyInit, headers?:Record<string,string>, signal?:AbortSignal}} [o] */
async function request(method, path, o = {}) {
  /** @type {RequestInit} */
  const opts = { method, headers: { ...o.headers }, credentials: 'same-origin', signal: o.signal };
  if (o.json !== undefined) {
    opts.body = JSON.stringify(o.json);
    /** @type {any} */ (opts.headers)['Content-Type'] = 'application/json';
  } else if (o.body !== undefined) opts.body = o.body;
  const r = await fetch(BASE + path, opts);
  if (!r.ok) {
    if (r.status === 401 && !path.startsWith('/auth/')) hooks.onUnauthorized();
    let detail = r.statusText;
    try { const j = await r.json(); detail = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail); } catch { /* sin cuerpo JSON */ }
    throw new ApiError(r.status, detail);
  }
  return r.json();
}

export const api = {
  get: (/** @type {string} */ p, /** @type {any} */ o) => request('GET', p, o),
  post: (/** @type {string} */ p, /** @type {any} */ o) => request('POST', p, o),
  put: (/** @type {string} */ p, /** @type {any} */ o) => request('PUT', p, o),
  patch: (/** @type {string} */ p, /** @type {any} */ o) => request('PATCH', p, o),
  del: (/** @type {string} */ p, /** @type {any} */ o) => request('DELETE', p, o),
};
