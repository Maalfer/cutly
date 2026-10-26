// @ts-check
// Panel de capas: lista (orden de apilado), visibilidad, selección, ordenar, borrar y menú «Añadir».
import { useState } from 'preact/hooks';
import { html } from '../html.js';
import { defaults, addLayer, duplicateLayer, layerLabel, moveLayerZ, removeLayer, TYPE_ICON } from './ops.js';
import { ed, patchLayer, select, useEd } from './state.js';
import { fmtClock } from './time.js';

export function LayersPanel() {
  const doc = useEd((s) => s.doc);
  const sel = useEd((s) => s.selection);
  const effects = useEd((s) => s.effects);
  const [menu, setMenu] = useState(false);
  if (!doc) return null;
  const layers = [...doc.layers].map((/** @type {any} */ l, /** @type {number} */ i) => ({ l, i })).sort((a, b) => b.l.z - a.l.z || b.i - a.i);
  const add = async (/** @type {any} */ layer, /** @type {number} */ dur = 3) => { setMenu(false); await addLayer(layer, dur); };

  return html`
    <div class="panel-body layers">
      <div class="panel-head">
        <strong>Capas</strong>
        <div class="menu-anchor">
          <button class="primary small-btn" onClick=${() => setMenu(!menu)} aria-expanded=${menu} aria-haspopup="menu">+ Añadir</button>
          ${menu && html`<div class="menu" role="menu" onMouseLeave=${() => setMenu(false)}>
            <button role="menuitem" onClick=${() => add(defaults.text())}><span class="ico">T</span> Texto</button>
            <button role="menuitem" onClick=${() => add(defaults.shape())}><span class="ico">▭</span> Forma (rectángulo)</button>
            <button role="menuitem" onClick=${() => { ed.set({ left: 'library' }); setMenu(false); }}><span class="ico">★</span> Icono o imagen…</button>
            <button role="menuitem" onClick=${() => add(defaults.subtitle(), doc.layers.length ? 3 : 999)}><span class="ico">❝</span> Subtítulos</button>
            <button role="menuitem" onClick=${() => { ed.set({ left: 'library' }); setMenu(false); }}><span class="ico">✦</span> Efecto…</button>
          </div>`}
        </div>
      </div>
      ${layers.length === 0 && html`<p class="muted small pad">Aún no hay capas. Añade texto, iconos, formas, subtítulos o efectos.</p>`}
      <ul class="layer-list">
        ${layers.map(({ l }) => html`<li key=${l.id} class=${'layer-row' + (sel.kind === 'layer' && sel.id === l.id ? ' sel' : '') + (l.visible ? '' : ' off')}
            onClick=${() => select('layer', l.id)}>
          <span class=${'type t-' + l.type} title=${l.type}>${TYPE_ICON[l.type] || '?'}</span>
          <span class="lbl" title=${`${layerLabel(l)} (${fmtClock(l.start)}–${fmtClock(l.end)})`}>${layerLabel(l)}</span>
          <button class="icon-btn" title=${l.visible ? 'Ocultar' : 'Mostrar'} aria-label=${l.visible ? 'Ocultar capa' : 'Mostrar capa'} onClick=${(/** @type {Event} */ e) => { e.stopPropagation(); patchLayer(l.id, { visible: !l.visible }, true); }}>${l.visible ? '👁' : '◌'}</button>
          <button class="icon-btn" title="Subir (por encima)" aria-label="Subir capa" onClick=${(/** @type {Event} */ e) => { e.stopPropagation(); moveLayerZ(l.id, 1); }}>▲</button>
          <button class="icon-btn" title="Bajar" aria-label="Bajar capa" onClick=${(/** @type {Event} */ e) => { e.stopPropagation(); moveLayerZ(l.id, -1); }}>▼</button>
          <button class="icon-btn" title="Duplicar" aria-label="Duplicar capa" onClick=${(/** @type {Event} */ e) => { e.stopPropagation(); duplicateLayer(l.id); }}>⧉</button>
          <button class="icon-btn danger" title="Borrar (Supr)" aria-label="Borrar capa" onClick=${(/** @type {Event} */ e) => { e.stopPropagation(); removeLayer(l.id); }}>✕</button>
        </li>`)}
      </ul>
      <span hidden>${effects.length}</span>
    </div>`;
}
