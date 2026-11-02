import { straddleView, cursorOwner } from './bezel.js';

const BRIDGE = import.meta.env.VITE_BRIDGE_URL || 'http://localhost:8000';
const params = new URLSearchParams(location.search);
const simDual = params.get('sim-dual') !== '0'; // default ON for local testing
document.getElementById('m-mode').textContent = simDual ? 'SIM-DUAL' : 'LINKED';

const W_LEFT = 960; // viewport-mapped left width (canvas px)
const cvWin = document.getElementById('cv-win');
const cvMac = document.getElementById('cv-mac');
const ctxWin = cvWin.getContext('2d');
const ctxMac = cvMac.getContext('2d');
const drag = document.getElementById('drag');
const logEl = document.getElementById('log');
const strip = document.getElementById('bezel-strip');

const WIN_W = 420, WIN_H = 260;
let winY = 170;
let t = 0;
let frames = 0;
let lastFpsT = performance.now();
let cursorX = 200;

function log(msg) {
  const line = document.createElement('div');
  line.textContent = `[${new Date().toISOString().slice(11, 19)}] ${msg}`;
  logEl.prepend(line);
}

function drawWorld(ctx, ox, w, label) {
  // Dark sandbox room + parallax hills + bouncing player block (mini-Terraria).
  const H = 600;
  ctx.fillStyle = '#0a0e16';
  ctx.fillRect(0, 0, w, H);
  ctx.fillStyle = '#131b28';
  for (let i = 0; i < 4; i++) {
    const y0 = H - 90 - i * 34;
    ctx.beginPath();
    ctx.moveTo(0, y0);
    for (let x = 0; x <= w; x += 8) {
      ctx.lineTo(x, y0 + 12 * Math.sin((x + ox + t * (40 + i * 30)) / 90));
    }
    ctx.lineTo(w, H); ctx.lineTo(0, H); ctx.fill();
  }
  const px = w / 2 + (w / 3) * Math.sin(t * 1.7) - ox * 0;
  const py = H - 150 + 30 * Math.abs(Math.sin(t * 3.1));
  ctx.fillStyle = '#56d678';
  ctx.fillRect(px - 18, py - 18, 36, 36);
  ctx.fillStyle = '#06110a';
  ctx.fillRect(px - 10, py - 8, 8, 8);
  ctx.fillRect(px + 2, py - 8, 8, 8);
  ctx.fillStyle = '#8a94a3';
  ctx.font = '11px monospace';
  ctx.fillText(label, 8, 24);
}

function frame() {
  t += 1 / 60;
  const winX = parseInt(drag.value, 10);
  const v = straddleView(winX, winY, WIN_W, WIN_H, W_LEFT);

  // HUD
  document.getElementById('m-straddle').textContent = String(v.straddleOffsetPx);
  const owner = cursorOwner(cursorX, W_LEFT);
  document.getElementById('owner-win').classList.toggle('active', owner === 'WIN');
  document.getElementById('owner-mac').classList.toggle('active', owner === 'MAC');
  strip.classList.toggle('lit', winX > W_LEFT - 30 || v.straddling);
  document.getElementById('win-geom').textContent = `win_x=${winX} left_vis=${v.leftVisibleW}`;
  document.getElementById('mac-geom').textContent = v.straddling
    ? `mac_win_x=${v.macWinX} right_vis=${v.rightVisibleW}` : 'no straddle';

  // LEFT viewport: draw window clipped to visible left part.
  ctxWin.save();
  ctxWin.clearRect(0, 0, cvWin.width, cvWin.height);
  ctxWin.beginPath();
  ctxWin.rect(0, 0, v.leftVisibleW, cvWin.height);
  ctxWin.clip();
  ctxWin.save();
  ctxWin.translate(winX, winY);
  drawWorldInto(ctxWin, WIN_W, WIN_H);
  ctxWin.restore();
  ctxWin.restore();

  // RIGHT viewport: overflow rendered from Mac screen left edge.
  ctxMac.clearRect(0, 0, cvMac.width, cvMac.height);
  if (v.straddling && simDual) {
    ctxMac.save();
    ctxMac.beginPath();
    ctxMac.rect(0, 0, v.rightVisibleW, cvMac.height);
    ctxMac.clip();
    ctxMac.translate(v.macWinX, v.macWinY);
    drawWorldInto(ctxMac, WIN_W, WIN_H);
    ctxMac.restore();
  } else if (!simDual) {
    ctxMac.fillStyle = '#8a94a3';
    ctxMac.font = '12px monospace';
    ctxMac.fillText('LINKED MODE: stream via WS /ws/viewport', 20, 40);
  }

  // Cursor cross
  for (const [ctx, base] of [[ctxWin, 0], [ctxMac, W_LEFT]]) {
    void base;
    void ctx;
  }
  drawCursor(ctxWin, cursorX, 300);
  if (owner === 'MAC') drawCursor(ctxMac, cursorX - W_LEFT, 300);

  frames++;
  const now = performance.now();
  if (now - lastFpsT >= 1000) {
    document.getElementById('m-fps').textContent = String(frames);
    frames = 0;
    lastFpsT = now;
  }
  requestAnimationFrame(frame);
}

function drawWorldInto(ctx, w, h) {
  const off = ctx.getTransform();
  void off;
  // Reuse world painter in window-local space.
  const tmp = document.createElement('canvas');
  tmp.width = w; tmp.height = h;
  const c = tmp.getContext('2d');
  c.fillStyle = '#0d1320';
  c.fillRect(0, 0, w, h);
  const px = w / 2 + (w / 3) * Math.sin(t * 1.7);
  const py = h - 80 + 24 * Math.abs(Math.sin(t * 3.1));
  c.fillStyle = '#1a2436';
  for (let i = 0; i < 3; i++) {
    const y0 = h - 40 - i * 22;
    c.beginPath(); c.moveTo(0, y0);
    for (let x = 0; x <= w; x += 8) c.lineTo(x, y0 + 8 * Math.sin((x + t * 60) / 70));
    c.lineTo(w, h); c.lineTo(0, h); c.fill();
  }
  c.fillStyle = '#56d678';
  c.fillRect(px - 18, py - 18, 36, 36);
  c.fillStyle = '#06110a';
  c.fillRect(px - 10, py - 8, 8, 8);
  c.fillRect(px + 2, py - 8, 8, 8);
  c.fillStyle = '#8a94a3';
  c.font = '11px monospace';
  c.fillText('TERRARIA.EXE · LIVE', 8, 18);
  ctx.drawImage(tmp, 0, 0);
  void drawWorld;
}

function drawCursor(ctx, x, y) {
  ctx.strokeStyle = '#ffb224';
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.moveTo(x - 8, y); ctx.lineTo(x + 8, y);
  ctx.moveTo(x, y - 8); ctx.lineTo(x, y + 8);
  ctx.stroke();
}

window.addEventListener('mousemove', (e) => {
  const r = cvWin.getBoundingClientRect();
  cursorX = Math.round(((e.clientX - r.left) / Math.max(1, r.width)) * cvWin.width);
});

async function hit(path, opts = {}) {
  try {
    const res = await fetch(`${BRIDGE}${path}`, opts);
    const j = await res.json();
    log(`${path} → ${JSON.stringify(j).slice(0, 160)}`);
  } catch (err) {
    log(`${path} !! bridge unreachable (${BRIDGE}): ${err}`);
  }
}

document.getElementById('btn-sam').onclick = () =>
  hit('/membrane/sam-rip', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ prompt: 'boss', point: [0.5, 0.5] }),
  });

document.getElementById('btn-xfer').onclick = () => {
  const fd = new FormData();
  fd.append('file', new Blob(['#!/bin/sh\necho hi\n'], { type: 'text/x-sh' }), 'setup.sh');
  hit('/membrane/transfer-file?transform=sh-to-ps1', { method: 'POST', body: fd });
};

document.getElementById('btn-voice').onclick = () =>
  hit('/membrane/voice-command', { method: 'POST', body: new Uint8Array([1, 2, 3, 4]) });

document.getElementById('btn-shot').onclick = () => {
  const winX = parseInt(drag.value, 10);
  drag.value = String(Math.min(1400, winX + 120));
  log(`slid window toward Mac (win_x=${drag.value})`);
};

requestAnimationFrame(frame);
log(`portal up · sim-dual=${simDual} · bridge=${BRIDGE}`);
