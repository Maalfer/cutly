// @ts-check
import { useState } from 'preact/hooks';
import { html } from '../html.js';
import { api } from '../api.js';
import { store } from '../store.js';

export function Login() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function submit(/** @type {SubmitEvent} */ e) {
    e.preventDefault();
    const f = new FormData(/** @type {HTMLFormElement} */ (e.target));
    setBusy(true); setError('');
    try {
      await api.post('/auth/login', { json: { username: f.get('username'), password: f.get('password') } });
      store.set({ user: await api.get('/auth/me') });
    } catch (err) {
      setError(/** @type {Error} */ (err).message);
    } finally { setBusy(false); }
  }
  return html`
    <main class="login">
      <form class="card login-card" onSubmit=${submit}>
        <div class="logo big" aria-hidden="true"></div>
        <h1>Cutly</h1>
        <p class="muted">Inicia sesión para editar tus directos.</p>
        <label>Usuario<input name="username" autocomplete="username" required autofocus /></label>
        <label>Contraseña<input name="password" type="password" autocomplete="current-password" required /></label>
        ${error && html`<p class="error" role="alert">${error}</p>`}
        <button class="primary" disabled=${busy}>${busy ? 'Entrando…' : 'Entrar'}</button>
      </form>
    </main>`;
}
