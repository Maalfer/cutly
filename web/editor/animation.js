// @ts-check
// Motor de animación: port exacto de services/render/animation.py (el servidor es la referencia).

export function ease(/** @type {string} */ name, /** @type {number} */ p) {
  p = Math.min(Math.max(p, 0), 1);
  switch (name) {
    case 'linear': return p;
    case 'ease_in': return p ** 3;
    case 'ease_out': return 1 - (1 - p) ** 3;
    case 'ease_in_out': return p < 0.5 ? 4 * p ** 3 : 1 - (-2 * p + 2) ** 3 / 2;
    case 'ease_out_back': { const c1 = 1.70158, c3 = 2.70158; return 1 + c3 * (p - 1) ** 3 + c1 * (p - 1) ** 2; }
    case 'ease_out_bounce': return bounce(p);
    case 'ease_out_elastic': return p === 0 ? 0 : p === 1 ? 1 : 2 ** (-10 * p) * Math.sin((p * 10 - 0.75) * (2 * Math.PI) / 3) + 1;
    default: return p;
  }
}

function bounce(/** @type {number} */ p) {
  const n1 = 7.5625, d1 = 2.75;
  if (p < 1 / d1) return n1 * p * p;
  if (p < 2 / d1) { p -= 1.5 / d1; return n1 * p * p + 0.75; }
  if (p < 2.5 / d1) { p -= 2.25 / d1; return n1 * p * p + 0.9375; }
  p -= 2.625 / d1;
  return n1 * p * p + 0.984375;
}

/** @typedef {{dx:number,dy:number,scale:number,opacity:number,rot:number}} Props */
const props = (/** @type {Partial<Props>} */ o = {}) => ({ dx: 0, dy: 0, scale: 1, opacity: 1, rot: 0, ...o });
const DX = 0.15, DY = 0.10;

function preset(/** @type {string} */ name, /** @type {number} */ p, /** @type {boolean} */ leaving) {
  const e = ease(leaving ? 'ease_in' : 'ease_out', p);
  if (name === 'fade') return props({ opacity: e });
  if (name === 'pop') return props({ scale: 0.5 + 0.5 * ease(leaving ? 'ease_in' : 'ease_out_back', p), opacity: Math.min(1, p * 3) });
  if (name === 'zoom_in' || name === 'zoom') return props({ scale: 0.3 + 0.7 * e, opacity: Math.min(1, p * 2) });
  if (name === 'zoom_out') return props({ scale: 1 + 0.7 * (1 - e), opacity: e });
  if (name === 'spin_in' || name === 'spin') return props({ scale: 0.3 + 0.7 * e, rot: -180 * (1 - e), opacity: Math.min(1, p * 2) });
  if (name === 'rotate') return props({ scale: 0.7 + 0.3 * e, rot: -360 * (1 - e), opacity: e });
  if (name === 'flip') return props({ scale: Math.abs(Math.cos(Math.PI * (1 - e))), rot: 0, opacity: e });
  if (name === 'bounce') return props({ dy: -0.12 * (1 - ease(leaving ? 'ease_in' : 'ease_out_bounce', p)), opacity: Math.min(1, p * 4) });
  if (name === 'fade_scale') return props({ scale: 0.8 + 0.2 * e, opacity: e });
  if (name === 'scale_up') return props({ scale: 0.5 + 0.5 * e, opacity: Math.min(1, p * 2) });
  if (name === 'scale_down') return props({ scale: 1.5 - 0.5 * e, opacity: e });
  if (name === 'blur_fade') return props({ scale: 0.9 + 0.1 * e, opacity: e });
  if (name === 'drop') return props({ dy: -0.3 * (1 - ease(leaving ? 'ease_in' : 'ease_out_bounce', p)), opacity: Math.min(1, p * 3) });
  const off = /** @type {Record<string,[number,number]>} */ ({ slide_up: [0, DY], slide_down: [0, -DY], slide_left: [DX, 0], slide_right: [-DX, 0], slide_up_big: [0, 0.3], slide_down_big: [0, -0.3], slide_left_big: [0.4, 0], slide_right_big: [-0.4, 0], from_top: [0, DY], from_bottom: [0, -DY], from_left: [DX, 0], from_right: [-DX, 0] })[name];
  if (off) return props({ dx: off[0] * (1 - e), dy: off[1] * (1 - e), opacity: Math.min(1, p * 2.5) });
  return props();
}

function loop(/** @type {string} */ name, /** @type {number} */ tau, /** @type {number} */ period, /** @type {number} */ amount) {
  const w = Math.sin((2 * Math.PI * tau) / period);
  if (name === 'pulse' || name === 'breathing') return props({ scale: 1 + amount * w });
  if (name === 'wiggle') return props({ rot: amount * 40 * w });
  if (name === 'float' || name === 'hover') return props({ dy: amount * 0.15 * w });
  if (name === 'blink') return props({ opacity: amount ? 1 - amount * 4 * (0.5 - 0.5 * w) : 1 });
  if (name === 'shake' || name === 'tremble') return props({ dx: amount * 0.2 * Math.sin((2 * Math.PI * 3 * tau) / period) });
  if (name === 'swing') return props({ rot: amount * 20 * Math.sin((2 * Math.PI * tau) / period) });
  if (name === 'zoom_pulse') return props({ scale: 1 + amount * 0.1 * w });
  if (name === 'bounce_loop') return props({ dy: -amount * 0.08 * Math.max(0, w) });
  if (name === 'spin_loop') return props({ rot: amount * 360 * (tau / period) % 360 });
  return props();
}

function kfValue(/** @type {any[]} */ kfs, /** @type {string} */ attr, /** @type {number} */ base, /** @type {number} */ tau) {
  /** @type {[number, number, string][]} */
  const pts = kfs.filter((k) => k[attr] !== null && k[attr] !== undefined).map((k) => [k.t, k[attr], k.easing || 'ease_out']);
  if (!pts.length) return null;
  pts.sort((a, b) => a[0] - b[0]);
  if (pts[0][0] > 0) pts.unshift([0, base, 'linear']);
  if (tau <= pts[0][0]) return pts[0][1];
  for (let i = 0; i < pts.length - 1; i++) {
    const [t0, v0] = pts[i], [t1, v1, easing] = pts[i + 1];
    if (tau <= t1) return v0 + (v1 - v0) * ease(easing, (tau - t0) / Math.max(t1 - t0, 1e-6));
  }
  return pts[pts.length - 1][1];
}

/** Propiedades de la layer `tau` segundos después de su inicio (desplazamientos relativos a su caja base). */
export function evalProps(/** @type {any} */ layer, /** @type {number} */ tau, /** @type {number} */ baseX, /** @type {number} */ baseY, baseRot = 0) {
  const an = layer.animations || {};
  const length = layer.end - layer.start;
  const out = props({ opacity: layer.opacity ?? 1 });
  if (an.keyframes && an.keyframes.length) {
    const x = kfValue(an.keyframes, 'x', baseX, tau), y = kfValue(an.keyframes, 'y', baseY, tau);
    const sc = kfValue(an.keyframes, 'scale', 1, tau), op = kfValue(an.keyframes, 'opacity', layer.opacity ?? 1, tau);
    const rt = kfValue(an.keyframes, 'rotation', baseRot, tau);
    out.dx = x === null ? 0 : x - baseX;
    out.dy = y === null ? 0 : y - baseY;
    out.scale = sc === null ? 1 : sc;
    out.opacity = op === null ? layer.opacity ?? 1 : op;
    out.rot = rt === null ? 0 : rt - baseRot;
  }
  for (const [anim, leaving] of /** @type {[any, boolean][]} */ ([[an.enter, false], [an.exit, true]])) {
    if (!anim) continue;
    const d = Math.min(anim.dur, length);
    let p;
    if (!leaving && tau < d) p = preset(anim.name, tau / d, false);
    else if (leaving && tau > length - d) p = preset(anim.name, (length - tau) / d, true);
    else continue;
    out.dx += p.dx; out.dy += p.dy; out.scale *= p.scale; out.rot += p.rot; out.opacity *= p.opacity;
  }
  if (an.loop) {
    const lp = loop(an.loop.name, tau, an.loop.period, an.loop.amount);
    out.dx += lp.dx; out.dy += lp.dy; out.scale *= lp.scale; out.rot += lp.rot; out.opacity *= lp.opacity;
  }
  out.opacity = Math.min(Math.max(out.opacity, 0), 1);
  out.scale = Math.max(out.scale, 0.01);
  return out;
}
