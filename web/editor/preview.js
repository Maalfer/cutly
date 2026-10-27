// @ts-check
// Vista previa: canvas del compositor + controles de reproducción + selección y arrastre directo de capas.
import { useEffect, useRef } from 'preact/hooks';
import { html } from '../html.js';
import { Player } from './player.js';
import { Stage } from './stage.js';
import { fmtClock } from './time.js';
import { clamp, round } from './geometry.js';
import { ed, get, layerById, patchLayer, select, useEd } from './state.js';
import { isCoarse, isNarrow } from './viewport.js';

/** Instancias compartidas (la línea de tiempo y los atajos mueven el mismo reproductor). */
export const rt = /** @type {{player:Player|null, stage:Stage|null}} */ ({ player: null, stage: null });

export function Preview() {
  const canvas = useRef(/** @type {HTMLCanvasElement|null} */ (null));
  const video = useRef(/** @type {HTMLVideoElement|null} */ (null));
  const media = useEd((s) => s.media);
  const doc = useEd((s) => s.doc);
  const words = useEd((s) => s.words);
  const assets = useEd((s) => s.assets);
  const sel = useEd((s) => s.selection);
  const playing = useEd((s) => s.playing);
  const t = useEd((s) => s.t);
  const total = useEd((s) => s.project?.duration || 0);
  const selId = sel.kind === 'layer' ? sel.id : null;
  const drag = useRef(/** @type {any} */ (null));
  const pts = useRef(/** @type {Map<number,[number,number]>} */ (new Map())); // dedos/punteros activos sobre el escenario
  const big = useEd((s) => s.stageBig);

  useEffect(() => {
    const v = /** @type {HTMLVideoElement} */ (video.current), c = /** @type {HTMLCanvasElement} */ (canvas.current);
    const player = new Player(v), stage = new Stage(c, v);
    rt.player = player; rt.stage = stage;
    let last = 0;
    const draw = () => stage.render(player.t, ed.get().selection.kind === 'layer' ? ed.get().selection.id : null);
    stage.requestRedraw = draw;
    player.onFrame = (tt) => {
      draw();
      const now = performance.now();
      if (now - last > 66 || !player.playing) { last = now; ed.set({ t: tt }); }
    };
    player.onState = (p) => ed.set({ playing: p });
    return () => { player.pause(); stage.dispose(); rt.player = null; rt.stage = null; };
  }, []);

  useEffect(() => { if (media && rt.player) rt.player.setSource(`/api/v1/media/${media.id}/proxy.mp4`); }, [media?.id]);
  useEffect(() => { if (doc && rt.stage && rt.player) { rt.stage.setDoc(doc); rt.player.setTimeline(doc.timeline); rt.stage.render(rt.player.t, selId); } }, [doc]);
  useEffect(() => { rt.stage?.setWords(words); rt.stage?.render(rt.player?.t || 0, selId); }, [words]);
  useEffect(() => { if (assets.length) rt.stage?.loadFonts(assets); }, [assets]);
  useEffect(() => { rt.stage?.render(rt.player?.t || 0, selId); }, [selId]);

  const toCanvas = (/** @type {PointerEvent} */ e) => {
    const c = /** @type {HTMLCanvasElement} */ (canvas.current), r = c.getBoundingClientRect();
    return [((e.clientX - r.left) * c.width) / r.width, ((e.clientY - r.top) * c.height) / r.height];
  };

  const onDown = (/** @type {PointerEvent} */ e) => {
    const stage = rt.stage;
    if (!stage || !doc) return;
    pts.current.set(e.pointerId, [e.clientX, e.clientY]);
    /** @type {HTMLElement} */ (e.currentTarget).setPointerCapture(e.pointerId);
    // Dos dedos sobre una capa seleccionada: pellizcar para cambiar su tamaño.
    if (pts.current.size === 2 && selId) {
      const l = layerById(selId);
      if (l?.box) {
        const [a, b] = [...pts.current.values()];
        drag.current = { mode: 'pinch', id: selId, d0: Math.max(Math.hypot(a[0] - b[0], a[1] - b[1]), 1), w0: l.box.w, h0: l.box.h };
        return;
      }
    }
    if (pts.current.size > 1) return;
    const [x, y] = toCanvas(e);
    const c0 = /** @type {HTMLCanvasElement} */ (canvas.current);
    const grab = (isCoarse() ? 28 : 10) * (c0.width / c0.getBoundingClientRect().width); // radio del asa, en píxeles de canvas
    // ¿asa de redimensionado de la capa seleccionada?
    if (selId) {
      const h = stage.hits.find((q) => q.id === selId);
      if (h) {
        const [x0, y0, x1, y1] = h.rect;
        const corner = [[x0, y0], [x1, y0], [x1, y1], [x0, y1]].some(([cx, cy]) => Math.hypot(cx - x, cy - y) < grab);
        const l = layerById(selId);
        if (corner && l?.box) {
          drag.current = { mode: 'resize', id: selId, cx: (x0 + x1) / 2, cy: (y0 + y1) / 2, d0: Math.hypot(x - (x0 + x1) / 2, y - (y0 + y1) / 2), w0: l.box.w, h0: l.box.h };
          /** @type {HTMLElement} */ (e.currentTarget).setPointerCapture(e.pointerId);
          return;
        }
      }
    }
    const id = stage.hitTest(x, y);
    if (!id) { select('none'); return; }
    const wasSel = id === selId;
    select('layer', id);
    const l = layerById(id);
    drag.current = { mode: 'move', id, x, y, bx: l.box?.x, by: l.box?.y, py: l.style?.position_y, moved: false, wasSel };
    /** @type {HTMLElement} */ (e.currentTarget).setPointerCapture(e.pointerId);
  };

  const onMove = (/** @type {PointerEvent} */ e) => {
    if (pts.current.has(e.pointerId)) pts.current.set(e.pointerId, [e.clientX, e.clientY]);
    const d = drag.current;
    if (!d) return;
    const c = /** @type {HTMLCanvasElement} */ (canvas.current);
    const [x, y] = toCanvas(e);
    if (d.mode === 'pinch') {
      if (pts.current.size < 2) return;
      const [a, b] = [...pts.current.values()];
      const k = Math.hypot(a[0] - b[0], a[1] - b[1]) / d.d0;
      patchLayer(d.id, { box: { w: round(clamp(d.w0 * k, 0.02, 2)), ...(d.h0 ? { h: round(clamp(d.h0 * k, 0.01, 2)) } : {}) } });
      return;
    }
    if (pts.current.size > 1) return;
    if (d.mode === 'move') {
      if (!d.moved && Math.hypot(x - d.x, y - d.y) < 3) return;
      d.moved = true;
      if (d.bx !== undefined) patchLayer(d.id, { box: { x: round(clamp(d.bx + (x - d.x) / c.width, -0.2, 1.2)), y: round(clamp(d.by + (y - d.y) / c.height, -0.2, 1.2)) } });
      else if (d.py !== undefined) patchLayer(d.id, { style: { position_y: round(clamp(d.py + (y - d.y) / c.height, 0.05, 0.95)) } });
    } else {
      const k = Math.hypot(x - d.cx, y - d.cy) / Math.max(d.d0, 1);
      patchLayer(d.id, { box: { w: round(clamp(d.w0 * k, 0.02, 2)), ...(d.h0 ? { h: round(clamp(d.h0 * k, 0.01, 2)) } : {}) } });
    }
  };
  const onUp = (/** @type {PointerEvent} */ e) => {
    pts.current.delete(e.pointerId);
    const d = drag.current;
    // Móvil: tocar (sin arrastrar) una capa ya seleccionada abre sus ajustes.
    if (d?.mode === 'move' && !d.moved && d.wasSel && isNarrow() && e.type === 'pointerup') ed.set({ mtab: 'right' });
    if (pts.current.size === 0 || d?.mode === 'pinch') drag.current = null;
  };

  const fmt = fmtClock;
  return html`
    <div class="preview">
      <div class="stage-wrap">
        <video ref=${video} class="hidden-video" muted=${false} crossorigin="anonymous" playsinline webkit-playsinline preload="auto"></video>
        <canvas ref=${canvas} class="stage-canvas" style=${doc ? `aspect-ratio:${doc.output.width}/${doc.output.height}` : ''}
          onPointerDown=${onDown} onPointerMove=${onMove} onPointerUp=${onUp} onPointerCancel=${onUp} aria-label="Vista previa del clip"></canvas>
      </div>
      <div class="transport" role="group" aria-label="Reproducción">
        <button class="hide-xs" onClick=${() => rt.player?.seek(0)} title="Al principio (Inicio)" aria-label="Al principio">⏮</button>
        <button onClick=${() => rt.player?.seek(get().t - 1 / 30)} title="Fotograma anterior (←)" aria-label="Fotograma anterior">◂</button>
        <button class="primary play" onClick=${() => { const p = rt.player; if (!p) return; if (p.playing) p.pause(); else p.play(); }} title="Reproducir / pausar (Espacio)" aria-label=${playing ? 'Pausar' : 'Reproducir'}>${playing ? '❚❚' : '▶'}</button>
        <button onClick=${() => rt.player?.seek(get().t + 1 / 30)} title="Fotograma siguiente (→)" aria-label="Fotograma siguiente">▸</button>
        <button class="hide-xs" onClick=${() => rt.player?.seek(total)} title="Al final (Fin)" aria-label="Al final">⏭</button>
        <span class="clock" aria-live="off">${fmt(t)} <span class="muted">/ ${fmt(total)}</span></span>
        <button class="show-sm size-toggle" onClick=${() => ed.set({ stageBig: !big })} aria-pressed=${big} aria-label=${big ? 'Reducir la vista previa' : 'Ampliar la vista previa'} title="Ampliar / reducir la vista previa">${big ? '⤡' : '⤢'}</button>
      </div>
    </div>`;
}
