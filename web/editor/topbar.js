// @ts-check
// Barra superior del editor: volver, proyecto (cambiar/nuevo/renombrar), deshacer/rehacer, comprobar y renderizar.
import { useRef, useState } from 'preact/hooks';
import { html } from '../html.js';
import { api } from '../api.js';
import { navigate, toast } from '../store.js';
import { useDismiss, useMenuPos } from './floating-menu.js';
import { rt } from './preview.js';
import { applyOps, ed, loadProject, refreshProjectList, runChecks, startRender, undoRedo, useEd, get } from './state.js';

export function TopBar() {
  const media = useEd((s) => s.media);
  const projects = useEd((s) => s.projects);
  const pj = useEd((s) => s.project);
  const saving = useEd((s) => s.saving);
  const checking = useEd((s) => s.checking);
  const render = useEd((s) => s.render);
  const issues = useEd((s) => s.issues);
  const [menu, setMenu] = useState(false);
  const btnRef = useRef(/** @type {HTMLButtonElement|null} */ (null));
  const menuPos = useMenuPos(btnRef, menu);
  useDismiss(menu, setMenu);
  if (!pj || !media) return html`<header class="ed-top"><a class="link" href="#/">← Biblioteca</a></header>`;
  const busy = render && !['done', 'failed', 'cancelled'].includes(render.status);
  const problems = issues.filter((/** @type {any} */ i) => i.severity !== 'info').length;

  async function newProject() {
    const dur = get().media.duration, t = rt.player?.t || 0;
    const start = Math.max(0, Math.min(t, dur - 5));
    const p = await api.post('/projects', { json: { media_id: media.id, source_in: start, source_out: Math.min(dur, start + 60), name: `Clip ${projects.length + 1}` } }).catch((/** @type {Error} */ e) => { toast(e.message, 'error'); return null; });
    if (p) { await refreshProjectList(); await loadProject(p.id); }
  }
  async function rename() {
    const name = prompt('Nombre del proyecto', pj.name);
    if (!name || name === pj.name) return;
    const r = await api.patch(`/projects/${pj.id}`, { json: { name } }).catch((/** @type {Error} */ e) => { toast(e.message, 'error'); return null; });
    if (r) { ed.set({ project: { ...get().project, name: r.name } }); refreshProjectList(); }
  }
  async function removeProject() {
    if (!confirm(`¿Borrar el proyecto «${pj.name}»? Se eliminan también sus renders.`)) return;
    await api.del(`/projects/${pj.id}`).catch((/** @type {Error} */ e) => toast(e.message, 'error'));
    await refreshProjectList();
    const rest = get().projects;
    if (rest.length) await loadProject(rest[0].id); else navigate('/');
  }
  async function removeVideo() {
    if (!confirm(`¿Borrar el vídeo «${media.filename}» y todo lo asociado (transcripción, proyectos y renders)? No se puede deshacer.`)) return;
    rt.player?.pause();
    try {
      await api.del(`/media/${media.id}`);
      toast('Vídeo borrado', 'ok');
      navigate('/');
    } catch (e) {
      toast(/** @type {Error} */ (e).message, 'error');
    }
  }
  const frame = () => { const t = (rt.player?.t || 0).toFixed(2); window.open(`/api/v1/projects/${pj.id}/frame?t=${t}&quality=preview&wait=60`, '_blank', 'noopener'); };

  return html`
    <header class="ed-top">
      <a class="link back" href="#/" title="Volver a la biblioteca">←<span class="hide-sm"> Biblioteca</span></a>
      <select class="proj-select" value=${pj.id} onChange=${(/** @type {Event} */ e) => loadProject(/** @type {HTMLSelectElement} */ (e.target).value)} aria-label="Proyecto">
        ${projects.map((/** @type {any} */ p) => html`<option value=${p.id} selected=${p.id === pj.id}>${p.name}</option>`)}
      </select>
      <button class="icon-btn hide-sm" title="Renombrar proyecto" aria-label="Renombrar proyecto" onClick=${rename}>✎</button>
      <button class="small-btn hide-sm" onClick=${newProject} title="Nuevo clip a partir de este vídeo, desde el instante actual">+ Clip</button>
      <span class="grow"></span>
      <span class="save-state muted small hide-sm" aria-live="polite">${saving ? 'Guardando…' : 'Guardado'}</span>
      <button class="icon-btn" disabled=${!pj.can_undo} onClick=${() => undoRedo('undo')} title="Deshacer (Ctrl+Z)" aria-label="Deshacer">↶</button>
      <button class="icon-btn" disabled=${!pj.can_redo} onClick=${() => undoRedo('redo')} title="Rehacer (Ctrl+Shift+Z)" aria-label="Rehacer">↷</button>
      <button class="small-btn hide-sm" onClick=${runChecks} disabled=${checking} title="Comprobaciones automáticas de calidad">${checking ? 'Comprobando…' : 'Comprobar'}${problems ? html` <span class="badge bad">${problems}</span>` : ''}</button>
      <button class="small-btn hide-sm" onClick=${frame} title="Fotograma EXACTO del render en el instante actual (en una pestaña nueva)">Fotograma exacto</button>
      <div class="menu-anchor">
        <button ref=${btnRef} class="primary small-btn" onClick=${() => setMenu(!menu)} disabled=${!!busy} aria-haspopup="menu" aria-expanded=${menu}>${busy ? html`<span class="hide-sm">Renderizando </span>${Math.round(render.progress * 100)} %` : html`<span class="hide-sm">Renderizar ▾</span><span class="show-sm">Exportar ▾</span>`}</button>
        ${menu && menuPos && html`<div class="menu" role="menu" style=${{ top: menuPos.top + 'px', right: menuPos.right + 'px' }} onMouseLeave=${(/** @type {MouseEvent} */ e) => { if (e.pointerType !== 'touch') setMenu(false); }}>
          <button role="menuitem" class="show-sm" onClick=${() => { setMenu(false); runChecks(); }}>✔ Comprobar calidad${problems ? ` (${problems} avisos)` : ''}</button>
          <button role="menuitem" class="show-sm" onClick=${() => { setMenu(false); newProject(); }}>＋ Nuevo clip desde aquí</button>
          <button role="menuitem" class="show-sm" onClick=${() => { setMenu(false); rename(); }}>✎ Renombrar proyecto</button>
          <button role="menuitem" class="show-sm" onClick=${() => { setMenu(false); frame(); }}>▣ Fotograma exacto</button>
          <hr class="show-sm" />
          <button role="menuitem" onClick=${() => { setMenu(false); startRender('draft'); }}>Borrador rápido (baja calidad)</button>
          <button role="menuitem" onClick=${() => { setMenu(false); startRender('final'); }}>Final (calidad completa)</button>
          <button role="menuitem" onClick=${() => { setMenu(false); startRender('draft', { start: Math.max(0, (rt.player?.t || 0) - 3), end: (rt.player?.t || 0) + 5 }); }}>Borrador de ±5 s alrededor del cursor</button>
          <hr />
          <button role="menuitem" onClick=${() => { setMenu(false); removeProject(); }} class="danger-text">Borrar este proyecto…</button>
          <button role="menuitem" onClick=${() => { setMenu(false); removeVideo(); }} class="danger-text">Borrar el vídeo completo…</button>
          <a role="menuitem" href=${`#/media/${media.id}`}>Detalles del vídeo y transcripción…</a>
        </div>`}
      </div>
      ${render?.status === 'done' && html`<a class="small-btn linkbtn" href=${`/api/v1/renders/${render.job}/download`} download aria-label="Descargar el render"><span aria-hidden="true">⬇</span><span class="hide-sm"> Descargar ${render.quality === 'final' ? 'final' : 'borrador'}</span></a>`}
      ${render?.status === 'failed' && html`<span class="error small" title=${render.error}>Render fallido</span>`}
    </header>
  `;
}
export { applyOps };
