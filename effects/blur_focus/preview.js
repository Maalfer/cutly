export function render(ctx, img, p, progress, size) {
  ctx.filter = `blur(${p.sigma * (size.w / 1080)}px)`;
  ctx.drawImage(img, 0, 0, size.w, size.h);
  ctx.filter = 'none';
}
