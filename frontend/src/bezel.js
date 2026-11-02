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
