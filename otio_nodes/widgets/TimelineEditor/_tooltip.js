// A tooltip that appears quickly. The browser's own title tooltip waits about a second, which is slow for a row of
// icon buttons. The tip is added to the page body, so it shows above the expanded modal as well.

import { clamp } from './_time.js?v=966565b0';

export function createTooltip(doc = document, delay = 120) {
  let tip = null;
  let timer = 0;

  function hide() {
    clearTimeout(timer);
    timer = 0;
    if (tip) {
      tip.remove();
      tip = null;
    }
  }

  function show(target, text) {
    hide();
    tip = doc.createElement('div');
    tip.textContent = text;
    tip.setAttribute('role', 'tooltip');
    tip.style.cssText =
      'position:fixed;z-index:2147483000;pointer-events:none;max-width:280px;padding:4px 8px;border-radius:5px;' +
      'background:#0b0b0b;color:#f0f0f0;border:1px solid #3a3a3a;font:12px/1.3 system-ui,sans-serif;' +
      'box-shadow:0 4px 14px rgba(0,0,0,.5);white-space:normal;';
    doc.body.appendChild(tip);
    const view = doc.defaultView;
    const target_ = target.getBoundingClientRect();
    const size = tip.getBoundingClientRect();
    const left = clamp(target_.left + target_.width / 2 - size.width / 2, 4, (view ? view.innerWidth : 1200) - size.width - 4);
    let top = target_.top - size.height - 6;
    if (top < 4) top = target_.bottom + 6;
    tip.style.left = `${Math.round(left)}px`;
    tip.style.top = `${Math.round(top)}px`;
  }

  // Show `text` shortly after the pointer enters `node`. The text is also its accessible name.
  function attach(node, text) {
    node.setAttribute('aria-label', text);
    node.addEventListener('pointerenter', () => {
      clearTimeout(timer);
      timer = setTimeout(() => show(node, text), delay);
    });
    node.addEventListener('pointerleave', hide);
    node.addEventListener('pointerdown', hide);
  }

  return { attach, hide };
}
