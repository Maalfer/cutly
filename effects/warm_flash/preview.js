export function render(ctx, img, p, progress, size) {
  ctx.drawImage(img, 0, 0, size.w, size.h);
  const a = p.strength * Math.exp(-6 * progress);
  ctx.globalCompositeOperation = 'screen';
  ctx.fillStyle = `rgb(255, ${Math.round(255 - 90 * p.warmth)}, ${Math.round(255 - 210 * p.warmth)})`;
  ctx.globalAlpha = Math.min(1, a * 1.4);
  ctx.fillRect(0, 0, size.w, size.h);
  ctx.globalAlpha = 1; ctx.globalCompositeOperation = 'source-over';
}
