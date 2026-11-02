// Thin REST client for the Meta AI Bezel Membrane routers.

export function bridgeBase() {
  return import.meta.env.VITE_BRIDGE_URL || 'http://localhost:8000';
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

export function transferFile(filename, text, transform) {
  const fd = new FormData();
  fd.append('file', new Blob([text], { type: 'text/plain' }), filename);
  return fetch(`${bridgeBase()}/membrane/transfer-file?transform=${transform}`, {
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

export function restyleAsset(imageB64, style = 'concept-art-hd') {
  return post('/membrane/restyle-asset', JSON.stringify({ image_b64: imageB64, style }));
}

export function decodeB64(b64) {
  return new TextDecoder().decode(
    Uint8Array.from(atob(b64), (c) => c.charCodeAt(0)),
  );
}
