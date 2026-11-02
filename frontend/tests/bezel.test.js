import { describe, expect, it } from 'vitest';
import {
  clampCursor,
  cursorOwner,
  macToHostGameCoords,
  straddleView,
} from '../src/bezel.js';

describe('bezel straddle math', () => {
  it('no straddle when fully left', () => {
    const v = straddleView(100, 50, 800, 600, 1920);
    expect(v.straddling).toBe(false);
    expect(v.rightVisibleW).toBe(0);
    expect(v.straddleOffsetPx).toBe(0);
  });

  it('mac_win_x = win_x - W_left on crossing', () => {
    const v = straddleView(1720, 100, 400, 300, 1920);
    expect(v.straddling).toBe(true);
    expect(v.macWinX).toBe(-200);
    expect(v.macWinY).toBe(100);
    expect(v.leftVisibleW).toBe(200);
    expect(v.rightVisibleW).toBe(200);
    expect(v.straddleOffsetPx).toBe(200);
  });

  it('cursor hands off at W_left - 2', () => {
    expect(cursorOwner(1918, 1920)).toBe('MAC');
    expect(cursorOwner(1917, 1920)).toBe('WIN');
  });

  it('reverse game input maps and clamps', () => {
    expect(macToHostGameCoords(50, 150, -200, 100, 400, 300)).toEqual([250, 50]);
    expect(macToHostGameCoords(-5000, 9999, -200, 100, 400, 300)).toEqual([0, 299]);
  });

  it('clamp cursor', () => {
    expect(clampCursor(9999, -5, 1920, 1080)).toEqual([1919, 0]);
  });
});
