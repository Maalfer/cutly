export function render(ctx, img, p, progress, size) {
  const e = Math.sin(Math.PI * progress), z = 1 + (p.scale - 1) * e;
  const w = size.w * z, h = size.h * z;
  const x = Math.min(Math.max(p.focus_x * w - size.w / 2, 0), w - size.w);
  const y = Math.min(Math.max(p.focus_y * h - size.h / 2, 0), h - size.h);
  ctx.drawImage(img, -x, -y, w, h);
  ctx.globalAlpha = 0.35 * e;
  const z2 = 1 + (p.scale - 1) * e * 0.8;
  ctx.drawImage(img, -(p.focus_x * size.w * z2 - size.w / 2), -(p.focus_y * size.h * z2 - size.h / 2), size.w * z2, size.h * z2);
  ctx.globalAlpha = 1;
}
