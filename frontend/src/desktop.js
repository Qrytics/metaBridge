// Procedural desktop wallpapers for projection mode: the game renders with a
// transparent sky so the tiles/player look projected onto each OS desktop.

export function wallpaperStops(flavor) {
  if (flavor === 'mac') {
    return {
      top: '#1b1e26', mid: '#101218', bottom: '#07080b',
      grid: 'rgba(255,255,255,0.045)', accent: '#ffb224', glow: 'rgba(255,178,36,0.10)',
    };
  }
  // win
  return {
    top: '#0e2238', mid: '#0a1626', bottom: '#05090f',
    grid: 'rgba(120,190,255,0.06)', accent: '#4cc3ff', glow: 'rgba(76,195,255,0.12)',
  };
}

export function paintWallpaper(ctx, w, h, flavor) {
  const s = wallpaperStops(flavor);
  const grad = ctx.createLinearGradient(0, 0, 0, h);
  grad.addColorStop(0, s.top);
  grad.addColorStop(0.55, s.mid);
  grad.addColorStop(1, s.bottom);
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, w, h);
  // Faint perspective grid rising from the bottom (the "desktop plane").
  ctx.strokeStyle = s.grid;
  ctx.lineWidth = 1;
  ctx.beginPath();
  for (let x = 0; x <= w; x += 48) {
    ctx.moveTo(x, h);
    ctx.lineTo(w / 2 + (x - w / 2) * 0.25, h * 0.45);
  }
  for (let i = 0; i < 7; i++) {
    const y = h - (i * i * h) / 120;
    ctx.moveTo(0, y);
    ctx.lineTo(w, y);
  }
  ctx.stroke();
  // Horizon accent + soft glow band where the world sits.
  ctx.fillStyle = s.glow;
  ctx.fillRect(0, h * 0.42, w, h * 0.16);
  ctx.fillStyle = s.accent;
  ctx.fillRect(0, Math.round(h * 0.5), w, 2);
}
