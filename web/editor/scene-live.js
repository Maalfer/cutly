// @ts-check
// Capas `scene` con `code`: se ven REPRODUCIÉNDOSE de verdad en el editor, no como un marcador. El HTML/JS del
// agente corre en un <iframe sandbox> propio (origen aislado, sin acceso al DOM del editor), superpuesto al
// canvas con `position:fixed` (así no lo recorta el `overflow` de ningún contenedor — ver floating-menu.js).
//
// El documento se carga navegando el iframe con un <form method="POST"> hacia `/api/v1/scenes/live-doc` (ver
// ese endpoint): NO con `srcdoc`/`blob:`. Ambos heredan la Content-Security-Policy estricta del propio editor
// (`script-src 'self' '<hash>'`), que bloquearía EN SILENCIO cualquier <script> inline — tanto el harness del
// reloj como el código del agente — sin lanzar ningún error de JavaScript capturable (solo un aviso en la
// consola del navegador). Confirmado con Chromium real antes de llegar a este diseño. La respuesta de esa ruta
// (bajo /api/, sin esa CSP) sí puede ejecutar scripts inline con normalidad.
//
// El reloj del iframe lo controla este módulo, no el navegador: el harness que inyecta el servidor sustituye
// performance.now/requestAnimationFrame por versiones controladas por mensajes `postMessage`, así que el
// dibujo avanza EXACTAMENTE con el tiempo del reproductor (si se pausa el vídeo, se congela; si se
// adelanta/retrocede, salta) en vez de con el reloj real del sistema. El estado de estas animaciones es
// acumulativo (como un vídeo grabado, no una función del tiempo): un salto grande (clic en la línea de tiempo,
// no el avance normal de la reproducción) recarga el iframe entero y lo adelanta con una ráfaga de pasos
// pequeños hasta el instante correcto.
const SEEK_THRESHOLD_S = 0.4; // por debajo de esto, se trata como avance normal (tick con el delta real)
const FAST_FORWARD_STEP_MS = 1000 / 50;
let nextFrameId = 1;

/** Navega `iframe` (ya debe estar en el DOM) a `/scenes/live-doc` vía POST con `code` como único campo. */
function postToIframe(/** @type {HTMLIFrameElement} */ iframe, /** @type {string} */ code, /** @type {string} */ params, /** @type {string} */ words) {
  const form = document.createElement('form');
  form.method = 'POST';
  form.action = '/api/v1/scenes/live-doc';
  form.target = iframe.name;
  form.style.display = 'none';
  // <textarea>, no <input>: un <input> de una línea ELIMINA los saltos de línea del valor, y un `// comentario`
  // en la primera línea del script del agente se comería todo el resto (la escena nunca arrancaría).
  const input = document.createElement('textarea');
  input.name = 'code';
  input.value = code;
  form.appendChild(input);
  const p = document.createElement('textarea');
  p.name = 'params';
  p.value = params;
  form.appendChild(p);
  const wd = document.createElement('textarea');
  wd.name = 'words';
  wd.value = words;
  form.appendChild(wd);
  document.body.appendChild(form);
  form.submit();
  form.remove();
}

/** Un iframe vivo para una capa. No sabe de mensajes: SceneLive escucha y llama a sus métodos. */
class LiveLayer {
  constructor(/** @type {string} */ code, /** @type {string} */ params, /** @type {string} */ words) {
    this.code = code;
    this.words = words; // JSON de las palabras dichas durante la capa -> window.CUTLY_WORDS
    this.params = params; // JSON de layer.params -> window.CUTLY_PARAMS dentro de la escena
    this.el = document.createElement('iframe');
    this.el.name = `cutly-scene-${nextFrameId++}`;
    this.el.setAttribute('sandbox', 'allow-scripts allow-forms');
    this.el.setAttribute('title', 'Vista previa en vivo de la escena');
    // Opaco siempre (igual que al renderizar: estas escenas no llevan canal alfa), pero empieza invisible:
    // cargar el documento + el primer salto es asíncrono, y sin esto se ve un destello negro mientras tanto
    // (debajo se sigue viendo el vídeo normal hasta que la escena está lista para mostrarse).
    this.el.style.cssText = 'position:fixed;border:0;pointer-events:none;background:#000;opacity:0;transition:opacity .15s;';
    this.ready = false;
    this.lastT = /** @type {number|null} */ (null); // último tiempo (relativo a la capa) ya dibujado
    this.goTarget = /** @type {number|null} */ (null); // tiempo al que ir en cuanto el iframe esté listo
  }

  /** Solo tras añadirse al DOM: un <form target="..."> necesita que el iframe destino ya exista. */
  load() {
    postToIframe(this.el, this.code, this.params, this.words);
  }

  /** @param {number} tRel segundos desde el inicio de la capa */
  setTime(tRel) {
    if (!this.ready) { this.goTarget = tRel; return; }
    if (this.lastT == null || tRel < this.lastT - 1e-6 || tRel - this.lastT > SEEK_THRESHOLD_S) this._reloadTo(tRel);
    else { this._tick((tRel - this.lastT) * 1000); this.lastT = tRel; }
  }

  /** Avisa que el iframe terminó de cargar (harness listo): hace el salto pendiente, si lo había. */
  onReady() {
    this.ready = true;
    if (this.goTarget != null) { const target = this.goTarget; this.goTarget = null; this._fastForward(target); }
    else this.el.style.opacity = '1';
  }

  _reloadTo(tRel) {
    this.ready = false;
    this.goTarget = tRel;
    this.lastT = null;
    this.el.style.opacity = '0'; // se oculta mientras recarga: debajo se ve el vídeo, no un fotograma a medio pintar
    this.load();
  }

  _fastForward(tRel) {
    let t = 0;
    while (t + FAST_FORWARD_STEP_MS / 1000 < tRel) { this._tick(FAST_FORWARD_STEP_MS); t += FAST_FORWARD_STEP_MS / 1000; }
    if (tRel - t > 1e-4) this._tick((tRel - t) * 1000);
    this.lastT = tRel;
    this.el.style.opacity = '1';
  }

  _tick(ms) {
    try { this.el.contentWindow?.postMessage({ __cutly: 'tick', ms }, '*'); } catch (e) { /* iframe ya destruido */ }
  }

  destroy() { this.el.remove(); }
}

export class SceneLive {
  constructor(/** @type {HTMLElement} */ host) {
    this.host = host; // normalmente document.body: position:fixed no necesita un padre concreto
    /** @type {Map<string, LiveLayer & {code:string}>} */ this.live = new Map();
    this.errorLayers = new Set(); // capas cuyo JS falló: se avisa una vez, no en cada fotograma
    /** @type {(id:string, message:string)=>void} */ this.onError = () => {};
    window.addEventListener('message', (/** @type {MessageEvent} */ ev) => {
      for (const [id, entry] of this.live) {
        if (ev.source !== entry.el.contentWindow) continue;
        const d = ev.data;
        if (d?.__cutly === 'ready') entry.onReady();
        else if (d?.__cutly === 'error' && !this.errorLayers.has(id)) { this.errorLayers.add(id); this.onError(id, d.message); }
        break;
      }
    });
  }

  /** @param {any[]} activeLayers capas `scene` con `code` activas en este fotograma (ya filtradas por start/end)
   *  @param {number} t tiempo absoluto del clip @param {DOMRect} canvasRect rect del canvas en el viewport
   *  @param {number} logicalW ancho en píxeles del fotograma de salida: el iframe se maqueta a TAMAÑO REAL (como
   *  el viewport de Chromium al renderizar) y se reduce con transform, para que textos/tamaños en px del agente
   *  guarden las mismas proporciones que en el vídeo final. */
  sync(activeLayers, t, canvasRect, logicalW = canvasRect.width, wordsFor = (/** @type {any} */ _l) => []) {
    const seen = new Set();
    for (const layer of activeLayers) {
      seen.add(layer.id);
      let entry = this.live.get(layer.id);
      const paramsJson = JSON.stringify(layer.params || {});
      const wordsJson = JSON.stringify(wordsFor(layer));
      if (!entry || entry.code !== layer.code || entry.params !== paramsJson || entry.words !== wordsJson) {
        entry?.destroy();
        entry = /** @type {any} */ (new LiveLayer(layer.code, paramsJson, wordsJson));
        this.host.appendChild(entry.el); // debe estar en el DOM antes de poder ser target de un <form>
        entry.load();
        this.live.set(layer.id, entry);
        this.errorLayers.delete(layer.id);
      }
      const b = layer.box || { x: 0.5, y: 0.5, w: 1, h: 1, anchor: 'center' };
      const fx = b.anchor?.endsWith('left') ? 0 : b.anchor?.endsWith('right') ? 1 : 0.5;
      const fy = b.anchor?.startsWith('top') ? 0 : b.anchor?.startsWith('bottom') ? 1 : 0.5;
      const k = canvasRect.width / logicalW; // escala pantalla/salida
      const w = b.w * canvasRect.width, h = (b.h || b.w * (16 / 9)) * canvasRect.height; // tamaño en pantalla
      entry.el.style.left = `${canvasRect.left + b.x * canvasRect.width - w * fx}px`;
      entry.el.style.top = `${canvasRect.top + b.y * canvasRect.height - h * fy}px`;
      entry.el.style.width = `${w / k}px`;
      entry.el.style.height = `${h / k}px`;
      entry.el.style.transformOrigin = '0 0';
      entry.el.style.transform = `scale(${k})`;
      entry.setTime(t - layer.start);
    }
    for (const [id, entry] of this.live) {
      if (!seen.has(id)) { entry.destroy(); this.live.delete(id); this.errorLayers.delete(id); }
    }
  }

  destroyAll() {
    for (const entry of this.live.values()) entry.destroy();
    this.live.clear();
  }
}
