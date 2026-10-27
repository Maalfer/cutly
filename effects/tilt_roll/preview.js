export function render(ctx, img, p, progress, size) {
  const e = Math.sin(Math.PI * progress), a = p.angle * Math.PI / 180 * e;
  const z = Math.cos(a) + Math.max(size.h / size.w, size.w / size.h) * Math.abs(Math.sin(a));
  ctx.save(); ctx.translate(size.w / 2, size.h / 2); ctx.rotate(a); ctx.scale(z, z);
  ctx.drawImage(img, -size.w / 2, -size.h / 2, size.w, size.h); ctx.restore();
}
