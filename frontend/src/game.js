// PLAYABLE_TERRARIA_SANDBOX — shared 60fps 2D pixel-art sandbox engine.
// One state object renders BOTH viewports from a single offscreen buffer,
// so a straddled window lines up pixel-for-pixel with zero tearing.

export const TILE = 16;
export const COLS = 30;
export const ROWS = 18;
export const WORLD_W = COLS * TILE; // 480
export const WORLD_H = ROWS * TILE; // 288

export const T_AIR = 0;
export const T_DIRT = 1;
export const T_STONE = 2;
export const T_WOOD = 3;
export const T_LEAF = 4;
export const T_TORCH = 5;

const TILE_COLORS = {
  [T_DIRT]: '#8a5a32',
  [T_STONE]: '#6f7480',
  [T_WOOD]: '#6b4a26',
  [T_LEAF]: '#2f9e4f',
  [T_TORCH]: '#ffcf4d',
};
const TILE_NAMES = {
  [T_DIRT]: 'Dirt', [T_STONE]: 'Stone', [T_WOOD]: 'Wood',
  [T_LEAF]: 'Leaf', [T_TORCH]: 'Torch',
};
export function tileName(t) { return TILE_NAMES[t] || 'Air'; }

function hillY(c) {
  return ROWS - 6 + Math.round(2 * Math.sin(c / 5.2) + Math.cos(c / 8.7));
}

export function createGame() {
  const tiles = new Uint8Array(COLS * ROWS);
  const at = (c, r) => (c < 0 || r < 0 || c >= COLS || r >= ROWS ? T_STONE : tiles[r * COLS + c]);
  const set = (c, r, t) => { if (c >= 0 && r >= 0 && c < COLS && r < ROWS) tiles[r * COLS + c] = t; };
  for (let c = 0; c < COLS; c++) {
    const s = hillY(c);
    for (let r = s; r < ROWS; r++) set(c, r, r > s + 2 ? T_STONE : T_DIRT);
  }
  // Trees (trunk + leaf blob), never on spawn columns 4..7.
  for (const tc of [11, 19, 26]) {
    const s = hillY(tc);
    for (let r = s - 4; r < s; r++) set(tc, r, T_WOOD);
    for (let dc = -2; dc <= 2; dc++)
      for (let dr = -6; dr <= -3; dr++) {
        if (Math.abs(dc) + Math.abs(dr + 4) <= 4) set(tc + dc, s + dr, T_LEAF);
      }
  }
  // Torches near spawn.
  set(5, hillY(5) - 1, T_TORCH);
  set(16, hillY(16) - 1, T_TORCH);
  const spawnC = 5;
  return {
    tiles, at, set,
    player: { x: spawnC * TILE + 2, y: (hillY(spawnC) - 2) * TILE, w: 12, h: 22, vx: 0, vy: 0, onGround: false, facing: 1, swing: 0 },
    slime: { x: 20 * TILE, y: 4 * TILE, w: 26, h: 18, vx: 0, vy: 0, hp: 3, cool: 0, dead: false },
    eye: { x: 15 * TILE, y: 2 * TILE, t: 0 },
    torches: [],
    inventory: { [T_DIRT]: 9, [T_STONE]: 4, [T_WOOD]: 0, [T_LEAF]: 0, [T_TORCH]: 2 },
    selected: T_DIRT,
    dayT: 0.3,
    kills: 0,
  };
}

function solidAt(g, px, py) {
  const c = Math.floor(px / TILE), r = Math.floor(py / TILE);
  if (c < 0 || c >= COLS) return true;
  if (r < 0 || r >= ROWS) return r >= ROWS;
  const t = g.tiles[r * COLS + c];
  return t !== T_AIR;
}

function moveBody(g, b, dt) {
  // Horizontal
  b.x += b.vx * dt;
  if (b.vx > 0 && (solidAt(g, b.x + b.w, b.y + 2) || solidAt(g, b.x + b.w, b.y + b.h - 2))) {
    b.x = Math.floor((b.x + b.w) / TILE) * TILE - b.w - 0.01; b.vx = 0;
  } else if (b.vx < 0 && (solidAt(g, b.x, b.y + 2) || solidAt(g, b.x, b.y + b.h - 2))) {
    b.x = (Math.floor(b.x / TILE) + 1) * TILE + 0.01; b.vx = 0;
  }
  // Vertical
  b.y += b.vy * dt;
  b.onGround = false;
  if (b.vy >= 0 && (solidAt(g, b.x + 2, b.y + b.h) || solidAt(g, b.x + b.w - 2, b.y + b.h))) {
    b.y = Math.floor((b.y + b.h) / TILE) * TILE - b.h - 0.01; b.vy = 0; b.onGround = true;
  } else if (b.vy < 0 && (solidAt(g, b.x + 2, b.y) || solidAt(g, b.x + b.w - 2, b.y))) {
    b.y = (Math.floor(b.y / TILE) + 1) * TILE + 0.01; b.vy = 0;
  }
}

export function stepGame(g, keys, dt = 1) {
  const p = g.player;
  const SPEED = 2.2;
  if (keys.left) { p.vx = -SPEED; p.facing = -1; }
  else if (keys.right) { p.vx = SPEED; p.facing = 1; }
  else p.vx *= 0.6;
  p.vy = Math.min(p.vy + 0.5 * dt, 12);
  if (keys.jump && p.onGround) { p.vy = -8.6; p.onGround = false; }
  moveBody(g, p, dt);
  if (p.swing > 0) p.swing -= dt;
  // King Slime: hops toward the player.
  const s = g.slime;
  if (!s.dead) {
    s.vy = Math.min(s.vy + 0.5 * dt, 12);
    if (s.cool > 0) s.cool -= dt;
    if (s.onGround && s.cool <= 0) {
      s.vy = -8;
      s.vx = Math.sign(p.x - s.x) * 1.6 || 1.2;
      s.cool = 55;
    }
    moveBody(g, s, dt);
  }
  // Eye of Cthulhu: hovers above the player on a sine.
  g.eye.t += 0.03 * dt;
  g.eye.x += ((p.x - 40) - g.eye.x) * 0.02 * dt;
  g.eye.y = 3 * TILE + 22 * Math.sin(g.eye.t);
  g.dayT = (g.dayT + dt / (60 * 120)) % 1; // full day/night in 2 min
}

export function mineAt(g, wx, wy) {
  const c = Math.floor(wx / TILE), r = Math.floor(wy / TILE);
  if (c < 0 || r < 0 || c >= COLS || r >= ROWS) return null;
  const t = g.tiles[r * COLS + c];
  if (t === T_AIR) return null;
  g.tiles[r * COLS + c] = T_AIR;
  g.inventory[t] = (g.inventory[t] || 0) + 1;
  g.player.swing = 12;
  return t;
}

export function placeAt(g, wx, wy) {
  const c = Math.floor(wx / TILE), r = Math.floor(wy / TILE);
  if (c < 0 || r < 0 || c >= COLS || r >= ROWS) return false;
  if (g.tiles[r * COLS + c] !== T_AIR) return false;
  const t = g.selected;
  if ((g.inventory[t] || 0) <= 0) return false;
  // Never seal the player inside their own body.
  const p = g.player;
  const overlap = wx + 1 > p.x && wx - 1 < p.x + p.w && wy + 1 > p.y && wy - 1 < p.y + p.h;
  if (overlap) return false;
  g.tiles[r * COLS + c] = t;
  g.inventory[t]--;
  return true;
}

export function hitSlime(g, wx, wy) {
  const s = g.slime;
  if (s.dead) return false;
  if (wx >= s.x - 4 && wx <= s.x + s.w + 4 && wy >= s.y - 6 && wy <= s.y + s.h + 4) {
    s.hp--;
    g.player.swing = 12;
    if (s.hp <= 0) { s.dead = true; g.kills++; g.inventory[T_WOOD] += 5; }
    return true;
  }
  return false;
}

// --- Rendering (world-space 480x288) ---------------------------------------

function skyColor(dayT) {
  // dayT 0..1: 0.25 = noon. Blend day blue -> dusk orange -> night navy.
  const day = [125, 178, 232], dusk = [232, 140, 80], night = [8, 12, 26];
  const sun = Math.sin(dayT * Math.PI * 2 - Math.PI / 2) * 0.5 + 0.5; // 1 at noon
  const c = [0, 1, 2].map((i) => {
    if (sun > 0.6) return Math.round(night[i] + (day[i] - night[i]) * ((sun - 0.6) / 0.4));
    return Math.round(night[i] + (dusk[i] - night[i]) * (sun / 0.6));
  });
  return `rgb(${c[0]},${c[1]},${c[2]})`;
}

export function renderGame(ctx, g) {
  ctx.fillStyle = skyColor(g.dayT);
  ctx.fillRect(0, 0, WORLD_W, WORLD_H);
  // Sun / moon arc
  const a = g.dayT * Math.PI * 2 - Math.PI / 2;
  const sx = WORLD_W / 2 + (WORLD_W / 2 - 20) * Math.cos(a);
  const sy = WORLD_H - 30 + (WORLD_H - 60) * Math.sin(a);
  ctx.fillStyle = '#ffd94d';
  ctx.fillRect(Math.round(sx) - 7, Math.round(sy) - 7, 14, 14);
  // Tiles
  for (let r = 0; r < ROWS; r++) {
    for (let c = 0; c < COLS; c++) {
      const t = g.tiles[r * COLS + c];
      if (t === T_AIR) continue;
      const x = c * TILE, y = r * TILE;
      ctx.fillStyle = TILE_COLORS[t];
      ctx.fillRect(x, y, TILE, TILE);
      ctx.fillStyle = 'rgba(0,0,0,0.25)';
      ctx.fillRect(x, y + TILE - 3, TILE, 3);
      if (t === T_TORCH) {
        ctx.fillStyle = '#7a4a1a';
        ctx.fillRect(x + 6, y + 6, 4, 10);
        const night = 1 - (Math.sin(g.dayT * Math.PI * 2 - Math.PI / 2) * 0.5 + 0.5);
        ctx.fillStyle = `rgba(255,190,60,${0.25 + 0.55 * night})`;
        ctx.fillRect(x - 4, y - 6, 24, 24);
        ctx.fillStyle = '#ffe27a';
        ctx.fillRect(x + 5, y + 1, 6, 6);
      }
    }
  }
  const p = g.player;
  // Shadow
  ctx.fillStyle = 'rgba(0,0,0,0.3)';
  ctx.fillRect(Math.round(p.x) - 1, Math.round(p.y + p.h) - 1, p.w + 2, 3);
  // Player (Terraria-style: skin, hair, eyes, swing arm)
  const px = Math.round(p.x), py = Math.round(p.y);
  ctx.fillStyle = '#e8b07e';
  ctx.fillRect(px, py + 4, p.w, 14); // skin
  ctx.fillStyle = '#4a2f1a';
  ctx.fillRect(px, py, p.w, 6); // hair
  ctx.fillStyle = '#101018';
  ctx.fillRect(px + (p.facing > 0 ? 6 : 2), py + 9, 3, 3); // eye
  ctx.fillStyle = '#3f6fd1';
  ctx.fillRect(px, py + 14, p.w, 8); // shirt
  ctx.fillStyle = '#5a3d22';
  ctx.fillRect(px + 1, py + 20, 4, 2);
  ctx.fillRect(px + 7, py + 20, 4, 2); // boots
  if (p.swing > 0) { // pickaxe arc
    ctx.fillStyle = '#8a6a3f';
    const sw = p.swing;
    const hx = px + (p.facing > 0 ? p.w : 0) + p.facing * (14 - sw);
    ctx.fillRect(hx - 1, py - 2, 3, 16);
    ctx.fillStyle = '#c9ced6';
    ctx.fillRect(hx - 5, py - 4, 11, 4);
  }
  // King Slime (jumping blob + crown)
  const s = g.slime;
  if (!s.dead) {
    const slx = Math.round(s.x), sly = Math.round(s.y);
    ctx.fillStyle = 'rgba(0,0,0,0.3)';
    ctx.fillRect(slx - 1, sly + s.h - 1, s.w + 2, 3);
    ctx.fillStyle = 'rgba(70,160,255,0.85)';
    ctx.fillRect(slx, sly, s.w, s.h);
    ctx.fillStyle = 'rgba(200,235,255,0.9)';
    ctx.fillRect(slx + 4, sly + 3, s.w - 8, 5);
    ctx.fillStyle = '#101018';
    ctx.fillRect(slx + 6, sly + 9, 4, 4);
    ctx.fillRect(slx + s.w - 10, sly + 9, 4, 4);
    ctx.fillStyle = '#ffd94d'; // crown
    ctx.fillRect(slx + 6, sly - 7, s.w - 12, 7);
    ctx.fillRect(slx + 6, sly - 10, 4, 3);
    ctx.fillRect(slx + 11, sly - 12, 4, 5);
    ctx.fillRect(slx + s.w - 10, sly - 10, 4, 3);
  }
  // Eye of Cthulhu (hovering eyeball + teeth)
  const ex = Math.round(g.eye.x), ey = Math.round(g.eye.y);
  ctx.fillStyle = 'rgba(255,255,255,0.95)';
  ctx.fillRect(ex, ey, 30, 20);
  ctx.fillStyle = '#c22';
  ctx.fillRect(ex + 10, ey + 5, 10, 10);
  ctx.fillStyle = '#101018';
  ctx.fillRect(ex + 13, ey + 8, 4, 4);
  ctx.fillStyle = '#fff';
  for (let i = 0; i < 5; i++) ctx.fillRect(ex + 2 + i * 6, ey + 18, 3, 4);
  // Inventory bar overlay
  const bar = [T_DIRT, T_STONE, T_WOOD, T_TORCH, T_LEAF];
  ctx.fillStyle = 'rgba(5,7,10,0.82)';
  ctx.fillRect(8, WORLD_H - 26, bar.length * 30 + 8, 22);
  bar.forEach((t, i) => {
    const bx = 12 + i * 30, by = WORLD_H - 23;
    ctx.fillStyle = TILE_COLORS[t];
    ctx.fillRect(bx, by, 15, 15);
    if (t === g.selected) {
      ctx.strokeStyle = '#56d678';
      ctx.lineWidth = 2;
      ctx.strokeRect(bx - 2, by - 2, 19, 19);
    }
    ctx.fillStyle = '#fff';
    ctx.font = '9px monospace';
    ctx.fillText(String(g.inventory[t] || 0), bx + 17, by + 12);
  });
}
