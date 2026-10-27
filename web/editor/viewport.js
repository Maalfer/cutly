// @ts-check
// Detección de pantalla del editor: móvil/estrecha (la misma condición que el CSS `max-width:1000px`) y puntero táctil.
import { useEffect, useState } from 'preact/hooks';

const NARROW = '(max-width: 1000px)';
const COARSE = '(pointer: coarse)';

export const isNarrow = () => matchMedia(NARROW).matches;
/** Pantalla táctil principal (dedos, no ratón): objetivos de toque más grandes y gestos. */
export const isCoarse = () => matchMedia(COARSE).matches;

/** @param {string} query */
function useMedia(query) {
  const [v, setV] = useState(() => matchMedia(query).matches);
  useEffect(() => {
    const m = matchMedia(query), f = () => setV(m.matches);
    m.addEventListener('change', f);
    f();
    return () => m.removeEventListener('change', f);
  }, [query]);
  return v;
}

export const useNarrow = () => useMedia(NARROW);
export const useCoarse = () => useMedia(COARSE);

/**
 * Mantiene `--vvh` (altura visible real, descontando el teclado en pantalla) en el elemento y `data-kbd` cuando el teclado
 * está abierto: en iOS `100dvh` no encoge con el teclado y los campos quedarían tapados.
 * @param {{current: HTMLElement|null}} ref
 */
export function useVisualViewport(ref) {
  useEffect(() => {
    const vv = window.visualViewport;
    if (!vv) return;
    let max = vv.height;
    const f = () => {
      const el = ref.current;
      if (!el) return;
      if (vv.height > max) max = vv.height;
      el.style.setProperty('--vvh', vv.height + 'px');
      el.dataset.kbd = vv.height < max * 0.75 ? '1' : '';
      if (el.dataset.kbd) window.scrollTo(0, 0);
    };
    f();
    vv.addEventListener('resize', f);
    window.addEventListener('orientationchange', () => { max = 0; setTimeout(f, 300); });
    return () => vv.removeEventListener('resize', f);
  }, []);
}
