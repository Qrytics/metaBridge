// Headless check for CAST mode (?cast=1): fullscreen view-only spectator.
import { chromium } from '@playwright/test';

const URL = process.env.CAST_URL || 'http://localhost:4173/?sim-dual=1&cast=1';
const errors = [];

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 390, height: 844 } }); // phone
page.on('console', (m) => { if (m.type() === 'error') errors.push(`console: ${m.text()}`); });
page.on('pageerror', (e) => errors.push(`page: ${e.message()}`));

await page.goto(URL, { waitUntil: 'networkidle' });
await page.waitForFunction(() => window.__metaBridge && window.__metaBridge.mode === 'span');
await page.waitForTimeout(600);
const state = await page.evaluate(() => ({
  cast: document.body.classList.contains('cast'),
  projecting: window.__metaBridge.projecting,
  macHidden: getComputedStyle(document.getElementById('vp-mac')).display === 'none',
}));
console.log('cast state', JSON.stringify(state));
if (!state.cast || !state.projecting || !state.macHidden) throw new Error('cast layout wrong');
const lit = await page.evaluate(() => {
  const d = document.getElementById('cv-win').getContext('2d').getImageData(0, 0, 960, 600).data;
  let n = 0;
  for (let i = 0; i < d.length; i += 80) if (d[i] + d[i + 1] + d[i + 2] > 24) n++;
  return n / (d.length / 80);
});
console.log('cast coverage', lit);
if (lit < 0.05) throw new Error('cast canvas blank');

await browser.close();
if (errors.length) throw new Error(`console/page errors:\n${errors.join('\n')}`);
console.log('VERIFY PASS: cast spectator, zero console errors');
