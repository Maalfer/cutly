export function render(ctx, img, p, progress, size) {
  const e = Math.sin(Math.PI * progress), t = progress * 3;
  const z = 1 + 2.4 * p.intensity * e;
  const w = size.w * z, h = size.h * z;
  const dx = p.intensity * size.w * e * Math.sin(6.28 * p.frequency * t), dy = p.intensity * size.h * 0.8 * e * Math.cos(5.2 * p.frequency * t + 1);
  ctx.drawImage(img, -(w - size.w) / 2 + dx, -(h - size.h) / 2 + dy, w, h);
}
