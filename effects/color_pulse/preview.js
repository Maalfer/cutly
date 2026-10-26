export function render(ctx, img, p, progress, size) {
  const e = Math.sin(Math.PI * progress);
  ctx.filter = `saturate(${1 + (p.saturation - 1) * e}) contrast(${1 + (p.contrast - 1) * e})`;
  ctx.drawImage(img, 0, 0, size.w, size.h);
  ctx.filter = 'none';
}
