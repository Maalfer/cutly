export function render(ctx, img, p, progress, size) {
  ctx.drawImage(img, 0, 0, size.w, size.h);
  ctx.fillStyle = p.color === 'white' ? '#fff' : '#000';
  ctx.globalAlpha = p.strength * Math.exp(-6 * progress);
  ctx.fillRect(0, 0, size.w, size.h);
  ctx.globalAlpha = 1;
}
