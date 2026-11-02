import { describe, expect, it } from 'vitest';
import { dragHandoff, springStep, straddleView, viewportToFrame } from '../src/bezel.js';
import { createGame, hitSlime, mineAt, placeAt, stepGame } from '../src/game.js';

const W = 960;

describe('cross-bezel drag handoff', () => {
  it('keeps the drag alive while ownership flips WIN -> MAC', () => {
    const sweep = [100, 800, 957, 958, 1000, 1400].map((cx) => dragHandoff(cx, W, true));
    expect(sweep.every((s) => s.dragging)).toBe(true);
    expect(sweep[0].owner).toBe('WIN');
    expect(sweep[0].crossed).toBe(false);
    expect(sweep[2].owner).toBe('WIN');
    expect(sweep[3].owner).toBe('MAC');
    expect(sweep[3].crossed).toBe(true);
    expect(sweep[5].crossed).toBe(true);
    expect(dragHandoff(1000, W, false)).toEqual({ owner: 'MAC', dragging: false, crossed: false });
  });

  it('drags back MAC -> WIN', () => {
    expect(dragHandoff(1100, W, true).owner).toBe('MAC');
    expect(dragHandoff(400, W, true).owner).toBe('WIN');
  });

  it('drop point composes with straddle math (50% straddle)', () => {
    // WIN_W=480 at winX=720 -> right half renders on MAC.
    const v = straddleView(720, 100, 480, 320, W);
    expect(v.straddling).toBe(true);
    expect(v.macWinX).toBe(-240);
    expect(v.straddleOffsetPx).toBe(240);
  });
});

describe('SAM rip coordinate mapping', () => {
  it('MAC-local click resolves into shared-frame coords', () => {
    const v = straddleView(720, 100, 480, 320, W);
    expect(viewportToFrame(50, 150, v.macWinX, v.macWinY)).toEqual([290, 50]);
    const [nx, ny] = [290 / 480, 50 / 288];
    expect(nx).toBeGreaterThanOrEqual(0);
    expect(nx).toBeLessThanOrEqual(1);
    expect(ny).toBeGreaterThanOrEqual(0);
    expect(ny).toBeLessThanOrEqual(1);
  });
});

describe('voice glide spring', () => {
  it('converges and settles exactly on target', () => {
    let [x, v] = [200, 0];
    for (let i = 0; i < 600; i++) [x, v] = springStep(x, v, 1080);
    expect(x).toBe(1080);
    expect(v).toBe(0);
  });

  it('moves toward target on the first step', () => {
    const [x] = springStep(200, 0, 1080);
    expect(x).toBeGreaterThan(200);
  });
});

describe('playable sandbox', () => {
  it('player falls, walks right with D, and jumps', () => {
    const g = createGame();
    for (let i = 0; i < 200; i++) stepGame(g, {}, 1);
    expect(g.player.onGround).toBe(true);
    const x0 = g.player.x;
    for (let i = 0; i < 30; i++) stepGame(g, { right: true }, 1);
    expect(g.player.x).toBeGreaterThan(x0);
    const y0 = g.player.y;
    for (let i = 0; i < 10; i++) stepGame(g, { jump: true }, 1);
    expect(g.player.y).toBeLessThan(y0);
  });

  it('mines and places tiles through the shared buffer', () => {
    const g = createGame();
    // Find a solid tile near spawn to mine: scan column 5.
    let mined = null;
    for (let y = 0; y < 288 && mined === null; y += 16) mined = mineAt(g, 5 * 16 + 8, y);
    expect(mined).not.toBe(null);
    g.selected = mined;
    // Place back into a known air cell above the surface.
    expect(placeAt(g, 2 * 16 + 8, 2 * 16 + 8)).toBe(true);
  });

  it('sword kills the slime in 3 hits', () => {
    const g = createGame();
    const { x, y } = g.slime;
    expect(hitSlime(g, x + 10, y + 5)).toBe(true);
    expect(hitSlime(g, x + 10, y + 5)).toBe(true);
    expect(hitSlime(g, x + 10, y + 5)).toBe(true);
    expect(g.slime.dead).toBe(true);
    expect(g.kills).toBe(1);
  });
});
