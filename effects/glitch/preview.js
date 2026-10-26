export function render(ctx, img, p, progress, size) {
  const a = p.intensity * (size.w / 1080), flip = Math.floor(progress * 3 * p.rate) % 2 ? 1 : -1;
  ctx.drawImage(img, 0, 0, size.w, size.h);
  ctx.globalCompositeOperation = 'screen'; ctx.globalAlpha = 0.5;
  ctx.drawImage(img, a * flip, 0, size.w, size.h);
  ctx.globalCompositeOperation = 'source-over'; ctx.globalAlpha = 1;
}
