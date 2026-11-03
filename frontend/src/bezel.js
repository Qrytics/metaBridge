export const EDGE_THRESHOLD_PX = 2;

export function verticalOffset(hLeft, hRight) {
  if (!hLeft || !hRight) return 0;
  return Math.floor((hRight - hLeft) / 2);
}

export function straddleView(winX, winY, winW, winH, wLeft, hLeft = 0, hRight = 0) {
  const hOffset = verticalOffset(hLeft, hRight);
  const overflow = winX + winW - wLeft;
  if (overflow <= 0) {
    return {
      straddling: false,
      macWinX: 0,
      macWinY: winY + hOffset,
      leftVisibleW: winW,
      rightVisibleW: 0,
      straddleOffsetPx: 0,
    };
  }
  return {
    straddling: true,
    macWinX: winX - wLeft,
    macWinY: winY + hOffset,
    leftVisibleW: Math.max(0, wLeft - winX),
    rightVisibleW: overflow,
    straddleOffsetPx: overflow,
  };
}

export function cursorOwner(cx, wLeft, threshold = EDGE_THRESHOLD_PX) {
  return cx >= wLeft - threshold ? 'MAC' : 'WIN';
}

export function clampCursor(cx, cy, w, h) {
  return [Math.max(0, Math.min(cx, w - 1)), Math.max(0, Math.min(cy, h - 1))];
}

export function macToHostGameCoords(macX, macY, macWinX, macWinY, winW, winH) {
  return [
    Math.max(0, Math.min(macX - macWinX, winW - 1)),
    Math.max(0, Math.min(macY - macWinY, winH - 1)),
  ];
}

export function dragHandoff(cx, wLeft, dragging, threshold = EDGE_THRESHOLD_PX) {
  const owner = cursorOwner(cx, wLeft, threshold);
  return { owner, dragging, crossed: Boolean(dragging && owner === 'MAC') };
}

export function viewportToFrame(clickX, clickY, originX, originY, scale = 1) {
  return [(clickX - originX) * scale, (clickY - originY) * scale];
}

export function springStep(x, v, target, k = 90, d = 14, dt = 1 / 60) {
  const F = -k * (x - target) - d * v;
  v += F * dt;
  x += v * dt;
  if (Math.abs(x - target) < 0.5 && Math.abs(v) < 0.5) { x = target; v = 0; }
  return [x, v];
}

// SPAN mode: one world rendered 1:1 across both screens (Eyefinity-style).
// Fit any frame onto the desktop: 1:1 when it fits, scaled to fit otherwise.
export function fitScale(fw, fh, maxW, maxH) {
  if (fw <= 0 || fh <= 0 || maxW <= 0 || maxH <= 0) return 1;
  return Math.min(1, maxW / fw, maxH / fh);
}
export const SPAN_W = 1920; // == W_LEFT + W_RIGHT, both canvases edge-to-edge
export const SPAN_WORLD_COLS = 120; // 120 tiles * 16px == SPAN_W, zero stretch

export function spanCamX(playerCX, viewW, worldW) {
  if (worldW <= viewW) return 0;
  return Math.max(0, Math.min(playerCX - viewW / 2, worldW - viewW));
}

export function spanGlobalToWorld(gx, gy, yOff) {
  return [gx, gy - yOff];
}
