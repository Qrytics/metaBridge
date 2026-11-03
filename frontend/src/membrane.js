// Thin REST client for the Meta AI Bezel Membrane routers.

export function bridgeBase() {
  // Explicit build-time URL wins; otherwise talk to whoever serves the
  // portal (same laptop in sim-dual, LAN host in 2-machine mode).
  if (import.meta.env.VITE_BRIDGE_URL) return import.meta.env.VITE_BRIDGE_URL;
  try {
    const h = window.location.hostname;
    if (h) return `http://${h}:8000`;
  } catch { /* non-browser (tests): fall through */ }
  return 'http://localhost:8000';
}

async function post(path, body, contentType = 'application/json') {
  const res = await fetch(`${bridgeBase()}${path}`, {
    method: 'POST',
    headers: contentType ? { 'Content-Type': contentType } : {},
    body,
  });
  if (!res.ok) throw new Error(`${path} -> HTTP ${res.status}`);
  return res.json();
}

export function transferFile(filename, text, transform, land = true) {
  const fd = new FormData();
  fd.append('file', new Blob([text], { type: 'text/plain' }), filename);
  return fetch(`${bridgeBase()}/membrane/transfer-file?transform=${transform}${land ? '&land=1' : ''}`, {
    method: 'POST',
    body: fd,
  }).then((r) => {
    if (!r.ok) throw new Error(`transfer-file -> HTTP ${r.status}`);
    return r.json();
  });
}

export function samRip(prompt, point, imageB64 = '') {
  return post('/membrane/sam-rip', JSON.stringify({ prompt, point, image_b64: imageB64 }));
}

export function voiceCommand(wavBytes) {
  return post('/membrane/voice-command', wavBytes, 'audio/wav');
}

export function voiceCommandRaw(blob) {
  return post('/membrane/voice-command-raw', blob, blob.type || 'application/octet-stream');
}

export function restyleAsset(imageB64, style = 'concept-art-hd') {
  return post('/membrane/restyle-asset', JSON.stringify({ image_b64: imageB64, style }));
}

export function decodeB64(b64) {
  return new TextDecoder().decode(
    Uint8Array.from(atob(b64), (c) => c.charCodeAt(0)),
  );
}
