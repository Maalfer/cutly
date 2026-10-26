export function render(ctx, img, p, progress, size) {
  ctx.drawImage(img, 0, 0, size.w, size.h);
  const g = ctx.createRadialGradient(size.w / 2, size.h / 2, size.h * 0.25, size.w / 2, size.h / 2, size.h * 0.8);
  g.addColorStop(0, 'rgba(0,0,0,0)'); g.addColorStop(1, `rgba(0,0,0,${p.strength})`);
  ctx.fillStyle = g; ctx.fillRect(0, 0, size.w, size.h);
}
