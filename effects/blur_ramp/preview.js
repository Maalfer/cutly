export function render(ctx, img, p, progress, size) {
  const k = p.mode === 'out' ? 1 - progress : p.mode === 'in_out' ? 1 - Math.abs(2 * progress - 1) : progress;
  ctx.filter = `blur(${p.sigma * k * (size.w / 1080)}px)`;
  ctx.drawImage(img, 0, 0, size.w, size.h);
  ctx.filter = 'none';
}
