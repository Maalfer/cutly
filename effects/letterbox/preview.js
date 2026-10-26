export function render(ctx, img, p, progress, size) {
  ctx.drawImage(img, 0, 0, size.w, size.h);
  const e = Math.min(1, progress * 5, (1 - progress) * 5), h = size.h * p.amount * e;
  ctx.fillStyle = '#000'; ctx.fillRect(0, 0, size.w, h); ctx.fillRect(0, size.h - h, size.w, h);
}
