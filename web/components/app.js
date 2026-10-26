// @ts-check
import { useEffect } from 'preact/hooks';
import { html } from '../html.js';
import { api } from '../api.js';
import { navigate, store, useStore } from '../store.js';
import { Login } from './login.js';
import { Library } from './library.js';
import { MediaPage } from './media.js';
import { Settings } from './settings.js';
import { Editor } from '../editor/editor.js';

function Toasts() {
  const toasts = useStore((s) => s.toasts);
  return html`<div class="toasts" role="status" aria-live="polite">${toasts.map((t) => html`<div key=${t.id} class=${'toast ' + t.kind}>${t.text}</div>`)}</div>`;
}

export function App() {
  const user = useStore((s) => s.user);
  const route = useStore((s) => s.route);
  useEffect(() => {
    api.get('/auth/me').then((u) => store.set({ user: u })).catch(() => store.set({ user: null }));
  }, []);

  if (user === undefined) return html`<p class="boot">Cargando…</p>`;
  if (user === null) return html`<${Login} /><${Toasts} />`;

  if (route.name === 'editor' && route.id) return html`<${Editor} mediaId=${route.id} key=${route.id} /><${Toasts} />`;

  async function logout() {
    await api.post('/auth/logout').catch(() => {});
    store.set({ user: null });
  }
  return html`
    <header class="topbar">
      <a class="brand" href="#/" onClick=${(/** @type {Event} */ e) => { e.preventDefault(); navigate('/'); }}><span class="logo" aria-hidden="true"></span> Cutly</a>
      <span class="grow"></span>
      <span class="muted small user">${user.name}</span>
      <a class="link small" href="#/settings">Claves API</a>
      <button class="link" onClick=${logout}>Salir</button>
    </header>
    <main class="container">
      ${route.name === 'media' && route.id ? html`<${MediaPage} id=${route.id} key=${route.id} />`
        : route.name === 'settings' ? html`<${Settings} />` : html`<${Library} />`}
    </main>
    <${Toasts} />`;
}
