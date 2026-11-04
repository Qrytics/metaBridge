// End-to-end fault-injection harness for the LIVE_AGENT_STREAM path.
//
//   cd frontend && npm run build && node verify-live-agent.mjs
//
// Spawns its own bridge (:8000) + static portal (:4199) + a controllable fake
// agent, drives a real browser to click "Live agent", then injects every known
// failure and asserts BOTH ends (bridge /debug/stream + portal stream stats)
// noticed. Exits non-zero on any miss, any console/page error, or a stream
// that did not recover. Artifacts land in $METABRIDGE_DEBUG_DIR (default tmp).
import { chromium } from '@playwright/test';
import { spawn } from 'node:child_process';
import { mkdtempSync, existsSync, mkdirSync, readFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';

const ROOT = resolve(import.meta.dirname, '..');
const PY = existsSync(join(ROOT, '.venv/bin/python')) ? join(ROOT, '.venv/bin/python')
  : existsSync(join(ROOT, '.venv/Scripts/python.exe')) ? join(ROOT, '.venv/Scripts/python.exe') : 'python3';
const BRIDGE = 'http://127.0.0.1:8000';
const PORTAL = 'http://127.0.0.1:4199';
const DBG = process.env.METABRIDGE_DEBUG_DIR || mkdtempSync(join(tmpdir(), 'mb-e2e-'));
mkdirSync(DBG, { recursive: true });

const failures = [];
const log = (...a) => console.log(...a);
const check = (name, ok, detail = '') => {
  log(`${ok ? '  PASS' : '  FAIL'}  ${name}${detail ? '  — ' + detail : ''}`);
  if (!ok) failures.push(`${name}${detail ? ': ' + detail : ''}`);
};
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const procs = [];
function spawnProc(cmd, args, opts = {}) {
  const p = spawn(cmd, args, { cwd: ROOT, env: { ...process.env, METABRIDGE_DEBUG_DIR: DBG, ENV: 'dev', PYTHONUNBUFFERED: '1' }, stdio: ['ignore', 'pipe', 'pipe'], ...opts });
  p.out = '';
  p.stdout.on('data', (d) => { p.out += d; });
  p.stderr.on('data', (d) => { p.out += d; });
  procs.push(p);
  return p;
}
const kill = (p) => new Promise((r) => { if (!p || p.exitCode !== null) return r(); p.once('exit', r); p.kill('SIGTERM'); setTimeout(() => { try { p.kill('SIGKILL'); } catch {} r(); }, 1500); });
async function waitFor(fn, ms, what) {
  const t0 = Date.now();
  while (Date.now() - t0 < ms) { try { const v = await fn(); if (v) return v; } catch {} await sleep(100); }
  throw new Error(`timeout waiting for ${what}`);
}
const j = async (path) => (await fetch(BRIDGE + path)).json();
const startBridge = () => spawnProc(PY, ['-m', 'uvicorn', 'backend.main:app', '--host', '127.0.0.1', '--port', '8000', '--log-level', 'warning']);
const startAgent = (...args) => spawnProc(PY, ['-m', 'agent.sim_publisher', '--url', BRIDGE + '/viewport/frame', ...args.map(String)]);
const portalStream = (page) => page.evaluate(() => window.__metaBridge.stream);
const ready = () => waitFor(async () => (await fetch(BRIDGE + '/health')).ok, 15000, 'bridge /health');

let browser;
const pageErrors = [];
try {
  if (!existsSync(join(ROOT, 'frontend/dist/index.html'))) throw new Error('frontend/dist missing — run npm run build first');
  try { await fetch(BRIDGE + '/health'); throw new Error('port 8000 already in use — stop your running bridge first (this harness starts its own)'); }
  catch (e) { if (String(e.message).includes('already in use')) throw e; }

  let bridge = startBridge();
  spawnProc(PY, ['-m', 'http.server', '4199', '--bind', '127.0.0.1', '--directory', join(ROOT, 'frontend/dist')]);
  await ready();
  await waitFor(async () => (await fetch(PORTAL)).ok, 10000, 'portal');

  browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1600, height: 900 } });
  page.on('pageerror', (e) => pageErrors.push('pageerror: ' + e.message));
  page.on('console', (m) => { if (m.type() === 'error') pageErrors.push('console: ' + m.text()); });
  await page.goto(PORTAL + '/?sim-dual=0', { waitUntil: 'networkidle' });

  // ---- 1. click Live agent with NO publisher: must say so, loudly ----
  log('\n[1] Live agent clicked, no agent running');
  await page.click('#src-agent');
  await waitFor(async () => (await portalStream(page)).opens >= 1, 5000, 'portal ws open');
  await sleep(3800);
  let s = await j('/debug/stream');
  check('bridge sees the viewer', s.viewers === 1, `viewers=${s.viewers}`);
  check('bridge verdict DOWN with no publisher', s.health.status === 'DOWN', s.health.status);
  let ps = await portalStream(page);
  check('portal reports no-frames (socket open, nothing arrives)', ps.stalls >= 1, `stalls=${ps.stalls}`);
  const waitingOverlay = await page.evaluate(() => document.getElementById('log').innerText.includes('no-frames'));
  check('portal log shows the no-frames diagnosis', waitingOverlay);

  // ---- 2. healthy stream ----
  log('\n[2] Healthy 800x450 @30fps');
  let agent = startAgent('--w', 800, '--h', 450, '--fps', 30, '--src', 'dxcam');
  await waitFor(async () => (await portalStream(page)).decoded > 30, 8000, 'frames decoded in portal');
  await sleep(2500);
  s = await j('/debug/stream');
  ps = await portalStream(page);
  check('bridge verdict OK', s.health.status === 'OK', JSON.stringify(s.health.checks.filter((c) => !c.ok)));
  check('bridge fps >= 20', s.stream.fps_5s >= 20, `fps=${s.stream.fps_5s}`);
  check('bridge source = dxcam, none synthetic', s.stream.src.dxcam > 0 && !s.stream.synthetic);
  check('bridge dims 800x450', JSON.stringify(s.stream.dims) === '[800,450]');
  check('portal canvas matches frame size', JSON.stringify(ps.canvas) === '[800,450]', JSON.stringify(ps.canvas));
  check('portal decoded >= 80% of received', ps.decoded >= ps.rx * 0.8, `${ps.decoded}/${ps.rx}`);
  check('portal zero decode/draw errors', ps.decodeErrors === 0 && ps.drawErrors === 0);
  check('portal last frame fresh (<500ms)', ps.lastRxAgeMs !== null && ps.lastRxAgeMs < 500, `${ps.lastRxAgeMs}ms`);
  const lit = await page.evaluate(() => {
    const cv = document.getElementById('cv-win'), c2 = cv.getContext('2d');
    const d = c2.getImageData(0, 0, cv.width, cv.height).data; let n = 0;
    for (let i = 0; i < d.length; i += 64) if (d[i] > 150 && d[i + 2] < 90) n++;
    return n;
  });
  check('pixels from the agent frame are actually on the canvas', lit > 20, `orange px sampled=${lit}`);
  await page.screenshot({ path: join(DBG, 'e2e-healthy.png') });

  // ---- 3. resolution change mid-stream ----
  log('\n[3] Resolution change 800x450 -> 1280x720');
  await kill(agent); agent = startAgent('--w', 1280, '--h', 720, '--fps', 30, '--seq-start', 100000);
  await waitFor(async () => JSON.stringify((await portalStream(page)).canvas) === '[1280,720]', 6000, 'portal resize');
  ps = await portalStream(page);
  check('portal resized window, no crash', ps.resizes >= 2 && ps.win[0] > 0, JSON.stringify(ps.win));
  await sleep(1500); s = await j('/debug/stream');
  check('bridge logged resolution-change', (s.stream.anomalies['resolution-change'] || 0) >= 1);

  // ---- 4. corrupt frames ----
  log('\n[4] Truncated/corrupt frames every 5th');
  await kill(agent); agent = startAgent('--w', 800, '--h', 450, '--fps', 30, '--corrupt-every', 5, '--seq-start', 200000);
  await sleep(3000);
  s = await j('/debug/stream'); ps = await portalStream(page);
  check('bridge flagged invalid frames', s.stream.invalid > 0, `invalid=${s.stream.invalid}`);
  check('portal survived and counted decode errors', ps.decodeErrors > 0 || s.stream.invalid > 0, `decodeErrors=${ps.decodeErrors}`);
  check('portal kept streaming good frames', (await portalStream(page)).lastRxAgeMs < 800);

  // ---- 5. agent dies mid-stream ----
  log('\n[5] Agent process killed (stall)');
  await kill(agent);
  await sleep(3500);
  s = await j('/debug/stream'); ps = await portalStream(page);
  check('bridge detects stall', s.stream.stalled && s.stream.stalls >= 1);
  check('bridge verdict DOWN', s.health.status === 'DOWN', s.health.status);
  check('portal detects stall', ps.stalls >= 2, `stalls=${ps.stalls}`);
  // recovery
  agent = startAgent('--w', 800, '--h', 450, '--fps', 30, '--seq-start', 300000);
  await sleep(2500); s = await j('/debug/stream');
  check('bridge recovers after agent restart', !s.stream.stalled, JSON.stringify(s.stream.anomalies));
  check('recovery logged', (s.stream.anomalies['stall-recovered'] || 0) >= 1);

  // ---- 6. capture backend failed -> synthetic ----
  log('\n[6] Agent falls back to FAKE synthetic frames');
  await kill(agent); agent = startAgent('--w', 640, '--h', 360, '--fps', 30, '--src', 'synthetic', '--seq-start', 400000);
  await sleep(2500); s = await j('/debug/stream');
  check('bridge refuses to call synthetic "OK"', s.health.status === 'DEGRADED' && s.stream.synthetic > 0, s.health.status);

  // ---- 7. black frames (permission denied / DRM) ----
  log('\n[7] Agent sends flat black frames');
  await kill(agent); agent = startAgent('--blank', '--w', 800, '--h', 450, '--fps', 30, '--seq-start', 500000);
  await waitFor(async () => (await portalStream(page)).blank >= 1, 12000, 'portal blank detection').catch(() => {});
  ps = await portalStream(page);
  check('portal flags blank/black frames', ps.blank >= 1, `blank=${ps.blank}`);

  // ---- 8. bridge restart: socket closes, portal must reconnect itself ----
  log('\n[8] Bridge process restarted');
  await kill(agent);
  const before = await portalStream(page);
  await kill(bridge); await sleep(800);
  bridge = startBridge(); await ready();
  agent = startAgent('--w', 800, '--h', 450, '--fps', 30, '--seq-start', 600000);
  await waitFor(async () => (await portalStream(page)).opens > before.opens, 15000, 'portal reconnect');
  await waitFor(async () => (await portalStream(page)).rx > before.rx + 20, 10000, 'frames resume after reconnect');
  ps = await portalStream(page);
  check('portal auto-reconnected', ps.opens > before.opens && ps.reconnects >= 1, `opens ${before.opens}->${ps.opens}`);
  check('portal close was recorded', ps.closes > before.closes && ps.lastCloseCode !== null, `code=${ps.lastCloseCode}`);
  s = await j('/debug/stream');
  check('bridge sees viewer again', s.viewers === 1);

  // ---- 9. toggle away and back (timer/socket leaks) ----
  log('\n[9] Toggle sandbox <-> live x5');
  for (let i = 0; i < 5; i++) { await page.click('#src-sandbox'); await sleep(150); await page.click('#src-agent'); await sleep(250); }
  await sleep(1500);
  s = await j('/debug/stream');
  check('exactly one viewer socket after toggling (no leak)', s.viewers === 1, `viewers=${s.viewers}`);
  check('stream flowing after toggles', (await portalStream(page)).lastRxAgeMs < 800);

  // ---- 10. event trail + page errors ----
  log('\n[10] Evidence trail');
  // Read the crash-safe on-disk log (the in-memory ring was reset by the bridge restart in [8]).
  const ev = readFileSync(join(DBG, 'events.jsonl'), 'utf8').trim().split('\n').map((l) => JSON.parse(l).kind);
  for (const k of ['stream-first-frame', 'stream-stall', 'stream-stall-recovered', 'stream-resolution-change', 'stream-synthetic', 'stream-invalid-frame', 'client:ws-close', 'client:no-frames'])
    check(`flight recorder contains ${k}`, ev.includes(k));
  const bundle = await fetch(BRIDGE + '/debug/bundle');
  check('/debug/bundle downloads', bundle.ok && (await bundle.arrayBuffer()).byteLength > 500);
  const expected = /WebSocket connection|Failed to load resource|ERR_CONNECTION|net::|fetch/i; // bridge restart noise is expected
  const unexpected = pageErrors.filter((e) => !expected.test(e));
  check('zero unexpected page/console errors', unexpected.length === 0, unexpected.slice(0, 3).join(' | '));
  await page.screenshot({ path: join(DBG, 'e2e-final.png') });
} catch (e) {
  failures.push('harness: ' + (e.stack || e));
  log('HARNESS ERROR', e.message);
} finally {
  if (browser) await browser.close();
  for (const p of procs) await kill(p);
}
log(`\nartifacts: ${DBG}`);
if (failures.length) { log(`\nVERIFY FAIL (${failures.length}):\n - ${failures.join('\n - ')}`); process.exit(1); }
log('\nVERIFY PASS: live-agent stream, all faults detected, recovered');
