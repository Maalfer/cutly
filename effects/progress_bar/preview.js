export function render(ctx, img, p, progress, size) {
  ctx.drawImage(img, 0, 0, size.w, size.h);
  const th = Math.max(2, p.thickness * size.h);
  ctx.globalAlpha = p.opacity; ctx.fillStyle = p.color;
  ctx.fillRect(0, p.position === 'top' ? 0 : size.h - th, size.w * progress, th);
  ctx.globalAlpha = 1;
}
