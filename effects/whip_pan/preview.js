export function render(ctx, img, p, progress, size) {
  const e = Math.sin(Math.PI * progress), d = p.distance;
  const z = 1 + 2 * d * e, w = size.w * z, h = size.h * z;
  const sx = { left: -1, right: 1 }[p.direction] || 0, sy = { up: -1, down: 1 }[p.direction] || 0;
  const x = (w - size.w) / 2 + sx * d * size.w * e, y = (h - size.h) / 2 + sy * d * size.h * e;
  ctx.drawImage(img, -x, -y, w, h);
}
