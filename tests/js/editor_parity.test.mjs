// El JavaScript del editor debe dar los mismos números que el servidor (que es la referencia del render).
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { evalProps } from '../../web/editor/animation.js';
import { timelineStarts, timelineDuration, outputToSource, mapWords } from '../../web/editor/time.js';
import { groupCues, splitLines } from '../../web/editor/subtitles.js';
import { reframePlan } from '../../web/editor/geometry.js';

const fx = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const close = (a, b, msg, eps = 1e-9) => assert.ok(Math.abs(a - b) < eps, `${msg}: ${a} != ${b}`);
let n = 0;

for (const c of fx.animation) {
  const got = evalProps(c.layer, c.tau, c.base_x, c.base_y, c.base_rot);
  for (const k of ['dx', 'dy', 'scale', 'opacity', 'rot']) close(got[k], c.expected[k], `animación ${JSON.stringify(c.layer.animations)} tau=${c.tau} ${k}`);
  n++;
}
for (const c of fx.timeline) {
  const s = timelineStarts(c.timeline);
  s.forEach((v, i) => close(v, c.starts[i], 'inicio de clip'));
  close(timelineDuration(c.timeline), c.duration, 'duración');
  for (const [t, expected] of c.sources) {
    const r = outputToSource(c.timeline, t);
    if (expected === null) continue;
    close(r.source, expected, `salida→origen t=${t}`, 1e-6);
  }
  const mapped = mapWords(c.words, c.timeline);
  assert.equal(mapped.length, c.mapped.length, 'nº de palabras mapeadas');
  mapped.forEach((m, i) => { close(m[0], c.mapped[i][0], 'inicio palabra', 1e-9); close(m[1], c.mapped[i][1], 'fin palabra', 1e-9); assert.equal(m[2], c.mapped[i][2]); });
  n++;
}
for (const c of fx.cues) {
  const got = groupCues(c.words, c.max_words).map((cue) => cue.map((w) => w[2]));
  assert.deepEqual(got, c.cues, `cues max=${c.max_words}`);
  n++;
}
for (const c of fx.lines) {
  assert.deepEqual(splitLines(c.texts, c.max_lines), c.lines, `líneas ${JSON.stringify(c.texts)}`);
  n++;
}
// reencuadre: casos con valores conocidos (el recorte centrado de 16:9 a 9:16 y el apilado)
const [d] = reframePlan({ mode: 'center', center_x: 0.5 }, 1920, 1080, 1080, 1920);
close(d.sw / d.sh, 1080 / 1920, 'proporción del recorte center', 1e-9); close(d.sx, (1920 - d.sw) / 2, 'recorte centrado');
const stack = reframePlan({ mode: 'stack', stack_split: 0.4, facecam: { x: 0.7, y: 0, w: 0.3, h: 0.3 }, game: { x: 0, y: 0, w: 0.7, h: 1 }, game_fit: 'cover' }, 1920, 1080, 1080, 1920);
assert.equal(stack.length, 2); close(stack[0].dh, 768, 'banda superior'); close(stack[1].dy, 768, 'inicio banda inferior');
for (const s of stack) close(s.sw / s.sh, s.dw / s.dh, 'cada banda conserva su proporción (cover)', 1e-6);
const contain = reframePlan({ mode: 'game', game: { x: 0, y: 0, w: 1, h: 1 }, game_fit: 'contain' }, 1920, 1080, 1080, 1920);
assert.equal(contain.length, 2); assert.ok(contain[0].blur && !contain[1].blur); assert.ok(contain[1].dh < 1920);
n++;
console.log(`paridad editor ↔ servidor: ${n} grupos de casos correctos`);
