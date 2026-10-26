// @ts-check
// Inspector: ajustes del proyecto, del clip seleccionado o de la capa seleccionada (formularios generados del esquema).
import { useEffect, useState } from 'preact/hooks';
import { html } from '../html.js';
import { api } from '../api.js';
import { toast } from '../store.js';
import { applyOps, clipById, ed, get, layerById, patchLayer, patchClip, useEd } from './state.js';
import { removeLayer, duplicateLayer, layerLabel } from './ops.js';

const ANCHORS = ['center', 'top_left', 'top_center', 'top_right', 'bottom_left', 'bottom_center', 'bottom_right'];
const ENTER = ['', 'fade', 'pop', 'zoom', 'zoom_in', 'zoom_out', 'fade_scale', 'scale_up', 'scale_down', 'blur_fade', 'slide_up', 'slide_down', 'slide_left', 'slide_right', 'slide_up_big', 'slide_down_big', 'slide_left_big', 'slide_right_big', 'from_top', 'from_bottom', 'from_left', 'from_right', 'bounce', 'drop', 'spin', 'spin_in', 'rotate', 'flip'];
const LOOPS = ['', 'pulse', 'breathing', 'wiggle', 'float', 'hover', 'blink', 'shake', 'tremble', 'swing', 'zoom_pulse', 'bounce_loop', 'spin_loop'];
const EASINGS = ['linear', 'ease_in', 'ease_out', 'ease_in_out', 'ease_out_back', 'ease_out_bounce', 'ease_out_elastic'];
const TRANSITIONS = ['', 'fade', 'dissolve', 'fadeblack', 'fadewhite', 'wipeleft', 'wiperight', 'wipeup', 'wipedown', 'slideleft', 'slideright', 'slideup', 'slidedown', 'circleopen', 'circleclose', 'zoomin', 'pixelize', 'radial', 'smoothleft', 'smoothright'];
const REFRAME = [['center', 'Centro'], ['facecam', 'Solo cámara'], ['game', 'Solo juego'], ['stack', 'Cámara arriba + juego'], ['custom', 'Personalizado']];

const round = (/** @type {number} */ v, d = 3) => +v.toFixed(d);
/** @param {any} o @param {string} path */
const getp = (o, path) => path.split('.').reduce((a, k) => (a == null ? a : a[k]), o);
/** @param {string} path @param {any} v → patch anidado */
const nest = (path, v) => path.split('.').reduceRight((acc, k) => ({ [k]: acc }), v);

/** Vista previa de una escena: fotogramas generados por el servidor (POST /scenes/preview). */
function ScenePreview({ layer }) {
  const [src, setSrc] = useState('');
  const [busy, setBusy] = useState(false);
  useEffect(() => () => { if (src) URL.revokeObjectURL(src); }, [src]);
  const run = async () => {
    setBusy(true);
    try {
      const dur = layer.end - layer.start;
      const body = layer.template ? { template: layer.template, params: layer.params || {} } : { scene: layer.scene };
      const times = [0.08, 0.3, 0.55, 0.8].map((f) => +(f * dur).toFixed(2));
      const r = await fetch('/api/v1/scenes/preview', { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ...body, duration: dur, times, width: 360, cols: 2 }) });
      if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || r.statusText);
      setSrc(URL.createObjectURL(await r.blob()));
    } catch (e) { toast(/** @type {Error} */ (e).message, 'error'); } finally { setBusy(false); }
  };
  return html`<div><button class="small-btn" disabled=${busy} onClick=${run}>${busy ? 'Generando…' : '▶ Vista previa'}</button>${src && html`<img class="scene-preview" alt="Vista previa de la escena" src=${src} style="width:100%;margin-top:6px;border-radius:6px" />`}</div>`;
}

// --- controles ------------------------------------------------------------------------------------------------------------

function Num({ label, value, min, max, step = 0.01, onInput, unit = '' }) {
  const v = Number.isFinite(value) ? value : 0;
  return html`<label class="field"><span>${label}</span>
    <span class="num"><input type="range" min=${min} max=${max} step=${step} value=${v} onInput=${(/** @type {Event} */ e) => onInput(+(/** @type {HTMLInputElement} */ (e.target).value))} aria-label=${label} />
    <input type="number" min=${min} max=${max} step=${step} value=${round(v, 4)} onChange=${(/** @type {Event} */ e) => { const n = parseFloat(/** @type {HTMLInputElement} */ (e.target).value); if (Number.isFinite(n)) onInput(Math.min(max, Math.max(min, n))); }} />${unit && html`<em>${unit}</em>`}</span></label>`;
}
function Color({ label, value, onInput, nullable = false }) {
  const on = !!value;
  return html`<label class="field"><span>${label}</span><span class="num">
    <input type="color" value=${(value || '#000000').slice(0, 7)} onInput=${(/** @type {Event} */ e) => onInput(/** @type {HTMLInputElement} */ (e.target).value.toUpperCase())} aria-label=${label} />
    ${nullable && html`<label class="inline"><input type="checkbox" checked=${on} onChange=${(/** @type {Event} */ e) => onInput(/** @type {HTMLInputElement} */ (e.target).checked ? '#000000' : null)} /> activo</label>`}</span></label>`;
}
function Check({ label, value, onInput }) {
  return html`<label class="field inline"><input type="checkbox" checked=${!!value} onChange=${(/** @type {Event} */ e) => onInput(/** @type {HTMLInputElement} */ (e.target).checked)} /> <span>${label}</span></label>`;
}
function Sel({ label, value, options, onInput }) {
  return html`<label class="field"><span>${label}</span><select value=${value ?? ''} onChange=${(/** @type {Event} */ e) => onInput(/** @type {HTMLSelectElement} */ (e.target).value)}>
    ${options.map((/** @type {any} */ o) => { const [v, t] = Array.isArray(o) ? o : [o, o || '— ninguna —']; return html`<option value=${v} selected=${v === (value ?? '')}>${t}</option>`; })}</select></label>`;
}
function Group({ title, children, open = true }) {
  return html`<details class="group" open=${open}><summary>${title}</summary><div class="group-body">${children}</div></details>`;
}

// --- proyecto -------------------------------------------------------------------------------------------------------------

const setDoc = (/** @type {string} */ key, /** @type {any} */ patch, /** @type {string} */ op) => {
  const d = get().doc;
  ed.set({ doc: { ...d, [key]: { ...d[key], ...patch } } });
  debounceOp(op, key, patch);
};
/** @type {Record<string, {timer:any, patch:any}>} */
const q = {};
function debounceOp(/** @type {string} */ op, /** @type {string} */ key, /** @type {any} */ patch) {
  const prev = q[op];
  if (prev) clearTimeout(prev.timer);
  const merged = { ...(prev?.patch || {}), ...patch };
  q[op] = { patch: merged, timer: setTimeout(() => { delete q[op]; applyOps([{ op, patch: merged }]); }, 350) };
}

function ProjectPanel() {
  const doc = useEd((s) => s.doc);
  const media = useEd((s) => s.media);
  const presets = useEd((s) => s.presets);
  const rf = doc.reframe, au = doc.audio, co = doc.color, out = doc.output;
  const R = (/** @type {any} */ p) => setDoc('reframe', p, 'set_reframe');
  const rect = (/** @type {'facecam'|'game'} */ k) => {
    const r = rf[k] || { x: 0, y: 0, w: 0.5, h: 0.5 };
    const set = (/** @type {any} */ p) => R({ [k]: { ...r, ...p } });
    return html`<${Group} title=${k === 'facecam' ? 'Región de la cámara (en el vídeo original)' : 'Región del juego (en el vídeo original)'}>
      <${Num} label="X" value=${r.x} min=${0} max=${1} onInput=${(/** @type {number} */ v) => set({ x: Math.min(v, 1 - r.w) })} />
      <${Num} label="Y" value=${r.y} min=${0} max=${1} onInput=${(/** @type {number} */ v) => set({ y: Math.min(v, 1 - r.h) })} />
      <${Num} label="Ancho" value=${r.w} min=${0.05} max=${1} onInput=${(/** @type {number} */ v) => set({ w: Math.min(v, 1 - r.x) })} />
      <${Num} label="Alto" value=${r.h} min=${0.05} max=${1} onInput=${(/** @type {number} */ v) => set({ h: Math.min(v, 1 - r.y) })} />
      ${!rf[k] && html`<p class="muted small">Mueve un control para fijar la región.</p>`}
    <//>`;
  };
  return html`<div class="panel-body">
    <div class="panel-head"><strong>Proyecto</strong><span class="muted small">${out.width}×${out.height} · ${out.fps} fps</span></div>
    <p class="muted small pad">Selecciona un clip o una capa para editarlo. Aquí van los ajustes que afectan a todo el vídeo.</p>
    <${Group} title="Encuadre vertical (9:16)">
      <${Sel} label="Modo" value=${rf.mode} options=${REFRAME} onInput=${(/** @type {string} */ v) => R({ mode: v })} />
      ${(rf.mode === 'center') && html`<${Num} label="Centro horizontal" value=${rf.center_x} min=${0} max=${1} onInput=${(/** @type {number} */ v) => R({ center_x: v })} />`}
      ${(rf.mode === 'facecam' || rf.mode === 'stack' || rf.mode === 'custom') && rect('facecam')}
      ${(rf.mode === 'game' || rf.mode === 'stack' || rf.mode === 'custom') && rect('game')}
      ${rf.mode === 'stack' && html`<${Num} label="Reparto cámara/juego" value=${rf.stack_split} min=${0.1} max=${0.9} onInput=${(/** @type {number} */ v) => R({ stack_split: v })} />
        <${Sel} label="Ajuste del juego" value=${rf.game_fit} options=${['cover', 'contain']} onInput=${(/** @type {string} */ v) => R({ game_fit: v })} />`}
      <p class="muted small">Origen: ${media.metadata?.width}×${media.metadata?.height}</p>
    <//>
    <${Group} title="Color" open=${false}>
      <${Num} label="Brillo" value=${co.brightness} min=${-1} max=${1} onInput=${(/** @type {number} */ v) => setDoc('color', { brightness: v }, 'set_color')} />
      <${Num} label="Contraste" value=${co.contrast} min=${0} max=${3} onInput=${(/** @type {number} */ v) => setDoc('color', { contrast: v }, 'set_color')} />
      <${Num} label="Saturación" value=${co.saturation} min=${0} max=${3} onInput=${(/** @type {number} */ v) => setDoc('color', { saturation: v }, 'set_color')} />
      <${Num} label="Gamma" value=${co.gamma} min=${0.1} max=${3} onInput=${(/** @type {number} */ v) => setDoc('color', { gamma: v }, 'set_color')} />
      <button class="small-btn" onClick=${() => { ed.set({ doc: { ...get().doc, color: { brightness: 0, contrast: 1, saturation: 1, gamma: 1 } } }); applyOps([{ op: 'set_color', patch: { brightness: 0, contrast: 1, saturation: 1, gamma: 1 } }]); }}>Restablecer</button>
    <//>
    <${Group} title="Audio" open=${false}>
      <${Check} label="Normalizar volumen" value=${au.normalize} onInput=${(/** @type {boolean} */ v) => setDoc('audio', { normalize: v }, 'set_audio')} />
      <${Num} label="Volumen objetivo" value=${au.target_lufs} min=${-30} max=${-6} step=${0.5} unit="LUFS" onInput=${(/** @type {number} */ v) => setDoc('audio', { target_lufs: v }, 'set_audio')} />
      <${Num} label="Ganancia extra" value=${au.gain_db} min=${-30} max=${30} step=${0.5} unit="dB" onInput=${(/** @type {number} */ v) => setDoc('audio', { gain_db: v }, 'set_audio')} />
      <${Check} label="Reducir ruido" value=${au.denoise} onInput=${(/** @type {boolean} */ v) => setDoc('audio', { denoise: v }, 'set_audio')} />
    <//>
    <${Group} title="Salida" open=${false}>
      <${Sel} label="Formato" value=${`${out.width}x${out.height}`} options=${[['1080x1920', '9:16 vertical 1080×1920'], ['720x1280', '9:16 vertical 720×1280'], ['1080x1080', '1:1 cuadrado'], ['1920x1080', '16:9 horizontal']]}
        onInput=${(/** @type {string} */ v) => { const [width, height] = v.split('x').map(Number); setDoc('output', { width, height }, 'set_output'); }} />
      <${Sel} label="Fotogramas/s" value=${String(out.fps)} options=${['24', '25', '30', '60']} onInput=${(/** @type {string} */ v) => setDoc('output', { fps: +v }, 'set_output')} />
    <//>
    <${Group} title="Subtítulos: estilos rápidos" open=${false}>
      <${PresetList} kind="subtitle" presets=${presets} />
    <//>
    <${Group} title="Transiciones entre clips" open=${false}>
      <${PresetList} kind="transition" presets=${presets} extra=${{ clip_id: 'all' }} />
    <//>
  </div>`;
}

export async function applyPreset(/** @type {string} */ ref, /** @type {any} */ extra = {}) {
  const pj = get().project;
  try {
    const r = await api.post(`/projects/${pj.id}/presets/apply`, { json: { preset: ref, ...extra } });
    ed.set({ project: r, doc: r.project });
  } catch (e) { toast(/** @type {Error} */ (e).message, 'error'); }
}

function PresetList({ kind, presets, extra = {} }) {
  const items = presets.filter((/** @type {any} */ p) => p.kind === kind);
  if (!items.length) return html`<p class="muted small">Sin presets.</p>`;
  return html`<div class="chips">${items.map((/** @type {any} */ p) => html`<button class="chip" title=${p.description || ''} onClick=${() => applyPreset(`${p.kind}:${p.name}`, extra)}>${p.title || p.name}</button>`)}</div>`;
}

// --- clip -----------------------------------------------------------------------------------------------------------------

function ClipPanel({ id }) {
  useEd((s) => s.doc);
  const c = clipById(id);
  const doc = get().doc, idx = doc.timeline.findIndex((/** @type {any} */ x) => x.id === id);
  const media = get().media;
  if (!c) return null;
  return html`<div class="panel-body">
    <div class="panel-head"><strong>Clip ${idx + 1}</strong><span class="muted small">${((c.source_out - c.source_in) / c.speed).toFixed(1)} s</span></div>
    <${Group} title="Recorte (en el vídeo original)">
      <${Num} label="Inicio" value=${c.source_in} min=${0} max=${media.duration} step=${0.05} unit="s" onInput=${(/** @type {number} */ v) => patchClip(id, { source_in: Math.min(v, c.source_out - 0.2) })} />
      <${Num} label="Fin" value=${c.source_out} min=${0} max=${media.duration} step=${0.05} unit="s" onInput=${(/** @type {number} */ v) => patchClip(id, { source_out: Math.max(v, c.source_in + 0.2) })} />
      <${Num} label="Velocidad" value=${c.speed} min=${0.25} max=${4} step=${0.05} unit="×" onInput=${(/** @type {number} */ v) => patchClip(id, { speed: v })} />
    <//>
    <${Group} title="Transición de entrada">
      ${idx === 0 ? html`<p class="muted small">El primer clip no tiene transición.</p>` : html`
        <${Sel} label="Tipo" value=${c.transition_in?.name || ''} options=${TRANSITIONS} onInput=${(/** @type {string} */ v) => patchClip(id, { transition_in: v ? { name: v, dur: c.transition_in?.dur || 0.4 } : null })} />
        ${c.transition_in && html`<${Num} label="Duración" value=${c.transition_in.dur} min=${0.1} max=${1.5} unit="s" onInput=${(/** @type {number} */ v) => patchClip(id, { transition_in: { ...c.transition_in, dur: v } })} />`}`}
    <//>
    <div class="row-actions">
      <button class="small-btn" disabled=${idx === 0} onClick=${() => applyOps([{ op: 'move_clip', clip_id: id, to_index: idx - 1 }])}>◀ Mover antes</button>
      <button class="small-btn" disabled=${idx === doc.timeline.length - 1} onClick=${() => applyOps([{ op: 'move_clip', clip_id: id, to_index: idx + 1 }])}>Mover después ▶</button>
      <button class="small-btn danger-text" disabled=${doc.timeline.length < 2} onClick=${() => { ed.set({ selection: { kind: 'none', id: null } }); applyOps([{ op: 'delete_clip', clip_id: id }]); }}>Borrar clip</button>
    </div>
  </div>`;
}

// --- capa -----------------------------------------------------------------------------------------------------------------

function SchemaForm({ schema, params, onChange }) {
  const props = Object.entries(schema?.properties || {});
  if (!props.length) return html`<p class="muted small">Este efecto no tiene parámetros.</p>`;
  return props.map(([k, def]) => {
    const d = /** @type {any} */ (def), v = params?.[k] ?? d.default, label = d.title || k;
    if (d.enum) return html`<${Sel} label=${label} value=${v} options=${d.enum} onInput=${(/** @type {string} */ x) => onChange({ [k]: x })} />`;
    if (d.type === 'boolean') return html`<${Check} label=${label} value=${v} onInput=${(/** @type {boolean} */ x) => onChange({ [k]: x })} />`;
    if (d.type === 'number' || d.type === 'integer') {
      const min = d.minimum ?? 0, max = d.maximum ?? Math.max(1, (v || 1) * 4);
      return html`<${Num} label=${label} value=${v} min=${min} max=${max} step=${d.type === 'integer' ? 1 : (max - min) / 100 < 0.01 ? 0.001 : 0.01} onInput=${(/** @type {number} */ x) => onChange({ [k]: x })} />`;
    }
    if (d.type === 'string' && /color|colour/i.test(k)) return html`<${Color} label=${label} value=${v} onInput=${(/** @type {string} */ x) => onChange({ [k]: x })} />`;
    if (d.type === 'string') return html`<label class="field"><span>${label}</span><input type="text" value=${v ?? ''} onInput=${(/** @type {Event} */ e) => onChange({ [k]: /** @type {HTMLInputElement} */ (e.target).value })} /></label>`;
    return null;
  });
}

function LayerPanel({ id }) {
  useEd((s) => s.doc);
  const effects = useEd((s) => s.effects);
  const presets = useEd((s) => s.presets);
  const assets = useEd((s) => s.assets);
  const l = layerById(id);
  if (!l) return null;
  const P = (/** @type {any} */ patch) => patchLayer(id, patch);
  const F = (/** @type {string} */ path, /** @type {any} */ v) => P(nest(path, v));
  const g = (/** @type {string} */ path) => getp(l, path);
  const total = get().project.duration;
  const anim = l.animations || {};
  const fx = l.type === 'effect' ? effects.find((/** @type {any} */ e) => e.name === l.effect) : null;

  const style = () => {
    if (l.type === 'text') return html`<${Group} title="Texto">
      <label class="field"><span>Contenido</span><textarea rows="3" value=${l.text} onInput=${(/** @type {Event} */ e) => { const t = /** @type {HTMLTextAreaElement} */ (e.target).value; if (t.trim()) P({ text: t }); }}></textarea></label>
      <${Sel} label="Fuente" value=${g('style.font')} options=${fontOptions(assets, g('style.font'))} onInput=${(/** @type {string} */ v) => F('style.font', v)} />
      <${Num} label="Tamaño" value=${g('style.size')} min=${0.01} max=${0.3} step=${0.005} onInput=${(/** @type {number} */ v) => F('style.size', v)} />
      <${Color} label="Color" value=${g('style.color')} onInput=${(/** @type {string} */ v) => F('style.color', v)} />
      <${Color} label="Contorno" value=${g('style.outline_color')} onInput=${(/** @type {string} */ v) => F('style.outline_color', v)} />
      <${Num} label="Grosor contorno" value=${g('style.outline_width')} min=${0} max=${0.03} step=${0.001} onInput=${(/** @type {number} */ v) => F('style.outline_width', v)} />
      <${Color} label="Fondo" value=${g('style.bg_color')} nullable onInput=${(/** @type {string|null} */ v) => F('style.bg_color', v)} />
      <${Sel} label="Alineación" value=${g('style.align')} options=${[['left', 'Izquierda'], ['center', 'Centro'], ['right', 'Derecha']]} onInput=${(/** @type {string} */ v) => F('style.align', v)} />
      <div class="two"><${Check} label="Negrita" value=${g('style.bold')} onInput=${(/** @type {boolean} */ v) => F('style.bold', v)} /><${Check} label="Cursiva" value=${g('style.italic')} onInput=${(/** @type {boolean} */ v) => F('style.italic', v)} /><${Check} label="MAYÚSCULAS" value=${g('style.uppercase')} onInput=${(/** @type {boolean} */ v) => F('style.uppercase', v)} /></div>
    <//>`;
    if (l.type === 'subtitle') return html`<${Group} title="Subtítulos">
      <${Sel} label="Fuente" value=${g('style.font')} options=${fontOptions(assets, g('style.font'))} onInput=${(/** @type {string} */ v) => F('style.font', v)} />
      <${Num} label="Tamaño" value=${g('style.size')} min=${0.015} max=${0.2} step=${0.0025} onInput=${(/** @type {number} */ v) => F('style.size', v)} />
      <${Color} label="Color" value=${g('style.color')} onInput=${(/** @type {string} */ v) => F('style.color', v)} />
      <${Color} label="Palabra activa" value=${g('style.highlight_color')} nullable onInput=${(/** @type {string|null} */ v) => F('style.highlight_color', v)} />
      <${Color} label="Contorno" value=${g('style.outline_color')} onInput=${(/** @type {string} */ v) => F('style.outline_color', v)} />
      <${Num} label="Grosor contorno" value=${g('style.outline_width')} min=${0} max=${0.03} step=${0.001} onInput=${(/** @type {number} */ v) => F('style.outline_width', v)} />
      <${Color} label="Fondo" value=${g('style.bg_color')} nullable onInput=${(/** @type {string|null} */ v) => F('style.bg_color', v)} />
      <${Num} label="Posición vertical" value=${g('style.position_y')} min=${0.05} max=${0.95} onInput=${(/** @type {number} */ v) => F('style.position_y', v)} />
      <${Num} label="Palabras por frase" value=${g('style.max_words_per_cue')} min=${1} max=${12} step=${1} onInput=${(/** @type {number} */ v) => F('style.max_words_per_cue', v)} />
      <${Num} label="Líneas máx." value=${g('style.max_lines')} min=${1} max=${3} step=${1} onInput=${(/** @type {number} */ v) => F('style.max_lines', v)} />
      <${Sel} label="Animación" value=${g('style.animation')} options=${[['karaoke', 'Karaoke'], ['pop', 'Pop'], ['none', 'Ninguna']]} onInput=${(/** @type {string} */ v) => F('style.animation', v)} />
      <${Check} label="MAYÚSCULAS" value=${g('style.uppercase')} onInput=${(/** @type {boolean} */ v) => F('style.uppercase', v)} />
      <p class="muted small">Estilos rápidos:</p><${PresetList} kind="subtitle" presets=${presets} extra=${{ layer_id: id }} />
    <//>`;
    if (l.type === 'icon' || l.type === 'image') return html`<${Group} title=${l.type === 'icon' ? 'Icono' : 'Imagen'}>
      <${Sel} label="Recurso" value=${l.asset} options=${assetOptions(assets, l.type, l.asset)} onInput=${(/** @type {string} */ v) => P({ asset: v })} />
      ${l.type === 'icon' && html`<${Color} label="Tinte" value=${l.tint} nullable onInput=${(/** @type {string|null} */ v) => P({ tint: v })} />`}
    <//>`;
    if (l.type === 'shape') return html`<${Group} title="Forma">
      <${Sel} label="Forma" value=${l.shape} options=${[['rect', 'Rectángulo'], ['ellipse', 'Elipse']]} onInput=${(/** @type {string} */ v) => P({ shape: v })} />
      <${Color} label="Relleno" value=${l.fill} nullable onInput=${(/** @type {string|null} */ v) => P({ fill: v })} />
      <${Color} label="Borde" value=${l.stroke} nullable onInput=${(/** @type {string|null} */ v) => P({ stroke: v })} />
      <${Num} label="Grosor borde" value=${l.stroke_width} min=${0} max=${0.05} step=${0.001} onInput=${(/** @type {number} */ v) => P({ stroke_width: v })} />
    <//>`;
    if (l.type === 'scene') return html`<${Group} title="Animación (escena)">
      <p class="muted small">${l.template ? `Plantilla «${l.template}»: se ajusta sola a la duración de la capa.` : 'Escena personalizada (JSON).'}</p>
      ${l.template && html`<label class="field"><span>Parámetros (JSON)</span><textarea rows="5" value=${JSON.stringify(l.params || {}, null, 1)} onChange=${(/** @type {Event} */ e) => { try { P({ params: JSON.parse(/** @type {HTMLTextAreaElement} */ (e.target).value) }); } catch { toast('JSON no válido', 'error'); } }}></textarea></label>`}
      <${Sel} label="Encaje" value=${l.fit} options=${[['contain', 'Contener'], ['cover', 'Cubrir']]} onInput=${(/** @type {string} */ v) => P({ fit: v })} />
      <${ScenePreview} layer=${l} />
    <//>`;
    if (l.type === 'effect') return html`<${Group} title=${fx ? fx.title : l.effect}>
      ${fx && html`<p class="muted small">${fx.description}</p>`}
      <${Sel} label="Efecto" value=${l.effect} options=${effects.map((/** @type {any} */ e) => [e.name, e.title])} onInput=${(/** @type {string} */ v) => P({ effect: v, params: null })} />
      ${fx && html`<${SchemaForm} schema=${fx.params_schema} params=${l.params} onChange=${(/** @type {any} */ p) => P({ params: p })} />`}
      <${Check} label="Limitar a una zona" value=${!!l.region} onInput=${(/** @type {boolean} */ v) => P({ region: v ? { x: 0.1, y: 0.1, w: 0.8, h: 0.4 } : null })} />
      ${l.region && ['x', 'y', 'w', 'h'].map((k) => html`<${Num} label=${{ x: 'Zona X', y: 'Zona Y', w: 'Zona ancho', h: 'Zona alto' }[k]} value=${l.region[k]} min=${k === 'w' || k === 'h' ? 0.05 : 0} max=${1} onInput=${(/** @type {number} */ v) => F('region.' + k, v)} />`)}
    <//>`;
    return null;
  };

  return html`<div class="panel-body">
    <div class="panel-head"><strong>${layerLabel(l)}</strong>
      <span><button class="icon-btn" title="Duplicar (Ctrl+D)" aria-label="Duplicar" onClick=${() => duplicateLayer(id)}>⧉</button><button class="icon-btn danger" title="Borrar (Supr)" aria-label="Borrar capa" onClick=${() => removeLayer(id)}>✕</button></span></div>
    <${Group} title="Tiempo y visibilidad">
      <label class="field"><span>Nombre</span><input type="text" value=${l.name || ''} placeholder=${layerLabel({ ...l, name: null })} onChange=${(/** @type {Event} */ e) => P({ name: /** @type {HTMLInputElement} */ (e.target).value || null })} /></label>
      <${Num} label="Inicio" value=${l.start} min=${0} max=${total} step=${0.05} unit="s" onInput=${(/** @type {number} */ v) => P({ start: Math.min(v, l.end - 0.1) })} />
      <${Num} label="Fin" value=${l.end} min=${0} max=${Math.max(total, l.end)} step=${0.05} unit="s" onInput=${(/** @type {number} */ v) => P({ end: Math.max(v, l.start + 0.1) })} />
      <${Num} label="Opacidad" value=${l.opacity} min=${0} max=${1} onInput=${(/** @type {number} */ v) => P({ opacity: v })} />
      <${Num} label="Orden (z)" value=${l.z} min=${-100} max=${1000} step=${1} onInput=${(/** @type {number} */ v) => P({ z: Math.round(v) })} />
      <${Check} label="Visible" value=${l.visible} onInput=${(/** @type {boolean} */ v) => P({ visible: v })} />
    <//>
    ${style()}
    ${l.box && html`<${Group} title="Posición y tamaño">
      <${Num} label="X" value=${l.box.x} min=${-0.5} max=${1.5} onInput=${(/** @type {number} */ v) => F('box.x', v)} />
      <${Num} label="Y" value=${l.box.y} min=${-0.5} max=${1.5} onInput=${(/** @type {number} */ v) => F('box.y', v)} />
      <${Num} label="Ancho" value=${l.box.w} min=${0.02} max=${2} onInput=${(/** @type {number} */ v) => F('box.w', v)} />
      ${(l.type === 'shape' || l.box.h != null) && html`<${Num} label="Alto" value=${l.box.h ?? 0.1} min=${0.01} max=${2} onInput=${(/** @type {number} */ v) => F('box.h', v)} />`}
      <${Num} label="Rotación" value=${l.box.rotation} min=${-360} max=${360} step=${1} unit="°" onInput=${(/** @type {number} */ v) => F('box.rotation', v)} />
      <${Sel} label="Ancla" value=${l.box.anchor} options=${ANCHORS} onInput=${(/** @type {string} */ v) => F('box.anchor', v)} />
    <//>`}
    ${l.type !== 'effect' && html`<${Group} title="Animación" open=${false}>
      <${Sel} label="Entrada" value=${anim.enter?.name || ''} options=${ENTER} onInput=${(/** @type {string} */ v) => P({ animations: { enter: v ? { name: v, dur: anim.enter?.dur || 0.3 } : null } })} />
      ${anim.enter && html`<${Num} label="Duración entrada" value=${anim.enter.dur} min=${0.05} max=${3} unit="s" onInput=${(/** @type {number} */ v) => P({ animations: { enter: { name: anim.enter.name, dur: v } } })} />`}
      <${Sel} label="Salida" value=${anim.exit?.name || ''} options=${ENTER} onInput=${(/** @type {string} */ v) => P({ animations: { exit: v ? { name: v, dur: anim.exit?.dur || 0.3 } : null } })} />
      ${anim.exit && html`<${Num} label="Duración salida" value=${anim.exit.dur} min=${0.05} max=${3} unit="s" onInput=${(/** @type {number} */ v) => P({ animations: { exit: { name: anim.exit.name, dur: v } } })} />`}
      <${Sel} label="Bucle" value=${anim.loop?.name || ''} options=${LOOPS} onInput=${(/** @type {string} */ v) => P({ animations: { loop: v ? { name: v, period: anim.loop?.period || 1, amount: anim.loop?.amount ?? 0.08 } : null } })} />
      ${anim.loop && html`<${Num} label="Periodo" value=${anim.loop.period} min=${0.2} max=${10} unit="s" onInput=${(/** @type {number} */ v) => P({ animations: { loop: { period: v } } })} />
        <${Num} label="Intensidad" value=${anim.loop.amount} min=${0} max=${1} onInput=${(/** @type {number} */ v) => P({ animations: { loop: { amount: v } } })} />`}
      <${Keyframes} layer=${l} />
      <p class="muted small">Estilos rápidos de animación:</p><${PresetList} kind="animation" presets=${presets} extra=${{ layer_id: id }} />
    <//>`}
  </div>`;
}

function Keyframes({ layer }) {
  const kfs = layer.animations?.keyframes || [];
  const set = (/** @type {any[]} */ list) => patchLayer(layer.id, { animations: { keyframes: list } }, true);
  const t = Math.max(0, +(get().t - layer.start).toFixed(2));
  const cur = { t, x: layer.box?.x, y: layer.box?.y, opacity: layer.opacity, scale: 1, rotation: layer.box?.rotation ?? 0, easing: 'ease_out' };
  return html`<div class="kfs"><strong class="small">Fotogramas clave</strong>
    ${kfs.map((/** @type {any} */ k, /** @type {number} */ i) => html`<div class="kf"><button class="link" onClick=${() => import('./preview.js').then((m) => m.rt.player?.seek(layer.start + k.t))}>${k.t.toFixed(2)} s</button>
      <span class="muted tiny">${['x', 'y', 'scale', 'opacity', 'rotation'].filter((p) => k[p] != null).map((p) => `${p} ${round(k[p], 2)}`).join(' · ')}</span>
      <${Sel} label="" value=${k.easing} options=${EASINGS} onInput=${(/** @type {string} */ v) => set(kfs.map((/** @type {any} */ z, /** @type {number} */ j) => (j === i ? { ...z, easing: v } : z)))} />
      <button class="icon-btn danger" aria-label="Quitar fotograma clave" onClick=${() => set(kfs.filter((/** @type {any} */ _z, /** @type {number} */ j) => j !== i))}>✕</button></div>`)}
    <button class="small-btn" onClick=${() => set([...kfs.filter((/** @type {any} */ k) => Math.abs(k.t - t) > 0.01), cur].sort((a, b) => a.t - b.t))} title="Guarda posición, opacidad y rotación actuales en el instante del cabezal">◆ Añadir en el cabezal</button>
    <p class="muted tiny">Mueve el cabezal, cambia la posición/opacidad de la capa y pulsa «Añadir»: la capa se animará entre los fotogramas.</p></div>`;
}

const fontOptions = (/** @type {any[]} */ assets, /** @type {string} */ cur) => {
  const fams = [...new Set(['default', ...assets.filter((a) => a.kind === 'font').map((a) => a.family || a.name)])];
  if (cur && !fams.includes(cur)) fams.push(cur);
  return fams;
};
const assetOptions = (/** @type {any[]} */ assets, /** @type {string} */ kind, /** @type {string} */ cur) => {
  const list = assets.filter((a) => a.kind === kind || (kind === 'image' && a.kind === 'overlay')).map((a) => [a.id, a.name || a.id]);
  if (cur && !list.some((x) => x[0] === cur)) list.unshift([cur, cur]);
  return list;
};

export function Inspector() {
  const doc = useEd((s) => s.doc);
  const sel = useEd((s) => s.selection);
  if (!doc) return null;
  if (sel.kind === 'layer' && sel.id && layerById(sel.id)) return html`<${LayerPanel} key=${sel.id} id=${sel.id} />`;
  if (sel.kind === 'clip' && sel.id && clipById(sel.id)) return html`<${ClipPanel} key=${sel.id} id=${sel.id} />`;
  return html`<${ProjectPanel} />`;
}
