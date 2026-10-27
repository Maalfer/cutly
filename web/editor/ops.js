// @ts-check
// Acciones de edición de alto nivel: añadir capas con valores por defecto, dividir, borrar, duplicar, ordenar…
import { toast } from '../store.js';
import { applyOps, ed, get, layerById, select } from './state.js';
import { outputToSource } from './time.js';

const TEXT_STYLE = { font: 'Poppins', size: 0.05, color: '#FFFFFF', outline_color: '#000000', outline_width: 0.006, bold: true };

export const defaults = {
  text: (/** @type {string} */ text = 'Tu texto') => ({ type: 'text', text, box: { x: 0.5, y: 0.5, w: 0.8 }, style: { ...TEXT_STYLE }, animations: { enter: { name: 'pop', dur: 0.3 }, exit: { name: 'fade', dur: 0.25 } } }),
  icon: (/** @type {string} */ asset) => ({ type: 'icon', asset, box: { x: 0.5, y: 0.5, w: 0.18 }, animations: { enter: { name: 'pop', dur: 0.3 }, exit: { name: 'fade', dur: 0.2 } } }),
  image: (/** @type {string} */ asset) => ({ type: 'image', asset, box: { x: 0.5, y: 0.5, w: 0.5 }, animations: { enter: { name: 'fade', dur: 0.3 } } }),
  shape: () => ({ type: 'shape', shape: 'rect', fill: '#FFD40033', stroke: '#FFD400', stroke_width: 0.004, box: { x: 0.5, y: 0.5, w: 0.5, h: 0.08 }, animations: { enter: { name: 'pop', dur: 0.25 } } }),
  subtitle: () => ({ type: 'subtitle', source: 'transcript', style: { font: 'Poppins', size: 0.045, position_y: 0.72 } }),
  effect: (/** @type {string} */ name, /** @type {any} */ params = {}) => ({ type: 'effect', effect: name, params }),
  scene: (/** @type {string} */ template, /** @type {any} */ params = {}) => ({ type: 'scene', template, params, box: { x: 0.5, y: 0.5, w: 1 } }),
};

/** Añade una capa en el instante actual con la duración dada (acotada al clip) y la selecciona. */
export async function addLayer(/** @type {any} */ layer, dur = 3) {
  const total = get().doc ? get().project.duration : 0;
  const start = Math.min(get().t, Math.max(total - 0.5, 0));
  const end = Math.min(start + dur, total) || start + dur;
  const before = new Set(get().doc.layers.map((/** @type {any} */ l) => l.id));
  const r = await applyOps([{ op: 'add_layer', layer: { start: +start.toFixed(2), end: +end.toFixed(2), ...layer } }]);
  const added = r?.project.layers.find((/** @type {any} */ l) => !before.has(l.id));
  if (added) select('layer', added.id);
  return added || null;
}

export function removeLayer(/** @type {string} */ id) {
  select('none');
  return applyOps([{ op: 'remove_layer', layer_id: id }]);
}

export async function duplicateLayer(/** @type {string} */ id) {
  const l = layerById(id);
  if (!l) return;
  const { id: _drop, ...copy } = l;
  const before = new Set(get().doc.layers.map((/** @type {any} */ x) => x.id));
  if (copy.box) copy.box = { ...copy.box, x: Math.min(copy.box.x + 0.04, 1), y: Math.min(copy.box.y + 0.04, 1) };
  const r = await applyOps([{ op: 'add_layer', layer: { ...copy, name: copy.name ? `${copy.name} (copia)` : null } }]);
  const added = r?.project.layers.find((/** @type {any} */ x) => !before.has(x.id));
  if (added) select('layer', added.id);
}

/** Sube o baja una capa en el orden de apilado (z). */
export function moveLayerZ(/** @type {string} */ id, /** @type {1|-1} */ dir) {
  const layers = [...get().doc.layers].sort((/** @type {any} */ a, /** @type {any} */ b) => a.z - b.z);
  const i = layers.findIndex((/** @type {any} */ l) => l.id === id);
  const other = layers[i + dir];
  if (i < 0 || !other) return;
  const me = layers[i];
  const ops = me.z === other.z
    ? [{ op: 'update_layer', layer_id: id, patch: { z: me.z + dir } }]
    : [{ op: 'update_layer', layer_id: id, patch: { z: other.z } }, { op: 'update_layer', layer_id: other.id, patch: { z: me.z } }];
  return applyOps(ops, 'ordenar capas');
}

export function splitAtPlayhead() {
  const doc = get().doc, t = get().t;
  const r = outputToSource(doc.timeline, t);
  if (!r) return;
  const sel = get().selection;
  const clip = sel.kind === 'clip' ? doc.timeline.find((/** @type {any} */ c) => c.id === sel.id) : r.clip;
  if (!clip) return;
  return applyOps([{ op: 'split_clip', clip_id: clip.id, at_output: +t.toFixed(3) }], 'cortar');
}

export function deleteSelected() {
  const { kind, id } = get().selection;
  if (kind === 'layer' && id) return removeLayer(id);
  if (kind === 'clip' && id) {
    if (get().doc.timeline.length < 2) { toast('Es el único clip del proyecto; no se puede borrar', 'error'); return; }
    select('none');
    return applyOps([{ op: 'delete_clip', clip_id: id }], 'borrar clip');
  }
}

export async function addClip(/** @type {number} */ sourceIn, /** @type {number} */ sourceOut) {
  const r = await applyOps([{ op: 'add_clip', source_in: +sourceIn.toFixed(2), source_out: +sourceOut.toFixed(2) }], 'añadir clip');
  if (r) toast('Clip añadido al final de la línea de tiempo', 'ok');
  return r;
}

export const layerLabel = (/** @type {any} */ l) => l.name || (l.type === 'text' ? l.text.split('\n')[0].slice(0, 24) : l.type === 'effect' ? l.effect : l.type === 'audio' ? '♪ ' + l.sfx : l.type === 'scene' ? (l.template || 'Escena') : l.type === 'icon' || l.type === 'image' ? l.asset.split('/')[1] : l.type === 'subtitle' ? 'Subtítulos' : l.shape === 'ellipse' ? 'Elipse' : 'Rectángulo');
export const TYPE_ICON = /** @type {Record<string,string>} */ ({ text: 'T', icon: '★', image: '▣', shape: '▭', subtitle: '❝', effect: '✦', scene: '◈' });
export { ed };
