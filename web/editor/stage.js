// @ts-check
// Compositor de la vista previa: dibuja en un canvas lo mismo que el render (aproximado): reencuadre, color, capas,
// subtítulos con palabra activa y efectos (módulos preview.js del registro). Es la referencia visual mientras se edita.
import { evalProps } from './animation.js';
import { anchorFactors, reframePlan } from './geometry.js';
import { activeCue, groupCues } from './subtitles.js';
import { mapWords } from './time.js';

const hexA = (/** @type {string|null|undefined} */ hex, /** @type {number} */ mul = 1) => {
  if (!hex) return 'rgba(0,0,0,0)';
  const h = hex.replace('#', '');
  const a = h.length === 8 ? parseInt(h.slice(6, 8), 16) / 255 : 1;
  return `rgba(${parseInt(h.slice(0, 2), 16)},${parseInt(h.slice(2, 4), 16)},${parseInt(h.slice(4, 6), 16)},${(a * mul).toFixed(3)})`;
};

/** Familia CSS para una fuente del proyecto. */
const family = (/** @type {string} */ f) => (f === 'default' ? '"DejaVu Sans", sans-serif' : `"${f}", "DejaVu Sans", sans-serif`);

export class Stage {
  constructor(/** @type {HTMLCanvasElement} */ canvas, /** @type {HTMLVideoElement} */ video) {
    this.canvas = canvas;
    this.video = video;
    this.ctx = /** @type {CanvasRenderingContext2D} */ (canvas.getContext('2d'));
    this.A = document.createElement('canvas');
    this.B = document.createElement('canvas');
    /** @type {any} */ this.doc = null;
    /** @type {{w:string,start:number,end:number}[]} */ this.words = [];
    /** @type {Map<string, HTMLImageElement|'loading'|'error'>} */ this.images = new Map();
    /** @type {Map<string, any>} */ this.effects = new Map();
    /** @type {{id:string, rect:number[]}[]} */ this.hits = [];
    /** @type {() => void} */ this.requestRedraw = () => {};
    this._mappedKey = '';
    /** @type {[number,number,string][]} */ this._mapped = [];
    this.fontsReady = false;
  }

  setSize(/** @type {number} */ outW, /** @type {number} */ outH) {
    const s = Math.min(1, 540 / outW);
    const W = Math.round(outW * s), H = Math.round(outH * s);
    for (const c of [this.canvas, this.A, this.B]) { if (c.width !== W || c.height !== H) { c.width = W; c.height = H; } }
  }

  setDoc(/** @type {any} */ doc) {
    this.doc = doc;
    if (doc) this.setSize(doc.output.width, doc.output.height);
  }

  setWords(/** @type {any[]} */ words) { this.words = words; this._mappedKey = ''; }

  /** Carga las fuentes de la biblioteca como FontFace para que el canvas las use. */
  async loadFonts(/** @type {any[]} */ assets) {
    const faces = assets.filter((a) => a.kind === 'font').map((a) => {
      const bold = /-Bold$/.test(a.id);
      const ff = new FontFace(a.family, `url(/api/v1/assets/file/${a.id})`, { weight: bold ? '700' : '400' });
      return ff.load().then((f) => { document.fonts.add(f); }).catch(() => {});
    });
    await Promise.all(faces);
    this.fontsReady = true;
    this.requestRedraw();
  }

  // --- imágenes (iconos/imágenes de la biblioteca) ------------------------------------------------------------------------

  _image(/** @type {string} */ asset, /** @type {string|null} */ tint) {
    const key = `${asset}|${tint || ''}`;
    const cached = this.images.get(key);
    if (cached) return cached === 'loading' || cached === 'error' ? null : cached;
    this.images.set(key, 'loading');
    fetch(`/api/v1/assets/file/${asset}`, { credentials: 'same-origin' }).then(async (r) => {
      if (!r.ok) throw new Error(String(r.status));
      const ct = r.headers.get('content-type') || '';
      let url;
      if (ct.includes('svg')) {
        let svg = await r.text();
        svg = svg.replace(/<svg([^>]*)>/, (m, attrs) => (/\bwidth=/.test(attrs) ? m : `<svg${attrs} width="256" height="256">`));
        if (tint) svg = svg.replace(/(fill|stroke)="(#[0-9A-Fa-f]{3,8}|[a-z]+)"/g, (m, a, c) => (c === 'none' ? m : `${a}="${tint.slice(0, 7)}"`));
        url = URL.createObjectURL(new Blob([svg], { type: 'image/svg+xml' }));
      } else url = URL.createObjectURL(await r.blob());
      const img = new Image();
      img.onload = () => { this.images.set(key, img); this.requestRedraw(); };
      img.onerror = () => this.images.set(key, 'error');
      img.src = url;
    }).catch(() => this.images.set(key, 'error'));
    return null;
  }

  _effect(/** @type {string} */ name) {
    const c = this.effects.get(name);
    if (c) return c === 'loading' || c === 'error' ? null : c;
    this.effects.set(name, 'loading');
    import(/* @vite-ignore */ `/api/v1/effects/${name}/preview.js`).then((m) => { this.effects.set(name, m); this.requestRedraw(); }).catch(() => this.effects.set(name, 'error'));
    return null;
  }

  // --- dibujo --------------------------------------------------------------------------------------------------------------

  render(/** @type {number} */ t, /** @type {string|null} */ selectedId = null) {
    const doc = this.doc;
    if (!doc) return;
    const W = this.canvas.width, H = this.canvas.height;
    let cur = this.A, tmp = this.B;
    const c = /** @type {CanvasRenderingContext2D} */ (cur.getContext('2d'));
    this.hits = [];
    this._drawBase(c, W, H);
    const sorted = doc.layers.map((/** @type {any} */ l, /** @type {number} */ i) => [l, i]).sort((/** @type {any} */ a, /** @type {any} */ b) => a[0].z - b[0].z || a[1] - b[1]).map((/** @type {any} */ x) => x[0]);
    for (const layer of sorted) {
      if (!layer.visible || t < layer.start || t >= layer.end) continue;
      if (layer.type === 'effect') {
        const mod = this._effect(layer.effect);
        if (!mod) continue;
        const prog = (t - layer.start) / Math.max(layer.end - layer.start, 0.001);
        const tctx = /** @type {CanvasRenderingContext2D} */ (tmp.getContext('2d'));
        tctx.clearRect(0, 0, W, H);
        tctx.drawImage(cur, 0, 0);
        try {
          if (layer.region) {
            const r = layer.region, rx = r.x * W, ry = r.y * H, rw = r.w * W, rh = r.h * H;
            const sub = document.createElement('canvas');
            sub.width = Math.max(1, Math.round(rw)); sub.height = Math.max(1, Math.round(rh));
            const sctx = /** @type {CanvasRenderingContext2D} */ (sub.getContext('2d'));
            sctx.drawImage(cur, rx, ry, rw, rh, 0, 0, sub.width, sub.height);
            tctx.save(); tctx.beginPath(); tctx.rect(rx, ry, rw, rh); tctx.clip(); tctx.translate(rx, ry);
            mod.render(tctx, sub, layer.params || {}, prog, { w: rw, h: rh });
            tctx.restore();
          } else {
            tctx.save();
            mod.render(tctx, cur, layer.params || {}, prog, { w: W, h: H });
            tctx.restore();
          }
          [cur, tmp] = [tmp, cur];
        } catch { /* un preview defectuoso no debe romper la edición */ }
        continue;
      }
      const cctx = /** @type {CanvasRenderingContext2D} */ (cur.getContext('2d'));
      if (layer.type === 'text') this._text(cctx, layer, t, W, H);
      else if (layer.type === 'shape') this._shape(cctx, layer, t, W, H);
      else if (layer.type === 'icon' || layer.type === 'image') this._icon(cctx, layer, t, W, H);
      else if (layer.type === 'subtitle') this._subtitle(cctx, layer, t, W, H);
      else if (layer.type === 'scene') this._scene(cctx, layer, W, H);
    }
    this.ctx.clearRect(0, 0, W, H);
    this.ctx.drawImage(cur, 0, 0);
    if (selectedId) this._selection(selectedId);
  }

  _drawBase(/** @type {CanvasRenderingContext2D} */ c, /** @type {number} */ W, /** @type {number} */ H) {
    const v = this.video, doc = this.doc;
    c.setTransform(1, 0, 0, 1, 0, 0);
    c.globalAlpha = 1;
    c.filter = 'none';
    c.fillStyle = '#000';
    c.fillRect(0, 0, W, H);
    if (!v.videoWidth) return;
    const col = doc.color;
    const adj = `brightness(${(1 + col.brightness).toFixed(3)}) contrast(${col.contrast}) saturate(${col.saturation})`;
    for (const d of reframePlan(doc.reframe, v.videoWidth, v.videoHeight, W, H)) {
      c.filter = d.blur ? `blur(${Math.round(W / 40)}px) ${adj}` : adj;
      c.drawImage(v, d.sx, d.sy, d.sw, d.sh, d.dx, d.dy, d.dw, d.dh);
    }
    c.filter = 'none';
  }

  /** Mide texto con la fuente en px de ALTURA DE LÍNEA (criterio de libass: ascendente+descendente = tamaño). */
  _setFont(/** @type {CanvasRenderingContext2D} */ c, /** @type {string} */ fontName, /** @type {number} */ sizePx, /** @type {boolean} */ bold) {
    const w = bold ? '700' : '400';
    c.font = `${w} ${sizePx}px ${family(fontName)}`;
    const m = c.measureText('Hg');
    const lineH = (m.fontBoundingBoxAscent || sizePx * 0.9) + (m.fontBoundingBoxDescent || sizePx * 0.25);
    const em = Math.max(6, sizePx * (sizePx / lineH));
    c.font = `${w} ${em}px ${family(fontName)}`;
    return em;
  }

  _wrap(/** @type {CanvasRenderingContext2D} */ c, /** @type {string} */ text, /** @type {number} */ maxW) {
    /** @type {string[]} */
    const lines = [];
    for (const raw of text.split('\n')) {
      let cur = '';
      for (const word of raw.split(/\s+/).filter(Boolean)) {
        const trial = cur ? `${cur} ${word}` : word;
        if (cur && c.measureText(trial).width > maxW) { lines.push(cur); cur = word; } else cur = trial;
      }
      lines.push(cur);
    }
    return lines;
  }

  /** Aplica traslación al ancla, giro y escala de la animación; devuelve la función para pasar de local a pantalla. */
  _xf(/** @type {CanvasRenderingContext2D} */ c, /** @type {number} */ ax, /** @type {number} */ ay, /** @type {any} */ p, /** @type {number} */ rot) {
    c.translate(ax, ay);
    c.rotate(((rot + p.rot) * Math.PI) / 180);
    c.scale(p.scale, p.scale);
    const m = c.getTransform();
    return (/** @type {number} */ x, /** @type {number} */ y) => [m.a * x + m.c * y + m.e, m.b * x + m.d * y + m.f];
  }

  _bounds(/** @type {string} */ id, /** @type {(x:number,y:number)=>number[]} */ toScreen, /** @type {number} */ x0, /** @type {number} */ y0, /** @type {number} */ x1, /** @type {number} */ y1) {
    const pts = [toScreen(x0, y0), toScreen(x1, y0), toScreen(x1, y1), toScreen(x0, y1)];
    this.hits.push({ id, rect: [Math.min(...pts.map((p) => p[0])), Math.min(...pts.map((p) => p[1])), Math.max(...pts.map((p) => p[0])), Math.max(...pts.map((p) => p[1]))] });
  }

  _text(/** @type {CanvasRenderingContext2D} */ c, /** @type {any} */ layer, /** @type {number} */ t, /** @type {number} */ W, /** @type {number} */ H) {
    const st = layer.style, box = layer.box;
    const p = evalProps(layer, t - layer.start, box.x, box.y, box.rotation);
    c.save();
    const sizePx = st.size * H;
    const em = this._setFont(c, st.font, sizePx, st.bold);
    const text = st.uppercase ? layer.text.toUpperCase() : layer.text;
    const lines = this._wrap(c, text, box.w * W);
    const widths = lines.map((l) => c.measureText(l).width);
    const bw = Math.max(...widths, 1), bh = lines.length * sizePx;
    const [fx, fy] = anchorFactors(box.anchor);
    const toScreen = this._xf(c, (box.x + p.dx) * W, (box.y + p.dy) * H, p, box.rotation);
    c.globalAlpha = p.opacity;
    c.textBaseline = 'middle';
    const pad = st.bg_color ? sizePx * 0.2 : 0, outline = st.bg_color ? 0 : st.outline_width * H;
    const hAlign = box.anchor.endsWith('left') ? 'left' : box.anchor.endsWith('right') ? 'right' : 'center';
    lines.forEach((ln, i) => {
      const lw = widths[i];
      const x = -bw * fx + (hAlign === 'left' ? 0 : hAlign === 'right' ? bw - lw : (bw - lw) / 2);
      const y = -bh * fy + i * sizePx + sizePx / 2;
      if (st.bg_color) { c.fillStyle = hexA(st.bg_color); c.fillRect(x - pad, y - sizePx / 2 - pad * 0.4, lw + pad * 2, sizePx + pad * 0.8); }
      if (outline > 0) { c.lineWidth = outline * 2; c.lineJoin = 'round'; c.strokeStyle = hexA(st.outline_color); c.strokeText(ln, x, y); }
      c.fillStyle = hexA(st.color);
      c.fillText(ln, x, y);
    });
    this._bounds(layer.id, toScreen, -bw * fx - pad, -bh * fy - pad, -bw * fx + bw + pad, -bh * fy + bh + pad);
    c.restore();
    return em;
  }

  _shape(/** @type {CanvasRenderingContext2D} */ c, /** @type {any} */ layer, /** @type {number} */ t, /** @type {number} */ W, /** @type {number} */ H) {
    const box = layer.box;
    const p = evalProps(layer, t - layer.start, box.x, box.y, box.rotation);
    const w = box.w * W, h = box.h ? box.h * H : w;
    const [fx, fy] = anchorFactors(box.anchor);
    c.save();
    const cx = (box.x + p.dx) * W - w * fx + w / 2, cy = (box.y + p.dy) * H - h * fy + h / 2; // gira y escala sobre su centro
    const toScreen = this._xf(c, cx, cy, p, box.rotation);
    c.globalAlpha = p.opacity;
    c.beginPath();
    if (layer.shape === 'ellipse') c.ellipse(0, 0, w / 2, h / 2, 0, 0, Math.PI * 2); else c.rect(-w / 2, -h / 2, w, h);
    if (layer.fill) { c.fillStyle = hexA(layer.fill); c.fill(); }
    if (layer.stroke) { c.lineWidth = layer.stroke_width * H; c.strokeStyle = hexA(layer.stroke); c.stroke(); }
    this._bounds(layer.id, toScreen, -w / 2, -h / 2, w / 2, h / 2);
    c.restore();
  }

  /** Las escenas animadas las dibuja el servidor (motor Python): aquí solo un marcador con su caja. */
  _scene(/** @type {CanvasRenderingContext2D} */ c, /** @type {any} */ layer, /** @type {number} */ W, /** @type {number} */ H) {
    const b = layer.box, tall = layer.params?.orient === 'tall';
    const w = b.w * W, h = b.h ? b.h * H : w * (tall ? 16 / 9 : 9 / 16);
    const [fx, fy] = anchorFactors(b.anchor);
    const x = b.x * W - w * fx, y = b.y * H - h * fy;
    c.save();
    c.fillStyle = 'rgba(52,227,255,.08)'; c.fillRect(x, y, w, h);
    c.strokeStyle = 'rgba(52,227,255,.7)'; c.setLineDash([10, 8]); c.lineWidth = 2; c.strokeRect(x, y, w, h);
    c.setLineDash([]); c.fillStyle = 'rgba(255,255,255,.9)'; c.textAlign = 'center'; c.textBaseline = 'middle';
    c.font = `600 ${Math.max(12, W / 28)}px sans-serif`;
    c.fillText(`◈ ${layer.template || 'Escena'}`, x + w / 2, y + h / 2 - W / 40);
    c.font = `${Math.max(10, W / 40)}px sans-serif`; c.fillStyle = 'rgba(255,255,255,.6)';
    c.fillText('se anima al renderizar', x + w / 2, y + h / 2 + W / 40);
    this.hits.push({ id: layer.id, rect: [x, y, x + w, y + h] });
    c.restore();
  }

  _icon(/** @type {CanvasRenderingContext2D} */ c, /** @type {any} */ layer, /** @type {number} */ t, /** @type {number} */ W, /** @type {number} */ H) {
    const box = layer.box;
    const img = this._image(layer.asset, layer.tint || null);
    const p = evalProps(layer, t - layer.start, box.x, box.y, box.rotation);
    const w = box.w * W, h = box.h ? box.h * H : img ? (w * img.naturalHeight) / Math.max(img.naturalWidth, 1) : w;
    const [fx, fy] = anchorFactors(box.anchor);
    c.save();
    const cx = (box.x + p.dx) * W - w * fx + w / 2, cy = (box.y + p.dy) * H - h * fy + h / 2;
    const toScreen = this._xf(c, cx, cy, p, box.rotation);
    c.globalAlpha = p.opacity;
    if (img) c.drawImage(img, -w / 2, -h / 2, w, h);
    else { c.strokeStyle = 'rgba(255,255,255,.4)'; c.setLineDash([4, 4]); c.strokeRect(-w / 2, -h / 2, w, h); }
    this._bounds(layer.id, toScreen, -w / 2, -h / 2, w / 2, h / 2);
    c.restore();
  }

  _subtitle(/** @type {CanvasRenderingContext2D} */ c, /** @type {any} */ layer, /** @type {number} */ t, /** @type {number} */ W, /** @type {number} */ H) {
    const doc = this.doc, st = layer.style;
    const key = JSON.stringify(doc.timeline) + this.words.length;
    if (key !== this._mappedKey) { this._mapped = mapWords(this.words, doc.timeline); this._mappedKey = key; /** @type {any} */ (this)._cues = new Map(); }
    const cues = /** @type {Map<string, any>} */ (/** @type {any} */ (this)._cues);
    const ck = `${layer.id}|${st.max_words_per_cue}|${layer.start}|${layer.end}`;
    if (!cues.has(ck)) {
      const ws = /** @type {[number,number,string][]} */ (this._mapped.map(([s, e, w]) => /** @type {[number,number,string]} */ ([Math.max(s, layer.start), Math.min(e, layer.end), w])).filter(([s, e]) => e > layer.start && s < layer.end));
      cues.set(ck, groupCues(ws, st.max_words_per_cue));
    }
    const cue = activeCue(cues.get(ck), t, st);
    if (!cue) { this.hits.push({ id: layer.id, rect: [W * 0.06, (st.position_y - 0.04) * H, W * 0.94, (st.position_y + 0.04) * H] }); return; }
    c.save();
    const sizePx = st.size * H;
    this._setFont(c, st.font, sizePx, st.bold);
    c.textBaseline = 'middle';
    const space = c.measureText(' ').width;
    const rows = cue.lines.map((/** @type {any[]} */ ln) => ({ ln, w: ln.reduce((/** @type {number} */ a, /** @type {any} */ w) => a + c.measureText(w.text).width, 0) + space * (ln.length - 1) }));
    const top = st.position_y * H - (rows.length * sizePx) / 2;
    const outline = st.bg_color ? 0 : st.outline_width * H, pad = st.bg_color ? sizePx * 0.18 : 0;
    let maxW = 0;
    rows.forEach((row, i) => {
      maxW = Math.max(maxW, row.w);
      const y = top + i * sizePx + sizePx / 2;
      if (st.bg_color) { c.fillStyle = hexA(st.bg_color); c.fillRect(W / 2 - row.w / 2 - pad, y - sizePx / 2, row.w + pad * 2, sizePx); }
      let x = W / 2 - row.w / 2;
      for (const w of row.ln) {
        const wd = c.measureText(w.text).width;
        const hl = w.active && st.animation !== 'none' && st.highlight_color;
        const scale = w.active && st.animation === 'pop' ? 0.8 + 0.32 * cue.progress : 1;
        c.save();
        c.translate(x + wd / 2, y);
        c.scale(scale, scale);
        if (outline > 0) { c.lineWidth = outline * 2; c.lineJoin = 'round'; c.strokeStyle = hexA(st.outline_color); c.strokeText(w.text, -wd / 2, 0); }
        c.fillStyle = hexA(hl ? st.highlight_color : st.color);
        c.fillText(w.text, -wd / 2, 0);
        c.restore();
        x += wd + space;
      }
    });
    this.hits.push({ id: layer.id, rect: [W / 2 - maxW / 2 - pad, top, W / 2 + maxW / 2 + pad, top + rows.length * sizePx] });
    c.restore();
  }

  _selection(/** @type {string} */ id) {
    const h = this.hits.find((x) => x.id === id);
    if (!h) return;
    const c = this.ctx, [x0, y0, x1, y1] = h.rect;
    c.save();
    c.strokeStyle = '#6d5efc'; c.lineWidth = 2; c.setLineDash([6, 4]);
    c.strokeRect(x0, y0, x1 - x0, y1 - y0);
    c.setLineDash([]); c.fillStyle = '#fff'; c.strokeStyle = '#6d5efc';
    for (const [x, y] of [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]) { c.beginPath(); c.rect(x - 5, y - 5, 10, 10); c.fill(); c.stroke(); }
    c.restore();
  }

  /** Capa más alta bajo un punto del canvas (coordenadas internas) o null. */
  hitTest(/** @type {number} */ x, /** @type {number} */ y) {
    const sorted = this.doc ? new Map(this.doc.layers.map((/** @type {any} */ l, /** @type {number} */ i) => [l.id, [l.z, i]])) : new Map();
    const hits = this.hits.filter((h) => x >= h.rect[0] && x <= h.rect[2] && y >= h.rect[1] && y <= h.rect[3]);
    hits.sort((a, b) => { const A = sorted.get(a.id) || [0, 0], B = sorted.get(b.id) || [0, 0]; return B[0] - A[0] || B[1] - A[1]; });
    return hits[0]?.id || null;
  }
}
