import { afterEach, describe, expect, it } from 'vitest';
import { bridgeBase } from '../src/membrane.js';

describe('membrane bridgeBase', () => {
  afterEach(() => {
    delete globalThis.window;
  });

  it('falls back to localhost without a browser', () => {
    expect(bridgeBase()).toBe('http://localhost:8000');
  });

  it('follows the serving host (sim-dual / LAN)', () => {
    globalThis.window = { location: { hostname: '192.168.1.20' } };
    expect(bridgeBase()).toBe('http://192.168.1.20:8000');
  });
});
