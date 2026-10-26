// @ts-check
// Forma de onda en Canvas 2D. Los picos vienen precalculados del servidor; nunca se decodifica audio aquí.
import { useEffect, useRef } from 'preact/hooks';
import { html } from '../html.js';
import { api } from '../api.js';
import { fmtTime } from '../util.js';

/** @param {{mediaId:string, duration:number, video:{current:HTMLVideoElement|null}}} p */
export function Waveform({ mediaId, duration, video }) {
  const wrap = useRef(/** @type {HTMLDivElement|null} */ (null));
  const canvas = useRef(/** @type {HTMLCanvasElement|null} */ (null));
  const head = useRef(/** @type {HTMLDivElement|null} */ (null));

  useEffect(() => {
    const el = wrap.current, cv = canvas.current;
    if (!el || !cv) return;
    let timer = 0, alive = true;
    async function draw() {
      const dpr = window.devicePixelRatio || 1;
      const w = Math.floor(/** @type {HTMLElement} */ (el).clientWidth), hgt = 72;
      const c = /** @type {HTMLCanvasElement} */ (cv);
      c.width = w * dpr; c.height = hgt * dpr;
      c.style.height = hgt + 'px';
      const ctx = /** @type {CanvasRenderingContext2D} */ (c.getContext('2d'));
      ctx.scale(dpr, dpr);
      const styles = getComputedStyle(c);
      try {
        const p = await api.get(`/media/${mediaId}/peaks?bins=${Math.min(w * 1, 4000)}`);
        if (!alive) return;
        ctx.clearRect(0, 0, w, hgt);
        ctx.fillStyle = styles.getPropertyValue('--wave').trim() || '#6d5efc';
        const mid = hgt / 2;
        for (let i = 0; i < p.count; i++) {
          const x = (i / p.count) * w;
          const top = (p.max[i] / p.scale) * mid, bot = (p.min[i] / p.scale) * mid;
          ctx.fillRect(x, mid - Math.max(top, 0.5), Math.max(w / p.count, 1), Math.max(top - bot, 1));
        }
      } catch { ctx.fillStyle = styles.color; ctx.fillText('Forma de onda no disponible', 8, 36); }
    }
    draw();
    const ro = new ResizeObserver(() => { clearTimeout(timer); timer = window.setTimeout(draw, 200); });
    ro.observe(el);
    return () => { alive = false; ro.disconnect(); clearTimeout(timer); };
  }, [mediaId]);

  // Cabezal: se mueve con CSS (sin redibujar el canvas ni re-renderizar Preact).
  useEffect(() => {
    const v = video.current;
    if (!v) return;
    const upd = () => { if (head.current && duration) head.current.style.left = (v.currentTime / duration) * 100 + '%'; };
    v.addEventListener('timeupdate', upd); v.addEventListener('seeked', upd);
    return () => { v.removeEventListener('timeupdate', upd); v.removeEventListener('seeked', upd); };
  }, [duration]);

  function seekTo(/** @type {number} */ t) {
    if (video.current) video.current.currentTime = Math.min(Math.max(t, 0), duration);
  }
  return html`
    <div class="wave" ref=${wrap} role="slider" tabindex="0" aria-label="Posición del vídeo" aria-valuemin="0"
         aria-valuemax=${Math.floor(duration)} aria-valuetext=${fmtTime(video.current?.currentTime || 0)}
         onPointerDown=${(/** @type {PointerEvent} */ e) => { const r = /** @type {HTMLElement} */ (e.currentTarget).getBoundingClientRect(); seekTo(((e.clientX - r.left) / r.width) * duration); }}
         onKeyDown=${(/** @type {KeyboardEvent} */ e) => {
           const cur = video.current?.currentTime || 0;
           if (e.key === 'ArrowRight') { seekTo(cur + (e.shiftKey ? 30 : 5)); e.preventDefault(); }
           if (e.key === 'ArrowLeft') { seekTo(cur - (e.shiftKey ? 30 : 5)); e.preventDefault(); }
         }}>
      <canvas ref=${canvas}></canvas>
      <div class="playhead" ref=${head}></div>
    </div>`;
}
