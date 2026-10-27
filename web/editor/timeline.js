// @ts-check
// Línea de tiempo en canvas: regla, clips con forma de onda, filas de capas, cabezal; arrastrar, recortar, zoom y desplazamiento.
import { useEffect, useRef } from 'preact/hooks';
import { html } from '../html.js';
import { api } from '../api.js';
import { rt } from './preview.js';
import { applyOps, clipById, ed, get, patchLayer, select, useEd } from './state.js';
import { clipDuration, fmtClock, timelineDuration, timelineStarts } from './time.js';
import { splitAtPlayhead, deleteSelected, TYPE_ICON, layerLabel } from './ops.js';
import { isCoarse } from './viewport.js';

// Medidas en píxeles CSS. Con dedos (puntero grueso) todo es más alto y las asas de recorte más anchas.
let RULER = 24, CLIP_H = 50, ROW = 24, PAD = 6, EDGE = 7, SNAP_PX = 7;
function applyDims() {
  const t = isCoarse();
  RULER = t ? 30 : 24; CLIP_H = t ? 60 : 50; ROW = t ? 34 : 24; EDGE = t ? 16 : 7; SNAP_PX = t ? 10 : 7;
}
const COLORS = /** @type {Record<string,string>} */ ({ text: '#4f8cff', icon: '#e6a23c', image: '#b07cff', shape: '#3ec9a7', subtitle: '#ff6b81', effect: '#f0c040', scene: '#35d0ff', audio: '#8bd450' });

/** @param {string} v */
const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();

export function Timeline() {
  const doc = useEd((s) => s.doc);
  const wrap = useRef(/** @type {HTMLDivElement|null} */ (null));
  const cv = useRef(/** @type {HTMLCanvasElement|null} */ (null));
  const ptr = useRef(/** @type {Map<number,[number,number]>} */ (new Map())); // dedos activos (pellizco)
  const view = useRef({ w: 600, h: 200, rows: /** @type {any[]} */ ([]), peaks: /** @type {Map<string,any>} */ (new Map()), drag: /** @type {any} */ (null) });
  const raf = useRef(0);
  const redraw = () => { cancelAnimationFrame(raf.current); raf.current = requestAnimationFrame(draw); };

  // --- geometría ---
  const x2t = (/** @type {number} */ x) => get().scroll + x / get().zoom;
  const t2x = (/** @type {number} */ t) => (t - get().scroll) * get().zoom;
  const layerRows = () => [...get().doc.layers].sort((a, b) => b.z - a.z);

  function layout() {
    applyDims();
    const d = get().doc;
    const rows = d ? layerRows() : [];
    const h = RULER + CLIP_H + PAD + Math.max(rows.length, 1) * ROW + PAD * 2;
    view.current.rows = rows;
    view.current.h = h;
    const c = cv.current, w = wrap.current;
    if (!c || !w) return;
    view.current.w = w.clientWidth;
    const dpr = devicePixelRatio || 1;
    c.width = Math.round(view.current.w * dpr); c.height = Math.round(h * dpr);
    c.style.width = view.current.w + 'px'; c.style.height = h + 'px';
    // si hay más filas de las que caben, el dedo debe poder desplazar en vertical; si no, todo el gesto es nuestro
    c.style.touchAction = h > w.clientHeight ? 'pan-y' : 'none';
  }

  function snapPoints(/** @type {string} */ skip) {
    const d = get().doc, pts = [0, get().t];
    const starts = timelineStarts(d.timeline);
    d.timeline.forEach((/** @type {any} */ c, /** @type {number} */ i) => { pts.push(starts[i], starts[i] + clipDuration(c)); });
    d.layers.forEach((/** @type {any} */ l) => { if (l.id !== skip) pts.push(l.start, l.end); });
    return pts;
  }
  const snap = (/** @type {number} */ t, /** @type {string} */ skip) => {
    let best = t, bd = SNAP_PX / get().zoom;
    for (const p of snapPoints(skip)) if (Math.abs(p - t) < bd) { bd = Math.abs(p - t); best = p; }
    return best;
  };

  // --- forma de onda ---
  async function loadPeaks() {
    const d = get().doc, m = get().media;
    if (!d || !m?.has_peaks) return;
    const starts = timelineStarts(d.timeline);
    for (let i = 0; i < d.timeline.length; i++) {
      const c = d.timeline[i];
      const bins = Math.min(4000, Math.max(50, Math.round(clipDuration(c) * get().zoom)));
      const key = `${c.source_in}|${c.source_out}|${Math.round(bins / 50)}`;
      if (view.current.peaks.has(key)) continue;
      view.current.peaks.set(key, null);
      api.get(`/media/${m.id}/peaks?start=${c.source_in}&end=${c.source_out}&bins=${bins}`).then((p) => { view.current.peaks.set(key, p); redraw(); }).catch(() => {});
    }
    void starts;
  }

  function draw() {
    const c = cv.current, d = get().doc;
    if (!c || !d) return;
    layout();
    const g = /** @type {CanvasRenderingContext2D} */ (c.getContext('2d'));
    const dpr = devicePixelRatio || 1, { w, h, rows } = view.current;
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    g.clearRect(0, 0, w, h);
    const fg = css('--text') || '#ddd', mut = css('--muted') || '#888', line = css('--border') || '#333', accent = css('--accent') || '#4f8cff';
    const st = get(), total = timelineDuration(d.timeline), z = st.zoom;

    // regla
    g.fillStyle = css('--surface-2') || '#1b1f27'; g.fillRect(0, 0, w, RULER);
    const steps = [0.1, 0.2, 0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300, 600];
    const step = steps.find((s) => s * z >= 70) || 600;
    g.font = '11px system-ui, sans-serif'; g.textBaseline = 'middle';
    for (let t = Math.floor(st.scroll / step) * step; t < st.scroll + w / z + step; t += step) {
      const x = Math.round(t2x(t)) + 0.5;
      g.strokeStyle = line; g.beginPath(); g.moveTo(x, RULER - 8); g.lineTo(x, RULER); g.stroke();
      g.fillStyle = mut; g.fillText(fmtClock(t), x + 3, RULER / 2 - 1);
    }

    // clips
    const starts = timelineStarts(d.timeline);
    d.timeline.forEach((/** @type {any} */ cl, /** @type {number} */ i) => {
      const x0 = t2x(starts[i]), wd = clipDuration(cl) * z, y = RULER + 2;
      if (x0 > w || x0 + wd < 0) return;
      const sel = st.selection.kind === 'clip' && st.selection.id === cl.id;
      g.fillStyle = sel ? '#2d4f86' : '#26324a'; g.fillRect(x0, y, wd, CLIP_H - 4);
      // onda
      const bins = Math.min(4000, Math.max(50, Math.round(clipDuration(cl) * z)));
      const pk = view.current.peaks.get(`${cl.source_in}|${cl.source_out}|${Math.round(bins / 50)}`);
      if (pk?.count) {
        g.fillStyle = sel ? '#9ec0ff' : '#6f88b8';
        const mid = y + (CLIP_H - 4) / 2, amp = (CLIP_H - 8) / 2;
        for (let px = Math.max(0, Math.floor(-x0)); px < Math.min(wd, w - x0); px++) {
          const k = Math.min(pk.count - 1, Math.floor((px / wd) * pk.count));
          const lo = pk.min[k] / pk.scale, hi = pk.max[k] / pk.scale;
          g.fillRect(x0 + px, mid - hi * amp, 1, Math.max(1, (hi - lo) * amp));
        }
      }
      g.strokeStyle = sel ? accent : line; g.lineWidth = sel ? 2 : 1; g.strokeRect(x0 + 0.5, y + 0.5, wd - 1, CLIP_H - 5);
      g.fillStyle = fg; g.fillText(`${fmtClock(cl.source_in)} → ${fmtClock(cl.source_out)}${cl.speed !== 1 ? `  ×${cl.speed}` : ''}`, x0 + 8, y + 10);
      // asas de recorte
      const hw = isCoarse() ? 8 : 4;
      g.fillStyle = 'rgba(255,255,255,.35)'; g.fillRect(x0, y, hw, CLIP_H - 4); g.fillRect(x0 + wd - hw, y, hw, CLIP_H - 4);
      if (cl.transition_in && i > 0) { g.fillStyle = '#ffffff55'; const tw = cl.transition_in.dur * z; g.fillRect(x0, y, tw, CLIP_H - 4); g.fillStyle = fg; g.fillText('⇄', x0 + 4, y + CLIP_H - 14); }
    });

    // capas
    rows.forEach((/** @type {any} */ l, /** @type {number} */ r) => {
      const y = RULER + CLIP_H + PAD + r * ROW, x0 = t2x(l.start), wd = Math.max(4, (l.end - l.start) * z);
      g.fillStyle = r % 2 ? 'rgba(255,255,255,.02)' : 'rgba(255,255,255,.04)'; g.fillRect(0, y, w, ROW);
      const sel = st.selection.kind === 'layer' && st.selection.id === l.id;
      g.globalAlpha = l.visible ? 1 : 0.35;
      g.fillStyle = COLORS[l.type] || '#888'; g.fillRect(x0, y + 2, wd, ROW - 4);
      if (sel) { g.strokeStyle = '#fff'; g.lineWidth = 2; g.strokeRect(x0 + 1, y + 3, wd - 2, ROW - 6); }
      g.save(); g.beginPath(); g.rect(x0, y, wd, ROW); g.clip();
      g.fillStyle = '#111'; g.fillText(`${TYPE_ICON[l.type] || ''} ${layerLabel(l)}`, Math.max(x0, 0) + 6, y + ROW / 2);
      g.restore(); g.globalAlpha = 1;
    });
    if (!rows.length) { g.fillStyle = mut; g.fillText('Las capas (texto, iconos, efectos, subtítulos) aparecen aquí', 10, RULER + CLIP_H + PAD + ROW / 2); }

    // fin del clip
    const xe = t2x(total);
    g.fillStyle = 'rgba(0,0,0,.35)'; if (xe < w) g.fillRect(xe, RULER, w - xe, h - RULER);

    // problemas detectados
    for (const i of st.issues) {
      const t = typeof i.t === 'number' ? i.t : typeof i.start === 'number' ? i.start : null;
      if (t == null) continue;
      g.fillStyle = i.severity === 'error' ? '#ff4d4f' : i.severity === 'warning' ? '#faad14' : '#8c8c8c';
      g.beginPath(); g.moveTo(t2x(t) - 4, 0); g.lineTo(t2x(t) + 4, 0); g.lineTo(t2x(t), 7); g.fill();
    }

    // cabezal
    const px = Math.round(t2x(st.t)) + 0.5;
    g.strokeStyle = '#ff3b30'; g.lineWidth = 1.5; g.beginPath(); g.moveTo(px, 0); g.lineTo(px, h); g.stroke();
    g.fillStyle = '#ff3b30'; g.beginPath(); g.moveTo(px - 6, 0); g.lineTo(px + 6, 0); g.lineTo(px, 9); g.fill();
  }

  // --- interacción ---
  function hit(/** @type {number} */ x, /** @type {number} */ y) {
    const d = get().doc;
    if (y < RULER) return { kind: 'ruler' };
    if (y < RULER + CLIP_H + PAD / 2) {
      const starts = timelineStarts(d.timeline);
      for (let i = 0; i < d.timeline.length; i++) {
        const c = d.timeline[i], x0 = t2x(starts[i]), x1 = x0 + clipDuration(c) * get().zoom;
        if (x >= x0 - 2 && x <= x1 + 2) {
          const eg = Math.min(EDGE, (x1 - x0) / 3);
          return { kind: 'clip', clip: c, index: i, edge: x - x0 < eg ? 'l' : x1 - x < eg ? 'r' : null, start: starts[i] };
        }
      }
      return { kind: 'ruler' };
    }
    const r = Math.floor((y - RULER - CLIP_H - PAD) / ROW);
    const l = view.current.rows[r];
    if (l) {
      const x0 = t2x(l.start), x1 = t2x(l.end);
      if (x >= x0 - 2 && x <= x1 + 2) {
        const eg = Math.min(EDGE, (x1 - x0) / 3);
        return { kind: 'layer', layer: l, edge: x - x0 < eg ? 'l' : x1 - x < eg ? 'r' : null };
      }
    }
    return { kind: 'empty' };
  }

  function localXY(/** @type {PointerEvent} */ e) {
    const r = /** @type {HTMLCanvasElement} */ (cv.current).getBoundingClientRect();
    return [e.clientX - r.left, e.clientY - r.top];
  }

  function onDown(/** @type {PointerEvent} */ e) {
    if (!get().doc) return;
    const [x, y] = localXY(e), h = hit(x, y);
    /** @type {HTMLCanvasElement} */ (cv.current).setPointerCapture(e.pointerId);
    const v = view.current;
    ptr.current.set(e.pointerId, [x, y]);
    if (ptr.current.size === 2) { // dos dedos: pellizco = zoom, y arrastrar = desplazar
      const [a, b] = [...ptr.current.values()], cx = (a[0] + b[0]) / 2, st = get();
      v.drag = { mode: 'pinch', d0: Math.max(Math.hypot(a[0] - b[0], a[1] - b[1]), 1), z0: st.zoom, tc: st.scroll + cx / st.zoom };
      return;
    }
    const touch = e.pointerType === 'touch';
    const st0 = get().selection;
    // Con el dedo, tocar algo SIN seleccionar solo lo selecciona y arrastrar desplaza la línea de tiempo (no mueve el clip
    // por accidente). Una vez seleccionado, arrastrarlo sí lo mueve/recorta.
    if (touch && (h.kind === 'clip' || h.kind === 'layer')) {
      const id = h.kind === 'clip' ? h.clip.id : h.layer.id;
      if (st0.kind !== h.kind || st0.id !== id) {
        select(h.kind, id);
        v.drag = { mode: 'pan', x0: x, s0: get().scroll };
        redraw();
        return;
      }
    }
    if (h.kind === 'ruler' || h.kind === 'empty') {
      if (h.kind === 'empty') select('none');
      v.drag = { mode: 'scrub' };
      rt.player?.seek(Math.max(0, x2t(x)));
    } else if (h.kind === 'clip') {
      select('clip', h.clip.id);
      if (h.edge) {
        v.drag = { mode: 'trim', edge: h.edge, id: h.clip.id, x0: x, orig: { ...h.clip }, start: h.start };
      } else {
        v.drag = { mode: 'moveclip', id: h.clip.id, x0: x, orig: { ...h.clip }, start: h.start, moved: false };
      }
    } else if (h.kind === 'layer') {
      select('layer', h.layer.id);
      v.drag = { mode: h.edge ? 'resize' : 'move', edge: h.edge, id: h.layer.id, x0: x, s0: h.layer.start, e0: h.layer.end, moved: false };
    }
    redraw();
  }

  function onMove(/** @type {PointerEvent} */ e) {
    const v = view.current, [x, y] = localXY(e);
    if (ptr.current.has(e.pointerId)) ptr.current.set(e.pointerId, [x, y]);
    const d = v.drag;
    if (d?.mode === 'pinch') {
      if (ptr.current.size < 2) return;
      const [a, b] = [...ptr.current.values()], cx = (a[0] + b[0]) / 2;
      const z = Math.min(600, Math.max(4, d.z0 * Math.hypot(a[0] - b[0], a[1] - b[1]) / d.d0));
      ed.set({ zoom: z, scroll: Math.max(0, d.tc - cx / z) });
      return;
    }
    if (d?.mode === 'pan') { ed.set({ scroll: Math.max(0, d.s0 - (x - d.x0) / get().zoom) }); return; }
    if (!d) {
      const h = hit(x, y);
      /** @type {HTMLCanvasElement} */ (cv.current).style.cursor = h.kind === 'layer' || h.kind === 'clip' ? (h.edge ? 'ew-resize' : h.kind === 'layer' ? 'grab' : 'move') : 'default';
      return;
    }
    const total = timelineDuration(get().doc.timeline);
    if (d.mode === 'scrub') rt.player?.seek(Math.min(Math.max(0, x2t(x)), total));
    else if (d.mode === 'move' || d.mode === 'resize') {
      const dt = (x - d.x0) / get().zoom;
      if (Math.abs(x - d.x0) > 2) d.moved = true;
      if (!d.moved) return;
      let s = d.s0, en = d.e0;
      if (d.mode === 'move') {
        const len = d.e0 - d.s0;
        s = Math.max(0, d.s0 + dt);
        const ss = snap(s, d.id), se = snap(s + len, d.id);
        s = Math.abs(ss - s) <= Math.abs(se - (s + len)) ? ss : se - len;
        s = Math.max(0, s); en = s + len;
      } else if (d.edge === 'l') { s = Math.max(0, Math.min(snap(d.s0 + dt, d.id), d.e0 - 0.1)); }
      else { en = Math.max(d.s0 + 0.1, snap(d.e0 + dt, d.id)); }
      patchLayer(d.id, { start: +s.toFixed(3), end: +en.toFixed(3) });
    } else if (d.mode === 'moveclip') {
      const dt = (x - d.x0) / get().zoom;
      if (Math.abs(x - d.x0) > 2) d.moved = true;
      if (!d.moved) return;
      let t = Math.max(0, d.start + dt);
      const doc = get().doc;
      const me = doc.timeline.find((/** @type {any} */ k) => k.id === d.id);
      if (me) {
        const md = clipDuration(me);
        let blocked = false;
        for (const c of doc.timeline) {
          if (c.id === d.id) continue;
          const st = c.start_at != null ? c.start_at : (function(){const ss=timelineStarts(doc.timeline); const idx=doc.timeline.findIndex((k)=>k.id===c.id); return ss[idx];})();
          const ed2 = st + clipDuration(c);
          if (!(t + md <= st + 0.001 || t >= ed2 - 0.001)) { blocked = true; break; }
        }
        if (blocked) return;
      }
      ed.set({ doc: { ...doc, timeline: doc.timeline.map((/** @type {any} */ k) => (k.id === d.id ? { ...k, start_at: +t.toFixed(3) } : k)) } });
    } else if (d.mode === 'trim') {
      const c = d.orig, dt = (x - d.x0) / get().zoom, sp = c.speed || 1;
      let si = c.source_in, so = c.source_out;
      if (d.edge === 'l') si = Math.min(Math.max(0, c.source_in + dt * sp), c.source_out - 0.2);
      else so = Math.max(c.source_in + 0.2, Math.min(get().media.duration, c.source_out + dt * sp));
      d.result = { source_in: +si.toFixed(3), source_out: +so.toFixed(3) };
      const doc = get().doc;
      ed.set({ doc: { ...doc, timeline: doc.timeline.map((/** @type {any} */ k) => (k.id === d.id ? { ...k, ...d.result } : k)) } });
    }
    redraw();
  }

  function onUp(/** @type {PointerEvent} */ e) {
    ptr.current.delete(e.pointerId);
    const d = view.current.drag;
    if (d?.mode === 'pinch' && ptr.current.size > 0) return; // queda un dedo: no se hace nada hasta soltarlo
    view.current.drag = null;
    if (d?.mode === 'trim' && d.result) applyOps([{ op: 'set_clip_range', clip_id: d.id, ...d.result }], 'Recortar clip');
    else if (d?.mode === 'moveclip' && d.moved) {
      const doc = get().doc;
      const c = doc.timeline.find((/** @type {any} */ k) => k.id === d.id);
      if (c) {
        const t = c.start_at != null ? c.start_at : (function(){const ss=timelineStarts(doc.timeline); const idx=doc.timeline.findIndex((k)=>k.id===d.id); return ss[idx];})();
        applyOps([{ op: 'set_clip_range', clip_id: d.id, start_at: +Math.max(0, t).toFixed(3) }], 'Mover clip');
      }
    }
  }

  function onWheel(/** @type {WheelEvent} */ e) {
    e.preventDefault();
    const st = get();
    if (e.ctrlKey || e.metaKey) {
      const [x] = [e.clientX - /** @type {HTMLCanvasElement} */ (cv.current).getBoundingClientRect().left];
      const tAt = x2t(x), z = Math.min(600, Math.max(4, st.zoom * (e.deltaY < 0 ? 1.15 : 1 / 1.15)));
      ed.set({ zoom: z, scroll: Math.max(0, tAt - x / z) });
    } else {
      const dx = Math.abs(e.deltaX) > Math.abs(e.deltaY) ? e.deltaX : e.deltaY;
      ed.set({ scroll: Math.max(0, st.scroll + dx / st.zoom) });
    }
  }

  // --- ciclo de vida ---
  useEffect(() => {
    const unsub = ed.subscribe(() => { redraw(); });
    const ro = new ResizeObserver(redraw);
    if (wrap.current) ro.observe(wrap.current);
    const cvEl = /** @type {HTMLCanvasElement} */ (cv.current);
    cvEl.addEventListener('wheel', onWheel, { passive: false });
    return () => { unsub(); ro.disconnect(); cvEl.removeEventListener('wheel', onWheel); cancelAnimationFrame(raf.current); };
  }, []);
  const zoom = useEd((s) => s.zoom);
  const media = useEd((s) => s.media);
  const fitted = useRef('');
  useEffect(() => {
    const pj = get().project;
    if (doc && pj && fitted.current !== pj.id && view.current.w > 50) {
      fitted.current = pj.id;
      ed.set({ zoom: Math.max(4, Math.min(300, (view.current.w - 24) / (timelineDuration(doc.timeline) || 1))), scroll: 0 });
    }
  }, [doc?.timeline.length, get().project?.id]);
  useEffect(() => { loadPeaks(); redraw(); }, [doc?.timeline, zoom, media]);

  // sigue el cabezal durante la reproducción
  useEffect(() => ed.subscribe((s) => {
    if (s.playing && view.current.w) {
      const x = (s.t - s.scroll) * s.zoom;
      if (x > view.current.w - 30 || x < 0) ed.set({ scroll: Math.max(0, s.t - 20 / s.zoom) });
    }
  }), []);

  const clipSel = useEd((s) => s.selection);
  return html`
    <div class="tl-tools">
      <button class="small-btn tl-split" onClick=${splitAtPlayhead} title="Dividir el clip en el cabezal (S)">✂<span class="hide-xs"> Dividir</span></button>
      <button class="small-btn" onClick=${deleteSelected} title="Borrar lo seleccionado (Supr)">🗑<span class="hide-xs"> Borrar</span></button>
      <button class="small-btn" disabled=${clipSel.kind !== 'clip'} onClick=${() => { const c = clipById(clipSel.id); if (c) applyOps([{ op: 'add_clip', source_in: c.source_in, source_out: c.source_out, speed: c.speed }], 'Duplicar clip'); }} title="Duplicar el clip seleccionado al final">⧉<span class="hide-sm"> Duplicar clip</span></button>
      <span class="grow"></span>
      <button class="icon-btn" aria-label="Alejar" onClick=${() => ed.set({ zoom: Math.max(4, zoom / 1.4) })}>−</button>
      <input class="hide-sm" type="range" min="4" max="600" step="1" value=${Math.round(zoom)} aria-label="Zoom" onInput=${(/** @type {Event} */ e) => ed.set({ zoom: +(/** @type {HTMLInputElement} */ (e.target).value) })} />
      <button class="icon-btn" aria-label="Acercar" onClick=${() => ed.set({ zoom: Math.min(600, zoom * 1.4) })}>+</button>
      <button class="small-btn" onClick=${() => { const w = view.current.w || 600; const tot = timelineDuration(get().doc.timeline) || 1; ed.set({ zoom: Math.max(4, Math.min(600, (w - 20) / tot)), scroll: 0 }); }} title="Ajustar todo el clip a la pantalla">Ajustar</button>
    </div>
    <div class="tl-wrap" ref=${wrap}>
      <canvas ref=${cv} class="tl-canvas" onPointerDown=${onDown} onPointerMove=${onMove} onPointerUp=${onUp} onPointerCancel=${onUp} role="application" aria-label="Línea de tiempo"></canvas>
    </div>`;
}
