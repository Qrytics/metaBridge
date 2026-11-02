import { describe, expect, it } from 'vitest';
import { createGame, renderGame, WORLD_H, WORLD_W } from '../src/game.js';
import { paintWallpaper, wallpaperStops } from '../src/desktop.js';

function stubCtx(calls) {
  return {
    set fillStyle(v) { calls.push(['fillStyle', v]); },
    set strokeStyle(_) {},
    set lineWidth(_) {},
    set font(_) {},
    fillRect(...a) { calls.push(['fillRect', ...a]); },
    fillText() {},
    strokeRect() {},
    beginPath() {},
    moveTo() {},
    lineTo() {},
    stroke() {},
    createLinearGradient() { return { addColorStop() {} }; },
  };
}

describe('desktop projection', () => {
  it('paints a full-view sky rect by default', () => {
    const calls = [];
    renderGame(stubCtx(calls), createGame(), 0, WORLD_W, 0);
    expect(calls).toContainEqual(['fillRect', 0, 0, WORLD_W, WORLD_H]);
  });

  it('sky:false skips the sky band but still paints tiles', () => {
    const calls = [];
    renderGame(stubCtx(calls), createGame(), 0, WORLD_W, 0, { sky: false });
    expect(calls).not.toContainEqual(['fillRect', 0, 0, WORLD_W, WORLD_H]);
    const tiles = calls.filter(([m, , , w]) => m === 'fillRect' && w === 16);
    expect(tiles.length).toBeGreaterThan(50);
  });

  it('wallpapers are flavor-distinct and full-bleed', () => {
    const win = wallpaperStops('win');
    const mac = wallpaperStops('mac');
    expect(win.top).not.toBe(mac.top);
    for (const [flavor, w, h] of [['win', 960, 600], ['mac', 960, 600]]) {
      const calls = [];
      paintWallpaper(stubCtx(calls), w, h, flavor);
      expect(calls).toContainEqual(['fillRect', 0, 0, w, h]);
    }
  });
});
