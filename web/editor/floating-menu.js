// @ts-check
// Posición de un menú desplegable (`.menu`) anclado a un botón, calculada en JS.
//
// `.menu` usa `position:fixed` en vez de `absolute`: varios contenedores del editor (`.ed-top`, `.ed-left`)
// tienen `overflow-x:auto`/`overflow:hidden` para el propio scroll de la barra o del panel, y CSS no permite
// "overflow-x:auto + overflow-y:visible" — el navegador fuerza SIEMPRE el eje no declarado a recortar también
// (spec de CSS Overflow), así que un menú `position:absolute` desplegándose hacia abajo queda invisible,
// recortado dentro de esa barra, aunque exista en el DOM (confirmado: display/visibility/opacity normales,
// pero fuera de la caja de scroll del padre). `fixed` saca el menú del recorte de cualquier ancestro (salvo que
// alguno tenga `transform`/`filter`/`perspective`, que no es el caso aquí); a cambio, su posición ya no es
// relativa al padre y hay que calcularla a mano con el rect real del botón.
import { useEffect, useLayoutEffect, useState } from 'preact/hooks';

/** @param {{current: HTMLElement|null}} anchorRef @param {boolean} open @returns {{top:number, right:number}|null} */
export function useMenuPos(anchorRef, open) {
  const [pos, setPos] = useState(/** @type {{top:number, right:number}|null} */ (null));
  useLayoutEffect(() => {
    if (!open || !anchorRef.current) { setPos(null); return; }
    const place = () => {
      const r = /** @type {HTMLElement} */ (anchorRef.current).getBoundingClientRect();
      setPos({ top: r.bottom + 4, right: Math.max(4, window.innerWidth - r.right) });
    };
    place();
    window.addEventListener('resize', place);
    return () => window.removeEventListener('resize', place);
  }, [open, anchorRef.current]);
  return pos;
}

/** Cierra el menú al tocar/hacer clic fuera de él o con Escape (en táctil no hay «mouseleave» fiable). */
export function useDismiss(/** @type {boolean} */ open, /** @type {(v:boolean)=>void} */ setOpen) {
  useEffect(() => {
    if (!open) return;
    const down = (/** @type {Event} */ e) => {
      const el = /** @type {Element} */ (e.target);
      if (!el.closest?.('.menu') && !el.closest?.('.menu-anchor')) setOpen(false);
    };
    const key = (/** @type {KeyboardEvent} */ e) => { if (e.key === 'Escape') setOpen(false); };
    document.addEventListener('pointerdown', down, true);
    document.addEventListener('keydown', key);
    return () => { document.removeEventListener('pointerdown', down, true); document.removeEventListener('keydown', key); };
  }, [open]);
}
