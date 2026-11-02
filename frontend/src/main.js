import { cursorOwner, dragHandoff, springStep, straddleView, viewportToFrame } from './bezel.js';
import { createGame, hitSlime, mineAt, placeAt, renderGame, stepGame, tileName, WORLD_H, WORLD_W } from './game.js';
import { decodeB64, restyleAsset, samRip, transferFile, voiceCommand } from './membrane.js';

// --- Global desktop geometry (canvas px = global units) ----------------------
const W_LEFT = 960;
const W_RIGHT = 960;
const WIN_W = 480;
const WIN_H = 320;
const TITLE_H = 28;
const TITLE = 'TERRARIA.EXE [PID 4812] // 60 FPS STREAM';

const params = new URLSearchParams(location.search);
const simDual = params.get('sim-dual') !== '0';
document.getElementById('m-mode').textContent = simDual ? 'SIM-DUAL' : 'LINKED';

const cvWin = document.getElementById('cv-win');
const cvMac = document.getElementById('cv-mac');
const ctxWin = cvWin.getContext('2d');
const ctxMac = cvMac.getContext('2d');
const dragSlider = document.getElementById('drag');
const logEl = document.getElementById('log');
const strip = document.getElementById('bezel-strip');

// --- Shared world state: ONE buffer renders both viewports (zero tearing) ---
const game = createGame();
const worldCanvas = document.createElement('canvas');
worldCanvas.width = WORLD_W; worldCanvas.height = WORLD_H;
const worldCtx = worldCanvas.getContext('2d');
const winCanvas = document.createElement('canvas');
winCanvas.width = WIN_W; winCanvas.height = WIN_H;
const winCtx = winCanvas.getContext('2d');

let winX = 240, winY = 140;
let winVX = 0, springTarget = null;
let dragging = false, dragGrabDX = 0, dragGrabDY = 0, dragMoved = 0, downGX = 0, downGY = 0, downBtn = 0, downAlt = false;
let cursorGX = 200, cursorGY = 300, owner = 'WIN';
let source = 'sandbox';
let agentFrame = null, agentBitmap = null, agentWS = null, lastFrameAt = 0;
let samMode = false;
let rips = []; // {fx, fy, prompt, poly:[[x,y]...], card}
const keys = { left: false, right: false, jump: false };
let frames = 0, lastFpsT = performance.now();

function log(msg) {
  const line = document.createElement('div');
  line.textContent = `[${new Date().toISOString().slice(11, 19)}] ${msg}`;
  logEl.prepend(line);
}
function tunnel(msg) { log(`MAC -> WIN INPUT TUNNEL: ${msg}`); }

// Debug/verification hook (Playwright + console poking).
window.__metaBridge = {
  get winX() { return Math.round(winX); },
  get winY() { return Math.round(winY); },
  get playerX() { return Math.round(game.player.x); },
  get straddle() { return straddleView(winX, winY, WIN_W, WIN_H, W_LEFT).straddleOffsetPx; },
  get owner() { return owner; },
  setWinX(x) { winX = Math.max(0, Math.min(x, W_LEFT + W_RIGHT - WIN_W)); },
};

// --- Coordinate helpers ------------------------------------------------------
function canvasLocal(canvas, clientX, clientY) {
  const r = canvas.getBoundingClientRect();
  return [
    ((clientX - r.left) / Math.max(1, r.width)) * canvas.width,
    ((clientY - r.top) / Math.max(1, r.height)) * canvas.height,
  ];
}
function globalFromEvent(canvas, isRight, clientX, clientY) {
  const [lx, ly] = canvasLocal(canvas, clientX, clientY);
  return isRight ? [lx + W_LEFT, ly] : [lx, ly];
}
function hitTitleBar(gx, gy) {
  return gx >= winX && gx <= winX + WIN_W && gy >= winY && gy <= winY + TITLE_H;
}
function inWindow(gx, gy) {
  return gx >= winX && gx <= winX + WIN_W && gy >= winY && gy <= winY + WIN_H;
}
function globalToGame(gx, gy) {
  return [gx - winX, gy - winY - TITLE_H]; // world is 480x288 below the title bar
}
function setOwner(gx) {
  const next = cursorOwner(Math.round(gx), W_LEFT);
  if (next !== owner) {
    owner = next;
    log(`cursor handoff -> CURSOR_OWNER: ${owner}`);
  }
}

// --- Sources: sandbox vs live agent stream -----------------------------------
const btnSandbox = document.getElementById('src-sandbox');
const btnAgent = document.getElementById('src-agent');
function setSource(next) {
  source = next;
  btnSandbox.classList.toggle('active', next === 'sandbox');
  btnAgent.classList.toggle('active', next === 'agent');
  log(`source -> ${next === 'sandbox' ? 'PLAYABLE_TERRARIA_SANDBOX' : 'LIVE_AGENT_STREAM'}`);
  if (next === 'agent') connectAgentStream();
  else if (agentWS) { try { agentWS.close(); } catch { /* noop */ } agentWS = null; }
}
btnSandbox.onclick = () => setSource('sandbox');
btnAgent.onclick = () => setSource('agent');

function bridgeBase() {
  return import.meta.env.VITE_BRIDGE_URL || 'http://localhost:8000';
}
function connectAgentStream() {
  if (agentWS) return;
  try {
    const url = bridgeBase().replace(/^http/, 'ws') + '/ws/viewport';
    agentWS = new WebSocket(url);
    agentWS.binaryType = 'arraybuffer';
    agentWS.onmessage = async (ev) => {
      if (ev.data instanceof ArrayBuffer) {
        try {
          agentBitmap = await createImageBitmap(new Blob([ev.data], { type: 'image/jpeg' }));
          lastFrameAt = performance.now();
        } catch { /* corrupt frame: keep last */ }
      }
    };
    agentWS.onerror = () => log(`agent stream !! bridge unreachable (${url})`);
    agentWS.onclose = () => { agentWS = null; };
  } catch (err) {
    log(`agent stream !! ${err}`);
  }
}

// --- Direct title-bar dragging across the bezel ------------------------------
function onDown(canvas, isRight, ev) {
  const [gx, gy] = globalFromEvent(canvas, isRight, ev.clientX, ev.clientY);
  cursorGX = gx; cursorGY = gy; setOwner(gx);
  downGX = gx; downGY = gy; downBtn = ev.button; downAlt = ev.altKey;
  if (ev.button === 2) return; // right-click reserves for block place (on mouseup)
  if (hitTitleBar(gx, gy)) {
    dragging = true; dragMoved = 0;
    dragGrabDX = gx - winX; dragGrabDY = gy - winY;
    downGX = gx; downGY = gy;
    log(`drag start @(${Math.round(gx)},${Math.round(gy)}) owner=${owner}`);
    ev.preventDefault();
    return;
  }
  // Potential game click / SAM rip (resolved on mouseup if not a drag).
  dragMoved = 0;
  dragging = false;
}
function onMove(canvas, isRight, ev) {
  const [gx, gy] = globalFromEvent(canvas, isRight, ev.clientX, ev.clientY);
  cursorGX = gx; cursorGY = gy;
  if (dragging) {
    dragMoved += Math.abs(gx - downGX) + Math.abs(gy - downGY);
    const prev = owner;
    winX = Math.max(0, Math.min(gx - dragGrabDX, W_LEFT + W_RIGHT - WIN_W));
    winY = Math.max(0, Math.min(gy - dragGrabDY, cvWin.height - WIN_H));
    const h = dragHandoff(Math.round(gx), W_LEFT, true);
    if (h.owner !== prev) {
      owner = h.owner;
      log(`drag handoff: active window drag crosses bezel -> CURSOR_OWNER: ${owner}`);
      flashBezel();
    }
  }
}
function onUp(canvas, isRight, ev) {
  const [gx, gy] = globalFromEvent(canvas, isRight, ev.clientX, ev.clientY);
  if (dragging) {
    dragging = false;
    const h = dragHandoff(Math.round(gx), W_LEFT, false);
    owner = h.owner;
    log(`drag drop @win_x=${Math.round(winX)} straddle=${straddleView(winX, winY, WIN_W, WIN_H, W_LEFT).straddleOffsetPx}px owner=${owner}`);
    return;
  }
  // Click (no drag): game input or SAM rip.
  if (Math.abs(gx - downGX) + Math.abs(gy - downGY) > 6) return;
  if (!inWindow(gx, gy)) return;
  const [wx, wy] = globalToGame(gx, gy);
  if (wy < 0 || wy >= WORLD_H) return;
  const macSide = owner === 'MAC';
  if (samMode || downAlt || ev.altKey) {
    samRipAt(wx, wy, gx, gy, macSide);
    return;
  }
  if (downBtn === 2 || ev.button === 2) {
    if (placeAt(game, wx, wy)) {
      if (macSide) tunnel(`PLACE (${Math.round(wx)},${Math.round(wy)})`);
      else log(`place ${tileName(game.selected)} @(${Math.round(wx)},${Math.round(wy)})`);
    }
  } else {
    if (hitSlime(game, wx, wy)) {
      if (macSide) tunnel(`SWORD_HIT boss (${Math.round(wx)},${Math.round(wy)})`);
      else log(`sword hit! slime hp=${game.slime.hp}`);
    } else {
      const t = mineAt(game, wx, wy);
      if (t !== null) {
        if (macSide) tunnel(`CLICK (${Math.round(wx)},${Math.round(wy)}) mine ${tileName(t)}`);
        else log(`mine ${tileName(t)} @(${Math.round(wx)},${Math.round(wy)})`);
      }
    }
  }
}

for (const [canvas, isRight] of [[cvWin, false], [cvMac, true]]) {
  canvas.addEventListener('mousedown', (ev) => onDown(canvas, isRight, ev));
  canvas.addEventListener('mousemove', (ev) => onMove(canvas, isRight, ev));
  canvas.addEventListener('mouseup', (ev) => onUp(canvas, isRight, ev));
  canvas.addEventListener('contextmenu', (ev) => ev.preventDefault());
}
window.addEventListener('mousemove', (ev) => {
  if (!dragging) return;
  // Keep the drag alive even when the pointer leaves both canvases.
  const stages = document.getElementById('stages').getBoundingClientRect();
  const unit = (stages.width - 26) / 2 / W_LEFT;
  const gx = (ev.clientX - stages.left) / unit;
  const gy = (ev.clientY - stages.top) / (((stages.height) / cvWin.height));
  if (gx >= -50 && gx <= W_LEFT + W_RIGHT + 50) {
    cursorGX = gx; cursorGY = gy;
    const prev = owner;
    winX = Math.max(0, Math.min(gx - dragGrabDX, W_LEFT + W_RIGHT - WIN_W));
    const h = dragHandoff(Math.round(gx), W_LEFT, true);
    if (h.owner !== prev) {
      owner = h.owner;
      log(`drag handoff: active window drag crosses bezel -> CURSOR_OWNER: ${owner}`);
      flashBezel();
    }
  }
});
window.addEventListener('mouseup', () => {
  if (dragging) {
    dragging = false;
    log(`drag drop @win_x=${Math.round(winX)} owner=${owner}`);
  }
});

// Keyboard: A/D/W/S/Space + arrows, 1-5 select block.
const KEYMAP = { a: 'left', arrowleft: 'left', d: 'right', arrowright: 'right', w: 'jump', s: null, ' ': 'jump', arrowup: 'jump' };
window.addEventListener('keydown', (ev) => {
  const k = ev.key.toLowerCase();
  if (k >= '1' && k <= '5') {
    game.selected = [1, 2, 3, 5, 4][Number(k) - 1];
    return;
  }
  if (k in KEYMAP && KEYMAP[k]) {
    if (!keys[KEYMAP[k]] && owner === 'MAC') tunnel(`KEY_${ev.key.toUpperCase()} down`);
    keys[KEYMAP[k]] = true;
    if ([' ', 'arrowup'].includes(k)) ev.preventDefault();
  }
  if (k === 's' || k === 'arrowdown') { if (owner === 'MAC') tunnel('KEY_S down'); }
});
window.addEventListener('keyup', (ev) => {
  const k = ev.key.toLowerCase();
  if (k in KEYMAP && KEYMAP[k]) keys[KEYMAP[k]] = false;
});

// --- Desktop file icons + cross-bezel transpile ------------------------------
const FILE_DEFS = [
  { name: 'deploy_server.ps1', kind: 'ps1', side: 'win', x: 20, y: 20,
    content: 'Write-Output "deploying..."\n$env:APP_PORT = 8080\n$env:APP_ENV = "prod"\nWrite-Output "done"\n' },
  { name: 'win_firewall_rules.bat', kind: 'bat', side: 'win', x: 130, y: 20,
    content: '@echo off\r\necho applying firewall rules\r\nnetsh advfirewall firewall add rule name="game" dir=in action=allow\r\n' },
  { name: 'terraria_world.wld', kind: 'wld', side: 'win', x: 20, y: 130,
    content: 'WLD1:terraria-world-save:seed=1337:size=large:difficulty=master\n' },
  { name: 'setup_mac_daemon.sh', kind: 'sh', side: 'mac', x: 20, y: 20,
    content: '#!/bin/sh\necho starting daemon\nexport APP_PORT=8080\necho ready\n' },
];
const GLYPH = { ps1: '▤', bat: '▤', sh: '⬣', wld: '◈' };
function transformFor(name) {
  if (name.endsWith('.ps1')) return 'ps1-to-sh';
  if (name.endsWith('.bat')) return 'bat-to-sh';
  if (name.endsWith('.sh')) return 'sh-to-ps1';
  return 'none';
}
function mountFiles() {
  for (const f of FILE_DEFS) {
    const el = document.createElement('div');
    el.className = `fileicon ${f.kind}`;
    el.innerHTML = `<span class="glyph">${GLYPH[f.kind]}</span>${f.name}<small>${f.side === 'win' ? 'WIN desktop' : 'MAC desktop'}</small>`;
    el.style.left = `${f.x}px`; el.style.top = `${f.y}px`;
    el.addEventListener('pointerdown', (ev) => startIconDrag(ev, f, el));
    document.getElementById(f.side === 'win' ? 'files-win' : 'files-mac').appendChild(el);
  }
}
function globalXFromClient(clientX) {
  const stages = document.getElementById('stages').getBoundingClientRect();
  return ((clientX - stages.left) / ((stages.width - 26) / 2)) * W_LEFT;
}
function startIconDrag(ev, f, el) {
  ev.preventDefault();
  const ghost = el.cloneNode(true);
  ghost.style.position = 'fixed';
  ghost.style.left = `${ev.clientX - 46}px`; ghost.style.top = `${ev.clientY - 20}px`;
  ghost.style.zIndex = 60; ghost.style.opacity = '0.92';
  document.body.appendChild(ghost);
  const move = (e) => {
    ghost.style.left = `${e.clientX - 46}px`; ghost.style.top = `${e.clientY - 20}px`;
    if (globalXFromClient(e.clientX) >= W_LEFT - 30) flashBezel();
  };
  const up = async (e) => {
    window.removeEventListener('pointermove', move);
    window.removeEventListener('pointerup', up);
    ghost.remove();
    const gx = globalXFromClient(e.clientX);
    // WIN -> MAC bezel cross: transpile + materialize + inspector modal.
    if (f.side === 'win' && gx >= W_LEFT) {
      flashBezel(true);
      const transform = transformFor(f.name);
      log(`bezel cross: ${f.name} -> POST /membrane/transfer-file (${transform})`);
      try {
        const res = await transferFile(f.name, f.content, transform);
        const text = decodeB64(res.content_b64);
        addMacFile(res.target_name || (f.name + '.sh'), text);
        openModal(f.name, f.content, res.target_name, text,
          `critic=${res.ok ? 'PASS' : 'FAIL'} retries=${res.retries} :: ${res.notes}`);
        log(`membrane drop: ${res.target_name} on MAC desktop (critic ${res.ok ? 'PASS' : 'FAIL'}, ${res.retries} retr)`);
      } catch (err) {
        log(`membrane transfer !! ${err}`);
      }
    } else if (f.side === 'mac' && gx < W_LEFT) {
      log(`bezel cross: ${f.name} -> WIN desktop (direct copy, transform=${transformFor(f.name)})`);
    }
  };
  window.addEventListener('pointermove', move);
  window.addEventListener('pointerup', up);
}
function addMacFile(name, content) {
  const kind = name.endsWith('.sh') ? 'sh' : name.endsWith('.ps1') ? 'ps1' : 'wld';
  const el = document.createElement('div');
  el.className = `fileicon ${kind}`;
  el.innerHTML = `<span class="glyph">${GLYPH[kind] || '◈'}</span>${name}<small>MAC desktop · converted</small>`;
  el.style.left = `${40 + Math.random() * 120}px`; el.style.top = `${160 + Math.random() * 120}px`;
  const f = { name, kind, side: 'mac', content };
  el.addEventListener('pointerdown', (ev) => startIconDrag(ev, f, el));
  document.getElementById('files-mac').appendChild(el);
}
function openModal(aName, aText, bName, bText, notes) {
  document.getElementById('diff-a-name').textContent = `BEFORE · ${aName}`;
  document.getElementById('diff-b-name').textContent = `AFTER · ${bName}`;
  document.getElementById('diff-a').textContent = aText;
  document.getElementById('diff-b').textContent = bText;
  document.getElementById('modal-notes').textContent = notes;
  document.getElementById('modal').hidden = false;
}
document.getElementById('modal-close').onclick = () => {
  document.getElementById('modal').hidden = true;
};
let bezelFlashT = 0;
function flashBezel(strong = false) {
  strip.classList.add(strong ? 'amber' : 'lit');
  if (strong) setTimeout(() => strip.classList.remove('amber'), 650);
  bezelFlashT = performance.now();
}

// --- SAM 3.1 live entity rip ---------------------------------------------------
const btnSamMode = document.getElementById('btn-sam-mode');
function setSamMode(on) {
  samMode = on;
  btnSamMode.textContent = `SAM 3.1 RIP MODE: ${on ? 'ON' : 'OFF'}`;
  btnSamMode.classList.toggle('armed', on);
  log(`sam-3.1 rip mode ${on ? 'ARMED' : 'off'} — Alt+click also rips`);
}
btnSamMode.onclick = () => setSamMode(!samMode);

function pickPrompt(wx, wy) {
  if (hitSlime(game, wx, wy)) return 'boss';
  const p = game.player;
  if (wx >= p.x - 6 && wx <= p.x + p.w + 6 && wy >= p.y - 8 && wy <= p.y + p.h + 6) return 'player character';
  const e = game.eye;
  if (wx >= e.x && wx <= e.x + 30 && wy >= e.y && wy <= e.y + 22) return 'flying eye boss';
  const c = Math.floor(wx / 16), r = Math.floor(wy / 16);
  if (game.at && game.at(c, r) === 5) return 'torch';
  return 'item';
}
async function samRipAt(wx, wy, gx, gy, macSide) {
  const [fx, fy] = viewportToFrame(wx, wy, 0, 0, 1);
  const prompt = pickPrompt(wx, wy);
  if (macSide) tunnel(`SAM_RIP "${prompt}" @frame(${Math.round(fx)},${Math.round(fy)})`);
  log(`sam-3.1 rip "${prompt}" @frame(${Math.round(fx)},${Math.round(fy)})`);
  try {
    const res = await samRip(prompt, [fx / WORLD_W, fy / WORLD_H]);
    const [x0, y0, x1, y1] = res.bbox || [0.25, 0.25, 0.75, 0.75];
    const poly = polyFromBbox(x0 * WORLD_W, y0 * WORLD_H, x1 * WORLD_W, y1 * WORLD_H, prompt);
    rips.push({ fx: (x0 + x1) / 2 * WORLD_W, fy: (y0 + y1) / 2 * WORLD_H, prompt, poly });
    mintSpriteCard(poly, prompt, gx, gy);
    log(`sam-3.1 contour locked (${poly.length} pts) — drag the card across the bezel`);
  } catch (err) {
    log(`sam-3.1 rip !! ${err}`);
  }
}
function polyFromBbox(x0, y0, x1, y1, seed) {
  // Deterministic neon polygon from a bbox (dev stand-in for the SAM mask).
  let h = 0;
  for (const ch of seed) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  const cx = (x0 + x1) / 2, cy = (y0 + y1) / 2, rx = (x1 - x0) / 2, ry = (y1 - y0) / 2;
  const pts = [];
  for (let i = 0; i < 10; i++) {
    h = (h * 1103515245 + 12345) >>> 0;
    const j = 0.82 + ((h >> (i % 16)) % 100) / 400;
    const a = (i / 10) * Math.PI * 2;
    pts.push([cx + Math.cos(a) * rx * j, cy + Math.sin(a) * ry * j]);
  }
  return pts;
}
function mintSpriteCard(poly, prompt, gx, gy) {
  const layer = document.getElementById('sprite-layer');
  const card = document.createElement('div');
  card.className = 'spritecard';
  const xs = poly.map((p) => p[0]), ys = poly.map((p) => p[1]);
  const x0 = Math.max(0, Math.min(...xs) - 6), y0 = Math.max(0, Math.min(...ys) - 6);
  const w = Math.min(WORLD_W - x0, Math.max(...xs) - x0 + 12);
  const h = Math.min(WORLD_H - y0, Math.max(...ys) - y0 + 12);
  card.innerHTML = `<canvas width="96" height="72"></canvas><div>${prompt}</div><div class="row"><button class="rs">MUSE IMAGE HD RESTYLE</button></div>`;
  const c = card.querySelector('canvas');
  c.getContext('2d').drawImage(worldCanvas, x0, y0, w, h, 0, 0, 96, 72);
  card.style.left = `${Math.min(innerWidth - 130, gx / ((W_LEFT + W_RIGHT)) * innerWidth)}px`;
  card.style.top = '180px';
  card.querySelector('.rs').onclick = async (ev) => {
    ev.stopPropagation();
    try {
      const res = await restyleAsset('', 'concept-art-hd');
      card.insertAdjacentHTML('beforeend', `<div class="hd">HD restyle ✓ (${res.style})</div>`);
      log(`muse-image restyle ✓ "${prompt}" -> ${res.style}`);
    } catch (err) {
      log(`restyle !! ${err}`);
    }
  };
  card.addEventListener('pointerdown', (ev) => {
    ev.preventDefault();
    const ox = ev.clientX - card.offsetLeft, oy = ev.clientY - card.offsetTop;
    const move = (e) => { card.style.left = `${e.clientX - ox}px`; card.style.top = `${e.clientY - oy}px`; };
    const up = (e) => {
      window.removeEventListener('pointermove', move);
      window.removeEventListener('pointerup', up);
      if (globalXFromClient(e.clientX) >= W_LEFT) {
        flashBezel(true);
        log(`sprite "${prompt}" teleported across bezel -> MAC desktop`);
      }
    };
    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', up);
  });
  layer.appendChild(card);
}
function drawRipContours() {
  winCtx.save();
  winCtx.strokeStyle = '#39ff88';
  winCtx.lineWidth = 2;
  winCtx.shadowColor = '#39ff88';
  winCtx.shadowBlur = 8;
  for (const rip of rips.slice(-3)) {
    winCtx.beginPath();
    rip.poly.forEach(([x, y], i) => {
      const px = x, py = TITLE_H + y;
      if (i === 0) winCtx.moveTo(px, py);
      else winCtx.lineTo(px, py);
    });
    winCtx.closePath();
    winCtx.stroke();
  }
  winCtx.restore();
}

// --- Voice cross-OS command bar --------------------------------------------------
const btnMic = document.getElementById('btn-mic');
async function voiceAction(target, label) {
  btnMic.classList.add('live');
  try {
    const res = await voiceCommand(new Uint8Array([82, 73, 70, 70, 1, 2, 3, 4]));
    log(`voice "${res.transcript}" -> action=${res.action} (${label})`);
    springTarget = target;
  } catch (err) {
    log(`voice !! ${err} — springing anyway (${label})`);
    springTarget = target;
  } finally {
    setTimeout(() => btnMic.classList.remove('live'), 900);
  }
}
btnMic.onclick = () => voiceAction(W_LEFT + 120, 'teleport-to-mac+screenshot');
document.getElementById('btn-v50').onclick = () => voiceAction(W_LEFT - WIN_W / 2, 'glide-50%-straddle');
document.getElementById('btn-vmac').onclick = () => voiceAction(W_LEFT + 120, 'teleport-to-mac');
document.getElementById('btn-vwin').onclick = () => voiceAction(200, 'back-to-win');

// --- Render loop: one shared buffer, two clipped viewports -----------------------
dragSlider.addEventListener('input', () => { winX = Number(dragSlider.value); });
mountFiles();

function drawWindowChrome() {
  winCtx.fillStyle = '#0b0e13';
  winCtx.fillRect(0, 0, WIN_W, WIN_H);
  // Title bar
  winCtx.fillStyle = dragging ? '#17351f' : '#141a24';
  winCtx.fillRect(0, 0, WIN_W, TITLE_H);
  winCtx.fillStyle = dragging ? '#56d678' : '#8a94a3';
  winCtx.font = '11px monospace';
  winCtx.fillText(`${TITLE} · ${source === 'sandbox' ? 'SANDBOX' : 'AGENT'}`, 8, 18);
  winCtx.fillStyle = '#3a4354';
  winCtx.fillRect(0, TITLE_H - 1, WIN_W, 1);
  // Content
  if (source === 'agent' && agentBitmap) {
    winCtx.drawImage(agentBitmap, 0, TITLE_H, WIN_W, WIN_H - TITLE_H);
    winCtx.fillStyle = 'rgba(76,195,255,0.9)';
    winCtx.font = '10px monospace';
    winCtx.fillText('LIVE_AGENT_STREAM', 8, TITLE_H + 16);
  } else {
    renderGame(worldCtx, game);
    winCtx.drawImage(worldCanvas, 0, TITLE_H);
    if (source === 'agent' && !agentBitmap) {
      winCtx.fillStyle = 'rgba(5,7,10,0.7)';
      winCtx.fillRect(0, TITLE_H, WIN_W, WIN_H - TITLE_H);
      winCtx.fillStyle = '#8a94a3';
      winCtx.font = '11px monospace';
      winCtx.fillText('waiting for agent frames on WS /ws/viewport ...', 24, TITLE_H + 60);
    }
  }
  drawRipContours();
}

function frame() {
  // Spring animation (voice glide).
  if (springTarget !== null) {
    const [nx, nv] = springStep(winX, winVX, springTarget);
    winX = nx; winVX = nv;
    if (nv === 0 && nx === springTarget) { springTarget = null; log(`glide settled @win_x=${Math.round(winX)}`); }
  }
  stepGame(game, keys, 1);
  drawWindowChrome();
  const v = straddleView(Math.round(winX), Math.round(winY), WIN_W, WIN_H, W_LEFT);

  document.getElementById('m-straddle').textContent = String(v.straddleOffsetPx);
  document.getElementById('owner-win').classList.toggle('active', owner === 'WIN');
  document.getElementById('owner-mac').classList.toggle('active', owner === 'MAC');
  document.getElementById('m-lat').textContent =
    source === 'agent' && lastFrameAt ? `${Math.max(1, Math.round(performance.now() - lastFrameAt))}.0` : '1.2';
  if (document.activeElement !== dragSlider) dragSlider.value = String(Math.round(winX));
  if (!dragging) setOwner(cursorGX);
  strip.classList.toggle('lit', winX > W_LEFT - 30 || v.straddling || performance.now() - bezelFlashT < 400);
  document.getElementById('win-geom').textContent = `win_x=${Math.round(winX)} left_vis=${v.leftVisibleW}`;
  document.getElementById('mac-geom').textContent = v.straddling
    ? `mac_win_x=${v.macWinX} right_vis=${v.rightVisibleW}` : 'no straddle';

  // LEFT: clip global [0, W_LEFT). RIGHT: overflow from global W_LEFT.
  ctxWin.clearRect(0, 0, cvWin.width, cvWin.height);
  ctxWin.save();
  ctxWin.beginPath();
  // Left canvas local x == global x: visible slice starts at winX.
  ctxWin.rect(Math.round(winX), 0, v.leftVisibleW, cvWin.height);
  ctxWin.clip();
  ctxWin.drawImage(winCanvas, Math.round(winX), Math.round(winY));
  ctxWin.restore();

  ctxMac.clearRect(0, 0, cvMac.width, cvMac.height);
  if (simDual && v.straddling) {
    ctxMac.save();
    ctxMac.beginPath();
    ctxMac.rect(0, 0, v.rightVisibleW, cvMac.height);
    ctxMac.clip();
    ctxMac.drawImage(winCanvas, v.macWinX, Math.round(winY));
    ctxMac.restore();
  } else if (!simDual) {
    ctxMac.fillStyle = '#8a94a3';
    ctxMac.font = '12px monospace';
    ctxMac.fillText('LINKED MODE: stream via WS /ws/viewport', 20, 40);
  }

  // Cursor cross.
  const drawCursor = (ctx, x, y) => {
    ctx.strokeStyle = '#ffb224';
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(x - 8, y); ctx.lineTo(x + 8, y);
    ctx.moveTo(x, y - 8); ctx.lineTo(x, y + 8);
    ctx.stroke();
  };
  if (owner === 'WIN') drawCursor(ctxWin, cursorGX, cursorGY);
  else drawCursor(ctxMac, cursorGX - W_LEFT, cursorGY);

  frames++;
  const now = performance.now();
  if (now - lastFpsT >= 1000) {
    document.getElementById('m-fps').textContent = String(frames);
    frames = 0;
    lastFpsT = now;
  }
  requestAnimationFrame(frame);
}

requestAnimationFrame(frame);
log(`portal up · sim-dual=${simDual} · drag the title bar across the bezel`);
window.__metaBridge.game = game;
