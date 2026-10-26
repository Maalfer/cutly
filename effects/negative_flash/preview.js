export function render(ctx, img, p, progress, size) {
  ctx.filter = 'invert(1)';
  ctx.drawImage(img, 0, 0, size.w, size.h);
  ctx.filter = 'none';
}
