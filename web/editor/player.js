// @ts-check
// Reproductor: sincroniza un <video> (el proxy) con el reloj del CLIP RESULTANTE (varios clips, velocidades).
import { clipDuration, outputToSource, timelineDuration, timelineStarts } from './time.js';

export class Player {
  constructor(/** @type {HTMLVideoElement} */ video) {
    this.video = video;
    /** @type {any[]} */ this.timeline = [];
    this.index = 0;
    this._t = 0;
    this.playing = false;
    /** @type {(t:number)=>void} */ this.onFrame = () => {};
    /** @type {(playing:boolean)=>void} */ this.onState = () => {};
    this._raf = 0;
    video.playsInline = true;
    video.preload = 'auto';
    video.addEventListener('seeked', () => { if (!this.playing) this.onFrame(this._t); });
    video.addEventListener('loadeddata', () => this.onFrame(this._t));
    video.addEventListener('ended', () => this.pause());
  }

  get t() { return this._t; }
  get duration() { return timelineDuration(this.timeline); }

  setSource(/** @type {string} */ url) {
    if (this.video.getAttribute('data-src') !== url) { this.video.setAttribute('data-src', url); this.video.src = url; this.video.load(); }
  }

  /** Cambia la línea de tiempo (tras una edición) conservando el instante actual si cabe. */
  setTimeline(/** @type {any[]} */ tl) {
    this.timeline = tl;
    if (!this.playing) this.seek(Math.min(this._t, Math.max(this.duration - 0.001, 0)));
  }

  seek(/** @type {number} */ t) {
    const tt = Math.min(Math.max(t, 0), this.duration);
    const r = outputToSource(this.timeline, tt);
    this._t = tt;
    if (!r) { this.onFrame(this._t); return; }
    this.index = r.index;
    this.video.playbackRate = Math.min(Math.max(r.clip.speed || 1, 0.25), 4);
    if (Math.abs(this.video.currentTime - r.source) > 0.01 || this.video.currentTime < r.source - 0.01) this.video.currentTime = r.source;
    else if (!this.playing) this.onFrame(this._t);
    if (this.playing) return;
    this.onFrame(this._t);
  }

  play() {
    if (this.playing || !this.timeline.length) return;
    if (this._t >= this.duration - 0.03) this.seek(0);
    else this.seek(this._t);
    this.playing = true;
    this.onState(true);
    try { this.video.play().catch(() => {}); } catch(e) {}
    this._loop();
  }

  pause() {
    this.playing = false;
    try { this.video.pause(); } catch(e) {}
    cancelAnimationFrame(this._raf);
    this.onState(false);
    this.onFrame(this._t);
  }

  toggle() { this.playing ? this.pause() : this.play(); }

  _loop() {
    const step = () => {
      if (!this.playing) return;
      const tl = this.timeline, c = tl[this.index];
      if (c) {
        const v = this.video.currentTime, starts = timelineStarts(tl), sp = c.speed || 1;
        if (v >= c.source_out - 0.02) {
          // Buscar siguiente clip en el tiempo de salida (puede haber hueco)
          const curStart = starts[this.index];
          const curEnd = curStart + clipDuration(c);
          let found = -1;
          for (let j = 0; j < tl.length; j++) {
            if (j === this.index) continue;
            if (starts[j] <= curEnd + 0.01 && starts[j] + clipDuration(tl[j]) >= curEnd - 0.01) { found = j; break; }
            if (starts[j] > curStart) { found = j; break; }
          }
          if (found >= 0 && starts[found] <= curEnd + 0.5) {
            const n = tl[found], overlap = Math.max(curEnd - starts[found], 0);
            this.index = found;
            this.video.playbackRate = Math.min(Math.max(n.speed || 1, 0.25), 4);
            this.video.currentTime = n.source_in + overlap * (n.speed || 1);
          } else {
            this._t = this.duration;
            this.pause();
            return;
          }
        } else {
          this._t = starts[this.index] + Math.max(v - c.source_in, 0) / sp;
        }
      } else {
        this._t = this.duration;
        this.pause();
        return;
      }
      this.onFrame(this._t);
      this._raf = requestAnimationFrame(step);
    };
    this._raf = requestAnimationFrame(step);
  }
}
