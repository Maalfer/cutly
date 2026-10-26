// @ts-check
// Subtítulos: port de services/render/ass.py (group_cues y _lines), para que el preview agrupe igual que el render.

const PAUSE_BREAK = 0.8;
const LINE_CHARS = 17;
const SENTENCE_END = /[.!?…]+["'»”)\]]*$/;

/** @typedef {[number, number, string]} W */

export function groupCues(/** @type {W[]} */ words, /** @type {number} */ maxWords) {
  /** @type {W[][]} */
  const cues = [];
  /** @type {W[]} */
  let cur = [];
  for (const w of words) {
    if (cur.length && w[0] - cur[cur.length - 1][1] > PAUSE_BREAK) { cues.push(cur); cur = []; }
    cur.push(w);
    if (cur.length >= maxWords || SENTENCE_END.test(w[2])) { cues.push(cur); cur = []; }
  }
  if (cur.length) cues.push(cur);
  return cues;
}

/** Reparte los índices de palabra en hasta `maxLines` líneas equilibradas por nº de letras (sin palabras huérfanas). */
export function splitLines(/** @type {string[]} */ texts, /** @type {number} */ maxLines) {
  const n = texts.length;
  const total = texts.reduce((a, t) => a + t.length, 0) + n - 1;
  if (maxLines <= 1 || n < 2 || total <= LINE_CHARS) return [[...Array(n).keys()]];
  const k = Math.min(maxLines, n);
  let best = null, bestLen = Infinity;
  const choose = (/** @type {number} */ start, /** @type {number[]} */ cuts) => {
    if (cuts.length === k - 1) {
      const bounds = [0, ...cuts, n];
      const groups = Array.from({ length: k }, (_, i) => Array.from({ length: bounds[i + 1] - bounds[i] }, (_, j) => bounds[i] + j));
      const longest = Math.max(...groups.map((g) => g.reduce((a, j) => a + texts[j].length, 0) + g.length - 1));
      if (longest < bestLen) { bestLen = longest; best = groups; }
      return;
    }
    for (let c = start; c < n; c++) choose(c + 1, [...cuts, c]);
  };
  choose(1, []);
  return /** @type {number[][]} */ (best);
}

/**
 * Subtítulo activo en `t`: {lines:[[{text,active}]]} o null. `words` ya en el reloj del clip.
 * Misma regla que el render: la palabra activa es la que se está diciendo (o la última dicha del cue).
 */
export function activeCue(/** @type {W[][]} */ cues, /** @type {number} */ t, /** @type {any} */ style) {
  for (const cue of cues) {
    const start = cue[0][0], end = cue[cue.length - 1][1] + 0.12;
    if (t < start || t >= end) continue;
    let active = 0;
    cue.forEach((w, i) => { if (t >= w[0]) active = i; });
    const texts = cue.map((w) => (style.uppercase ? w[2].toUpperCase() : w[2]));
    // Forzar siempre una sola línea
    const lines = [[...Array(texts.length).keys()]].map((idxs) => idxs.map((j) => ({ text: texts[j], active: j === active })));
    return { lines, progress: Math.min(1, (t - cue[active][0]) / 0.09) };
  }
  return null;
}
