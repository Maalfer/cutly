export function render(ctx, img, p, progress, size) {
  const z = 1 + (p.scale - 1) * progress, w = size.w * z, h = size.h * z;
  const x = Math.min(Math.max(p.focus_x * w - size.w / 2, 0), w - size.w);
  const y = Math.min(Math.max(p.focus_y * h - size.h / 2, 0), h - size.h);
  ctx.drawImage(img, -x, -y, w, h);
}
