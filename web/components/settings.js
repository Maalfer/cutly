// @ts-check
import { useEffect, useState } from 'preact/hooks';
import { html } from '../html.js';
import { api } from '../api.js';
import { toast } from '../store.js';

const BASE = location.origin;

/** Texto listo para pegar en Claude Code. Si hay clave, la incluye; si no, deja el marcador. */
function agentPrompt(/** @type {string} */ key) {
  return `Tienes acceso a un editor de vídeo mediante API REST.
- URL base: ${BASE}/api/v1
- Autenticación: cabecera "Authorization: Bearer ${key}"
- Primero lee la guía: curl -s -H "Authorization: Bearer ${key}" ${BASE}/api/v1/agent-guide
- OpenAPI: ${BASE}/api/v1/openapi.json
Con eso puedes subir directos, transcribirlos, proponer clips y editarlos. Guarda la clave en la variable CUTLY_API_KEY y no la escribas en ningún archivo del repositorio.`;
}

async function copy(/** @type {string} */ text, /** @type {string} */ what) {
  try { await navigator.clipboard.writeText(text); toast(`${what} copiado`, 'ok'); }
  catch { toast('No se pudo copiar; selecciona el texto a mano', 'error'); }
}

const fmtDate = (/** @type {string|null} */ s) => (s ? new Date(s + (s.endsWith('Z') ? '' : 'Z')).toLocaleString() : '—');

export function Settings() {
  const [keys, setKeys] = useState(/** @type {any[]|null} */ (null));
  const [name, setName] = useState('');
  const [write, setWrite] = useState(true);
  const [created, setCreated] = useState(/** @type {{name:string, token:string}|null} */ (null));
  const [busy, setBusy] = useState(false);

  const load = () => api.get('/api-keys').then(setKeys).catch((e) => toast(e.message, 'error'));
  useEffect(() => { load(); }, []);

  async function create(/** @type {SubmitEvent} */ e) {
    e.preventDefault();
    setBusy(true);
    try {
      const r = await api.post('/api-keys', { json: { name: name.trim(), can_write: write } });
      setCreated({ name: r.name, token: r.token });
      setName('');
      load();
    } catch (err) { toast(/** @type {Error} */ (err).message, 'error'); }
    finally { setBusy(false); }
  }
  async function revoke(/** @type {any} */ k) {
    if (!confirm(`¿Revocar la clave «${k.name}»? Quien la use dejará de tener acceso.`)) return;
    try { await api.del(`/api-keys/${k.id}`); toast('Clave revocada', 'ok'); load(); }
    catch (err) { toast(/** @type {Error} */ (err).message, 'error'); }
  }

  return html`
    <div class="back-row"><a href="#/" class="link">← Volver</a></div>
    <h2 class="page-title">Claves API</h2>
    <p class="muted">Con una clave, Claude Code (o cualquier script) usa los mismos endpoints que esta web para editar vídeos.</p>

    <form class="card" onSubmit=${create}>
      <h3>Nueva clave</h3>
      <label>Nombre<input value=${name} required maxlength="60" placeholder="p. ej. Claude Code portátil" onInput=${(/** @type {Event} */ e) => setName(/** @type {HTMLInputElement} */ (e.target).value)} /></label>
      <label class="check"><input type="checkbox" checked=${write} onChange=${(/** @type {Event} */ e) => setWrite(/** @type {HTMLInputElement} */ (e.target).checked)} /> Permiso de escritura (subir, transcribir, editar, borrar)</label>
      <p class="muted small">Sin escritura, la clave solo puede consultar.</p>
      <button class="primary" disabled=${busy || !name.trim()}>Crear clave</button>
    </form>

    ${created && html`<section class="card created" role="alert">
      <h3>Clave «${created.name}» creada</h3>
      <p class="error small"><strong>Cópiala ahora:</strong> no se vuelve a mostrar.</p>
      <code class="token">${created.token}</code>
      <div class="actions">
        <button class="primary" onClick=${() => copy(created.token, 'Clave')}>Copiar clave</button>
        <button onClick=${() => copy(agentPrompt(created.token), 'Instrucciones')}>Copiar instrucciones para Claude Code</button>
        <button class="link" onClick=${() => setCreated(null)}>Ocultar</button>
      </div>
    </section>`}

    <h3>Tus claves</h3>
    ${keys === null ? html`<p class="muted">Cargando…</p>`
      : keys.length === 0 ? html`<p class="muted">Aún no has creado ninguna clave.</p>`
      : html`<ul class="keys">${keys.map((k) => html`<li class="card" key=${k.id}>
          <div class="row"><strong class="name">${k.name}</strong>
            <span class=${'badge ' + (k.revoked ? 'error' : 'ready')}>${k.revoked ? 'Revocada' : 'Activa'}</span></div>
          <p class="muted small"><code>${k.prefix}…</code> · ${k.can_write ? 'Lectura y escritura' : 'Solo lectura'}</p>
          <p class="muted small">Creada: ${fmtDate(k.created_at)} · Último uso: ${fmtDate(k.last_used_at)}</p>
          ${!k.revoked && html`<button class="danger small-btn" onClick=${() => revoke(k)}>Revocar</button>`}
        </li>`)}</ul>`}

    <section class="card">
      <h3>Cómo usarla con Claude Code</h3>
      <ol class="steps">
        <li>Crea una clave con escritura y copia las <em>instrucciones para Claude Code</em>.</li>
        <li>Pégalas en Claude Code. Le indican la URL, cómo autenticarse y dónde está la guía.</li>
        <li>Para subir directos grandes desde tu equipo: <code>curl -sO ${BASE}/tools/upload.py</code> y <code>python3 upload.py directo.mkv --wait</code> (reanudable).</li>
      </ol>
      <div class="actions">
        <a class="link" href="/api/v1/agent-guide" target="_blank" rel="noopener">Guía para agentes</a>
        <a class="link" href="/api/v1/docs" target="_blank" rel="noopener">Documentación OpenAPI</a>
        <button class="link" onClick=${() => copy(agentPrompt('<TU_CLAVE>'), 'Instrucciones')}>Copiar instrucciones (sin clave)</button>
      </div>
    </section>`;
}
