// @ts-check
// Página del editor: rejilla (barra, paneles laterales, vista previa, línea de tiempo), atajos y modo móvil por pestañas.
import { useEffect, useState, useRef } from 'preact/hooks';
import { html } from '../html.js';
import { LayersPanel } from './layers.js';
import { Preview, rt } from './preview.js';
import { TopBar } from './topbar.js';
import { Timeline } from './timeline.js';
import { Inspector } from './inspector.js';
import { Library } from './library.js';
import { TranscriptPanel } from './transcript.js';
import { deleteSelected, duplicateLayer, splitAtPlayhead } from './ops.js';
import { ed, get, openMedia, select, undoRedo, useEd } from './state.js';

const TABS = /** @type {[string,string][]} */ ([['layers', 'Capas'], ['library', 'Biblioteca'], ['transcript', 'Transcripción']]);

export function Editor({ mediaId }) {
  const loading = useEd((s) => s.loading);
  const error = useEd((s) => s.error);
  const left = useEd((s) => s.left);
  const timelineH = useEd((s) => s.timelineH);
  const [mobile, setMobile] = useState('timeline'); // móvil: qué panel inferior se ve
  const resizeRef = useRef(/** @type {HTMLDivElement|null} */ (null));
  const dragging = useRef(false);

  useEffect(() => {
    const onMove = (/** @type {MouseEvent} */ e) => {
      if (!dragging.current) return;
      const h = Math.min(Math.max(e.clientY - 48 - 1, 150), window.innerHeight - 200);
      ed.set({ timelineH: h });
    };
    const onUp = () => { if (dragging.current) { dragging.current = false; resizeRef.current?.classList.remove('dragging'); document.body.style.userSelect = ''; } };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
    return () => { window.removeEventListener('mousemove', onMove); window.removeEventListener('mouseup', onUp); };
  }, []);

  useEffect(() => { openMedia(mediaId); return () => rt.player?.pause(); }, [mediaId]);

  useEffect(() => {
    const onKey = (/** @type {KeyboardEvent} */ e) => {
      const el = /** @type {HTMLElement} */ (e.target);
      if (el && (/^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName) || el.isContentEditable)) return;
      const p = rt.player, mod = e.ctrlKey || e.metaKey;
      if (!p || !get().doc) return;
      const key = e.key.toLowerCase();
      if (key === ' ') { e.preventDefault(); if (p.playing) p.pause(); else p.play(); }
      else if (key === 'arrowleft') { e.preventDefault(); p.seek(p.t - (e.shiftKey ? 1 : 1 / 30)); }
      else if (key === 'arrowright') { e.preventDefault(); p.seek(p.t + (e.shiftKey ? 1 : 1 / 30)); }
      else if (key === 'home') { e.preventDefault(); p.seek(0); }
      else if (key === 'end') { e.preventDefault(); p.seek(p.duration); }
      else if (mod && key === 'z') { e.preventDefault(); undoRedo(e.shiftKey ? 'redo' : 'undo'); }
      else if (mod && key === 'y') { e.preventDefault(); undoRedo('redo'); }
      else if (mod && key === 'd') { e.preventDefault(); const s = get().selection; if (s.kind === 'layer' && s.id) duplicateLayer(s.id); }
      else if (key === 's' && !mod) { e.preventDefault(); splitAtPlayhead(); }
      else if (key === 'delete' || key === 'backspace') { e.preventDefault(); deleteSelected(); }
      else if (key === 'escape') select('none');
      else if (key === '+' || key === '=') ed.set({ zoom: Math.min(get().zoom * 1.25, 600) });
      else if (key === '-') ed.set({ zoom: Math.max(get().zoom / 1.25, 4) });
      else if (key === '[' || key === ']') {
        const s = get().selection;
        if (s.kind === 'layer' && s.id) import('./state.js').then((m) => m.patchLayer(/** @type {string} */ (s.id), key === '[' ? { start: +p.t.toFixed(2) } : { end: +p.t.toFixed(2) }, true));
      }
    };
    addEventListener('keydown', onKey);
    return () => removeEventListener('keydown', onKey);
  }, []);

  if (error) return html`<div class="ed-fatal"><p class="error">${error}</p><a class="link" href="#/">← Volver a la biblioteca</a></div>`;
  if (loading) return html`<div class="ed-fatal"><p class="muted">Abriendo el editor…</p></div>`;

  return html`
    <div class=${'editor m-' + mobile} data-mobile=${mobile} style=${'grid-template-rows: 48px minmax(0, 1fr) 1px ' + timelineH + 'px'}>
      <${TopBar} />
      <aside class="ed-left">
        <div class="tabs" role="tablist">${TABS.map(([id, label]) => html`<button role="tab" aria-selected=${left === id} class=${left === id ? 'on' : ''} onClick=${() => ed.set({ left: id })}>${label}</button>`)}</div>
        ${left === 'layers' && html`<${LayersPanel} />`}
        ${left === 'library' && html`<${Library} />`}
        ${left === 'transcript' && html`<${TranscriptPanel} />`}
      </aside>
      <main class="ed-stage"><${Preview} /></main>
      <aside class="ed-right"><${Inspector} /></aside>
      <div ref=${resizeRef} class="tl-resize" onMouseDown=${(/** @type {MouseEvent} */ e) => { e.preventDefault(); dragging.current = true; resizeRef.current?.classList.add('dragging'); document.body.style.userSelect = 'none'; }}></div>
      <section class="ed-timeline"><${Timeline} /></section>
      <nav class="ed-mobile-tabs" aria-label="Paneles">
        ${[['timeline', 'Línea de tiempo'], ['left', 'Capas y más'], ['right', 'Ajustes']].map(([id, label]) => html`<button class=${mobile === id ? 'on' : ''} onClick=${() => setMobile(id)}>${label}</button>`)}
      </nav>
    </div>`;
}
