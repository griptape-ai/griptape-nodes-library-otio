// Small DOM helpers shared by the timeline editor modules.

export function el(tag, attrs = {}, children = []) {
  const node = document.createElement(tag);
  for (const [key, val] of Object.entries(attrs)) {
    if (key === 'class') node.className = val;
    else if (key === 'style') node.style.cssText = val;
    else if (key === 'text') node.textContent = val;
    else if (key.startsWith('on')) node.addEventListener(key.slice(2), val);
    else if (val !== false && val !== null && val !== undefined) node.setAttribute(key, val === true ? '' : val);
  }
  for (const child of [].concat(children)) if (child) node.appendChild(child);
  return node;
}

// Dark or light text, whichever reads better on `color`.
export function readableOn(color) {
  const m = /^#?([0-9a-f]{6})$/i.exec(color || '');
  if (!m) return '#111';
  const n = parseInt(m[1], 16);
  const lum = (0.299 * ((n >> 16) & 255) + 0.587 * ((n >> 8) & 255) + 0.114 * (n & 255)) / 255;
  return lum > 0.55 ? '#111' : '#fff';
}
