// @ts-check
// Tiempos de la línea de tiempo: mismos cálculos que el servidor (schema/project.py y render/ass.py).

/** @typedef {{id:string, source_in:number, source_out:number, speed:number, transition_in?:{name:string,dur:number}|null}} Clip */

export const clipDuration = (/** @type {Clip} */ c) => (c.source_out - c.source_in) / (c.speed || 1);

/** Instante de salida en que empieza cada clip (con transición empieza `dur` antes de que acabe el anterior). */
export function timelineStarts(/** @type {Clip[]} */ tl) {
  const starts = [];
  let t = 0;
  tl.forEach((c, i) => {
    if (c.start_at != null) {
      let s = c.start_at;
      if (i && c.transition_in) s -= c.transition_in.dur;
      starts.push(s);
      t = s + clipDuration(c);
      return;
    }
    if (i && c.transition_in) t -= c.transition_in.dur;
    starts.push(t);
    t += clipDuration(c);
  });
  return starts;
}

export function timelineDuration(/** @type {Clip[]} */ tl) {
  if (!tl.length) return 0;
  const s = timelineStarts(tl);
  let end = 0;
  for (let i = 0; i < tl.length; i++) end = Math.max(end, s[i] + clipDuration(tl[i]));
  return Math.round(end * 1000) / 1000;
}

/**
 * Del tiempo de salida al del original: {index, clip, source, start} (el clip que se ve en `t`).
 * Igual que el servidor: durante un solape de transición manda el clip que SALE hasta que termina.
 * Fuera de rango se acota al primero (t<0) o al final del último.
 */
export function outputToSource(/** @type {Clip[]} */ tl, /** @type {number} */ t) {
  if (!tl.length) return null;
  const starts = timelineStarts(tl);
  for (let i = 0; i < tl.length; i++) {
    const d = clipDuration(tl[i]);
    if (t >= starts[i] - 1e-9 && t < starts[i] + d - 1e-9) {
      return { index: i, clip: tl[i], source: tl[i].source_in + Math.max(t - starts[i], 0) * (tl[i].speed || 1), start: starts[i] };
    }
  }
  const last = tl.length - 1;
  if (t < 0) return { index: 0, clip: tl[0], source: tl[0].source_in, start: 0 };
  return { index: last, clip: tl[last], source: tl[last].source_out, start: starts[last] };
}

/** Palabras del original → (inicio, fin, texto) en el reloj del clip resultante; descarta las que caen fuera. */
export function mapWords(/** @type {{w:string,start:number,end:number}[]} */ words, /** @type {Clip[]} */ tl) {
  const starts = timelineStarts(tl);
  const out = [];
  for (const w of words) {
    for (let i = 0; i < tl.length; i++) {
      const c = tl[i];
      if (w.end > c.source_in && w.start < c.source_out) {
        const sp = c.speed || 1;
        const s = starts[i] + (Math.max(w.start, c.source_in) - c.source_in) / sp;
        const e = starts[i] + (Math.min(w.end, c.source_out) - c.source_in) / sp;
        if (e - s > 0.01) out.push([s, e, w.w]);
        break;
      }
    }
  }
  return out;
}

export const fmtClock = (/** @type {number} */ t) => {
  t = Math.max(0, t || 0);
  const m = Math.floor(t / 60), s = t - m * 60;
  return `${m}:${s.toFixed(2).padStart(5, '0')}`;
};
