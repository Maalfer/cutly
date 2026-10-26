// Preview del navegador (Canvas 2D). Debe imitar el render; márcalo "approximate" en effect.json si no es idéntico.
// ctx: CanvasRenderingContext2D · img: fotograma base · p: parámetros · progress: 0..1 dentro de la layer · size: {w, h}
export function render(ctx, img, p, progress, size) {
  const e = Math.sin(Math.PI * progress);
  ctx.filter = `saturate(${1 + p.intensity * e})`;
  ctx.drawImage(img, 0, 0, size.w, size.h);
  ctx.filter = 'none';
}
