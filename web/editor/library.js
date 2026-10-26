// @ts-check
// Biblioteca: iconos, imágenes, efectos y presets de capa/texto para añadir con un clic en el instante actual.
import { useEffect, useState } from 'preact/hooks';
import { html } from '../html.js';
import { api } from '../api.js';
import { toast } from '../store.js';
import { addLayer, defaults } from './ops.js';
import { ed, get, useEd } from './state.js';
import { applyPreset } from './inspector.js';

const TABS = /** @type {[string,string][]} */ ([['icon', 'Iconos'], ['image', 'Imágenes'], ['effect', 'Efectos'], ['scene', 'Animaciones'], ['preset', 'Presets'], ['font', 'Fuentes']]);

async function uploadAsset(/** @type {File} */ file, /** @type {string} */ kind) {
  const name = file.name.replace(/\.[^.]+$/, '').toLowerCase().replace(/[^a-z0-9_-]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 40) || 'asset';
  const license = prompt('¿De dónde sale este archivo / qué licencia tiene? (obligatorio)', 'propio');
  if (!license) return;
  try {
    await api.post(`/assets?name=${encodeURIComponent(name)}&kind=${kind}&license=${encodeURIComponent(license)}&replace=true`, { body: file, headers: { 'Content-Type': 'application/octet-stream' } });
    ed.set({ assets: (await api.get('/assets?limit=500')).assets });
    toast('Recurso subido', 'ok');
  } catch (e) { toast(/** @type {Error} */ (e).message, 'error'); }
}

export function Library() {
  const assets = useEd((s) => s.assets);
  const effects = useEd((s) => s.effects);
  const presets = useEd((s) => s.presets);
  const [tab, setTab] = useState('icon');
  const [q, setQ] = useState('');
  const [scenes, setScenes] = useState(/** @type {any[]} */ ([]));
  useEffect(() => { api.get('/scenes/templates').then((/** @type {any} */ r) => setScenes(r.templates)).catch(() => {}); }, []);
  const ql = q.trim().toLowerCase();
  const match = (/** @type {string} */ ...f) => !ql || f.join(' ').toLowerCase().includes(ql);

  const items = assets.filter((/** @type {any} */ a) => (tab === 'image' ? a.kind === 'image' || a.kind === 'overlay' : a.kind === tab) && match(a.id, (a.tags || []).join(' '), a.description || ''));
  return html`<div class="panel-body library">
    <div class="subtabs" role="tablist">${TABS.map(([id, label]) => html`<button role="tab" class=${tab === id ? 'on' : ''} aria-selected=${tab === id} onClick=${() => setTab(id)}>${label}</button>`)}</div>
    <input type="search" class="search" placeholder="Buscar…" value=${q} onInput=${(/** @type {Event} */ e) => setQ(/** @type {HTMLInputElement} */ (e.target).value)} aria-label="Buscar en la biblioteca" />
    ${(tab === 'icon' || tab === 'image') && html`
      <div class="grid-assets">${items.map((/** @type {any} */ a) => html`<button class="asset" key=${a.id} title=${`${a.id} — ${a.description || ''}`}
          onClick=${() => addLayer(tab === 'icon' ? defaults.icon(a.id) : defaults.image(a.id), 3)}>
          <img loading="lazy" alt=${a.description || a.id} src=${`/api/v1/assets/preview/${a.id}?size=96`} /><span>${a.id.split('/').pop()}</span></button>`)}</div>
      ${!items.length && html`<p class="muted small pad">Nada que mostrar.</p>`}
      <label class="small-btn upload-btn">⬆ Subir ${tab === 'icon' ? 'icono (SVG)' : 'imagen (PNG/JPG/WebP)'}
        <input type="file" hidden accept=${tab === 'icon' ? '.svg,image/svg+xml' : 'image/png,image/jpeg,image/webp'} onChange=${(/** @type {Event} */ e) => { const f = /** @type {HTMLInputElement} */ (e.target).files?.[0]; if (f) uploadAsset(f, tab); /** @type {HTMLInputElement} */ (e.target).value = ''; }} /></label>`}
    ${tab === 'font' && html`<ul class="plain">${items.map((/** @type {any} */ a) => html`<li key=${a.id}><strong style=${`font-family:'${a.family}'`}>${a.family}</strong> <span class="muted small">${a.id.split('/').pop()}</span><br /><span class="muted tiny">${a.description}</span></li>`)}</ul>
      <label class="small-btn upload-btn">⬆ Subir fuente (TTF/OTF)<input type="file" hidden accept=".ttf,.otf" onChange=${(/** @type {Event} */ e) => { const f = /** @type {HTMLInputElement} */ (e.target).files?.[0]; if (f) uploadAsset(f, 'font'); /** @type {HTMLInputElement} */ (e.target).value = ''; }} /></label>`}
    ${tab === 'effect' && html`<ul class="plain rows">${effects.filter((/** @type {any} */ e) => match(e.name, e.title, e.description, (e.tags || []).join(' '))).map((/** @type {any} */ e) => html`<li key=${e.name}>
        <button class="row-btn" onClick=${() => addLayer({ ...defaults.effect(e.name, e.example_layer?.params || {}) }, Math.min(2, Math.max(0.5, get().project.duration - get().t)))}>
          <strong>${e.title}</strong> <span class="badge">${e.category}</span><br /><span class="muted small">${e.description}</span></button></li>`)}</ul>`}
    ${tab === 'scene' && html`<ul class="plain rows">${scenes.filter((/** @type {any} */ s) => match(s.name, s.title, s.description, (s.tags || []).join(' '))).map((/** @type {any} */ s) => html`<li key=${s.name}>
        <button class="row-btn" onClick=${() => addLayer(defaults.scene(s.name, s.example_layer?.params || {}), Math.min(s.recommended_duration, Math.max(s.min_duration, get().project.duration - get().t)))}>
          <strong>${s.title}</strong> <span class="badge">${Math.round(s.recommended_duration)} s</span><br /><span class="muted small">${s.description}</span></button></li>`)}</ul>
      ${!scenes.length && html`<p class="muted small pad">Cargando animaciones…</p>`}
      <p class="muted tiny pad">Animaciones generadas en el servidor (se ven al renderizar o con «Vista previa» en el inspector).</p>`}
    ${tab === 'preset' && html`<ul class="plain rows">${presets.filter((/** @type {any} */ p) => ['layer', 'text', 'color'].includes(p.kind) && match(p.name, p.description || '', p.kind)).map((/** @type {any} */ p) => html`<li key=${p.kind + p.name}>
        <button class="row-btn" onClick=${() => applyPreset(`${p.kind}:${p.name}`, { start: +get().t.toFixed(2), end: +Math.min(get().t + 3, get().project.duration).toFixed(2) })}>
          <strong>${p.name.replace(/_/g, ' ')}</strong> <span class="badge">${p.kind}</span><br /><span class="muted small">${p.description}</span></button></li>`)}</ul>
      <p class="muted tiny pad">Los estilos de subtítulos, animaciones y transiciones están en el panel de ajustes.</p>`}
  </div>`;
}
