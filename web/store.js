// @ts-check
// Estado centralizado con suscripciones. Los componentes se suscriben a una porción (selector).
import { useEffect, useState } from 'preact/hooks';

/** @template T @param {T} initial */
export function createStore(initial) {
  let state = initial;
  const subs = new Set();
  return {
    get: () => state,
    /** @param {Partial<T>} patch */
    set(patch) { state = { ...state, ...patch }; subs.forEach((f) => f(state)); },
    /** @param {(s:T)=>void} f */
    subscribe(f) { subs.add(f); return () => subs.delete(f); },
  };
}

export const store = createStore({
  /** @type {undefined|null|{name:string,kind:string,can_write:boolean}} undefined = comprobando, null = sin sesión */
  user: undefined,
  route: parseRoute(),
  /** @type {{id:number,text:string,kind:string}[]} */
  toasts: [],
});

/** @template R @param {(s:ReturnType<typeof store.get>)=>R} selector @returns {R} */
export function useStore(selector) {
  const [v, setV] = useState(() => selector(store.get()));
  useEffect(() => store.subscribe((s) => setV(() => selector(s))), []);
  return v;
}

export function parseRoute() {
  const parts = location.hash.replace(/^#\/?/, '').split('/').filter(Boolean);
  return { name: parts[0] || 'library', id: parts[1] || null, rest: parts.slice(2) };
}
addEventListener('hashchange', () => store.set({ route: parseRoute() }));
export const navigate = (/** @type {string} */ path) => { location.hash = path; };

let toastId = 0;
export function toast(/** @type {string} */ text, kind = 'info') {
  const id = ++toastId;
  store.set({ toasts: [...store.get().toasts, { id, text, kind }] });
  setTimeout(() => store.set({ toasts: store.get().toasts.filter((t) => t.id !== id) }), kind === 'error' ? 7000 : 3500);
}
