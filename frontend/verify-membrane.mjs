// Headless Playwright Chromium verification (Stage 3 membrane):
// file-icon bezel transfer + modal, SAM rip card, voice glide — live bridge.
import { chromium } from '@playwright/test';

const URL = process.env.PORTAL_URL || 'http://localhost:4173/?sim-dual=1';
const errors = [];

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } });
page.on('console', (m) => { if (m.type() === 'error') errors.push(`console: ${m.text()}`); });
page.on('pageerror', (e) => errors.push(`page: ${e.message}`));

await page.goto(URL, { waitUntil: 'networkidle' });
await page.waitForFunction(() => window.__metaBridge && window.__metaBridge.game);

// 1. Drag deploy_server.ps1 across the bezel -> modal + converted icon.
const icon = page.locator('.fileicon.ps1').first();
await icon.waitFor();
const ib = await icon.boundingBox();
await page.mouse.move(ib.x + ib.width / 2, ib.y + ib.height / 2);
await page.mouse.down();
const macBox = await page.locator('#cv-mac').boundingBox();
const steps = 16;
for (let i = 1; i <= steps; i++) {
  await page.mouse.move(
    (ib.x + ib.width / 2) + ((macBox.x + macBox.width / 2) - (ib.x + ib.width / 2)) * (i / steps),
    ib.y,
  );
  await page.waitForTimeout(16);
}
await page.mouse.up();
await page.waitForFunction(() => !document.getElementById('modal').hidden, null, { timeout: 8000 });
const afterName = await page.locator('#diff-b-name').textContent();
console.log('transfer modal AFTER:', afterName);
if (!afterName.includes('.sh')) throw new Error('no transpiled .sh in modal');
const notes = await page.locator('#modal-notes').textContent();
console.log('critic:', notes);
if (!notes.includes('critic=PASS')) throw new Error('critic did not PASS');
await page.locator('#modal-close').click();
await page.locator('#files-mac .fileicon.sh').first().waitFor();
console.log('mac icon: converted .sh present');

// 2. SAM mode + Alt+click in the live game -> sprite card.
await page.locator('#btn-sam-mode').click();
const win = await page.evaluate(() => ({ x: window.__metaBridge.winX, y: window.__metaBridge.winY }));
const boxL = await page.locator('#cv-win').boundingBox();
await page.keyboard.down('Alt');
await page.mouse.click(boxL.x + ((win.x + 240) / 960) * boxL.width, boxL.y + ((win.y + 150) / 600) * boxL.height);
await page.keyboard.up('Alt');
await page.locator('.spritecard').first().waitFor({ timeout: 8000 });
console.log('sam: sprite card minted');
await page.locator('#btn-sam-mode').click(); // disarm

// 3. Voice quick command glides the window to 50% straddle and settles.
await page.locator('#btn-v50').click();
await page.waitForFunction(() => window.__metaBridge.winX === 720, null, { timeout: 8000 });
await page.waitForTimeout(300);
const s = await page.evaluate(() => document.getElementById('m-straddle').textContent);
console.log('glide straddle:', s);
if (s !== '240') throw new Error(`expected STRADDLE_OFFSET_PX=240, got ${s}`);

await browser.close();
if (errors.length) throw new Error(`console/page errors:\n${errors.join('\n')}`);
console.log('VERIFY PASS: membrane transfer, SAM rip, voice glide, zero console errors');
