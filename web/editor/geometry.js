// @ts-check
// Geometría del reencuadre: qué trozo del vídeo original se dibuja y dónde (misma lógica que render/graph.py).

/** @typedef {{sx:number,sy:number,sw:number,sh:number,dx:number,dy:number,dw:number,dh:number,blur?:boolean}} Draw */

const even = (/** @type {number} */ v) => Math.max(2, Math.round(v / 2) * 2);

/** Región `r` (0–1 del original) mostrada en la banda [dx,dy,dw,dh] de la salida: cubrir (recorta) o contener (con bandas). */
function band(/** @type {{x:number,y:number,w:number,h:number}} */ r, /** @type {number} */ sw, /** @type {number} */ sh, /** @type {number[]} */ b, /** @type {string} */ fit) {
  const rx = r.x * sw, ry = r.y * sh, rw = r.w * sw, rh = r.h * sh;
  const [dx, dy, dw, dh] = b;
  const cover = Math.max(dw / rw, dh / rh), contain = Math.min(dw / rw, dh / rh);
  if (fit === 'contain') {
    const w = rw * contain, h = rh * contain;
    return [
      /** @type {Draw} */ ({ sx: rx, sy: ry, sw: rw, sh: rh, dx, dy, dw, dh, blur: true }),
      /** @type {Draw} */ ({ sx: rx, sy: ry, sw: rw, sh: rh, dx: dx + (dw - w) / 2, dy: dy + (dh - h) / 2, dw: w, dh: h }),
    ];
  }
  const cw = dw / cover, ch = dh / cover; // trozo del original que cabe al cubrir
  return [/** @type {Draw} */ ({ sx: rx + (rw - cw) / 2, sy: ry + (rh - ch) / 2, sw: cw, sh: ch, dx, dy, dw, dh })];
}

/** Instrucciones de dibujo del vídeo base para un reencuadre. */
export function reframePlan(/** @type {any} */ rf, /** @type {number} */ sw, /** @type {number} */ sh, /** @type {number} */ W, /** @type {number} */ H) {
  if (rf.mode === 'stack' && rf.facecam && rf.game) {
    const top = even(H * rf.stack_split);
    return [...band(rf.facecam, sw, sh, [0, 0, W, top], 'cover'), ...band(rf.game, sw, sh, [0, top, W, H - top], rf.game_fit || 'cover')];
  }
  if (rf.mode === 'facecam' && rf.facecam) return band(rf.facecam, sw, sh, [0, 0, W, H], 'cover');
  if ((rf.mode === 'game' || rf.mode === 'custom') && rf.game) return band(rf.game, sw, sh, [0, 0, W, H], rf.game_fit || 'cover');
  // center: ventana vertical recortada alrededor de center_x
  const aspect = W / H;
  const [cw, ch] = sw / sh > aspect ? [sh * aspect, sh] : [sw, sw / aspect];
  const x = Math.min(Math.max(rf.center_x * sw - cw / 2, 0), sw - cw);
  return [/** @type {Draw} */ ({ sx: x, sy: (sh - ch) / 2, sw: cw, sh: ch, dx: 0, dy: 0, dw: W, dh: H })];
}

/** Anclaje: factores (0, 0.5, 1) horizontal y vertical de un `anchor`. */
export function anchorFactors(/** @type {string} */ anchor) {
  const h = anchor.endsWith('left') ? 0 : anchor.endsWith('right') ? 1 : 0.5;
  const v = anchor.startsWith('top') ? 0 : anchor.startsWith('bottom') ? 1 : 0.5;
  return [h, v];
}

export const clamp = (/** @type {number} */ v, /** @type {number} */ lo, /** @type {number} */ hi) => Math.min(Math.max(v, lo), hi);
export const round = (/** @type {number} */ v, n = 3) => Math.round(v * 10 ** n) / 10 ** n;
