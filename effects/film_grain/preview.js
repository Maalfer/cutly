export function render(ctx, img, p, progress, size) {
  ctx.drawImage(img, 0, 0, size.w, size.h);
  ctx.globalAlpha = p.strength / 200;
  for (let i = 0; i < 400; i++) { ctx.fillStyle = Math.random() > 0.5 ? '#fff' : '#000'; ctx.fillRect(Math.random() * size.w, Math.random() * size.h, 2, 2); }
  ctx.globalAlpha = 1;
}
