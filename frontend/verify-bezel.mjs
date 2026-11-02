// Headless Playwright Chromium verification (Stage 2):
// drags the live game window's title bar across the center bezel and asserts
// STRADDLE_OFFSET_PX updates, both screens render non-blank, zero console errors.
import { chromium } from '@playwright/test';

const URL = process.env.PORTAL_URL || 'http://127.0.0.1:4173/?sim-dual=1';
const errors = [];

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } });
page.on('console', (m) => { if (m.type() === 'error') errors.push(`console: ${m.text()}`); });
page.on('pageerror', (e) => errors.push(`page: ${e.message}`));

await page.goto(URL, { waitUntil: 'networkidle' });
await page.waitForFunction(() => window.__metaBridge && document.getElementById('m-straddle'));

const start = await page.evaluate(() => ({ x: window.__metaBridge.winX, s: document.getElementById('m-straddle').textContent }));
console.log('start', JSON.stringify(start));
if (start.s !== '0') throw new Error(`expected initial STRADDLE_OFFSET_PX=0, got ${start.s}`);

const boxL = await page.locator('#cv-win').boundingBox();
const boxR = await page.locator('#cv-mac').boundingBox();
const uxL = boxL.width / 960, uyL = boxL.height / 600;
const uxR = boxR.width / 960, uyR = boxR.height / 600;
// Title-bar grab point: window starts at winX=240, winY=140 -> center (480, 154).
await page.mouse.move(boxL.x + 480 * uxL, boxL.y + 154 * uyL);
await page.mouse.down();
const steps = 24;
for (let i = 1; i <= steps; i++) {
  const gx = 480 + ((1100 - 480) * i) / steps; // global desktop x
  if (gx < 960) await page.mouse.move(boxL.x + gx * uxL, boxL.y + 154 * uyL);
  else await page.mouse.move(boxR.x + (gx - 960) * uxR, boxR.y + 154 * uyR);
  await page.waitForTimeout(16);
}
await page.mouse.up();
await page.waitForTimeout(400);

const after = await page.evaluate(() => ({
  x: window.__metaBridge.winX,
  s: document.getElementById('m-straddle').textContent,
  ownerMac: document.getElementById('owner-mac').classList.contains('active'),
  geom: document.getElementById('mac-geom').textContent,
}));
console.log('after-drag', JSON.stringify(after));
if (after.s === '0') throw new Error('STRADDLE_OFFSET_PX did not update after bezel drag');
if (!after.ownerMac) throw new Error('CURSOR_OWNER did not hand off to MAC');
if (!after.geom.includes('mac_win_x=')) throw new Error('right viewport shows no straddle geometry');

// Both canvases must render non-blank (shared-buffer straddle, zero tearing).
const coverage = await page.evaluate(() => {
  const frac = (id) => {
    const c = document.getElementById(id);
    const d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data;
    let lit = 0;
    for (let i = 0; i < d.length; i += 40) if (d[i] + d[i + 1] + d[i + 2] > 24) lit++;
    return lit / (d.length / 40);
  };
  return { win: frac('cv-win'), mac: frac('cv-mac') };
});
console.log('coverage', JSON.stringify(coverage));
if (coverage.win < 0.005) throw new Error('left canvas blank');
if (coverage.mac < 0.02) throw new Error('right canvas blank after straddle');

// Reverse-input playability: hold D, the shared player must move.
const px0 = await page.evaluate(() => window.__metaBridge.playerX);
await page.keyboard.down('d');
await page.waitForTimeout(500);
await page.keyboard.up('d');
const px1 = await page.evaluate(() => window.__metaBridge.playerX);
console.log('player', px0, '->', px1);
if (!(px1 > px0)) throw new Error('player did not move with D key');

await browser.close();
if (errors.length) throw new Error(`console/page errors:\n${errors.join('\n')}`);
console.log('VERIFY PASS: bezel drag, dual render, reverse input, zero console errors');
