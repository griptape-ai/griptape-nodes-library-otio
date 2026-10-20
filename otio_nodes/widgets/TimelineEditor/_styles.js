// Layout constants and the stylesheet for the timeline editor.

export const HEAD_WIDTH = 124;
export const RULER_HEIGHT = 26;
export const BAND_HEIGHT = 20;
export const LANE_HEIGHT = 40;
export const SHOT_LANE_HEIGHT = 52;
export const EDGE_PX = 6;
export const SNAP_PX = 8;
export const MIN_ZOOM = 0.02;
export const MAX_ZOOM = 40;

const STYLE_ID = 'otio-timeline-editor-styles';

const CSS = `
.otl-root { display:flex; flex-direction:column; gap:6px; padding:8px; box-sizing:border-box; width:100%; min-height:560px;
  background:#1a1a1a; border-radius:6px; color:#d4d4d4; font:12px/1.3 system-ui, sans-serif; user-select:none; outline:none; }
.otl-main { display:flex; flex-direction:column; gap:6px; flex:1 1 auto; min-height:0; min-width:0; }
.otl-toolbar { display:flex; flex-wrap:wrap; align-items:center; gap:6px; }
.otl-toolbar .otl-title { font-weight:600; color:#f0f0f0; margin-right:4px; max-width:220px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.otl-readout { font:11px ui-monospace, monospace; color:#9aa; padding:2px 6px; background:#252525; border-radius:4px; }
.otl-sep { width:1px; align-self:stretch; background:#333; margin:0 2px; }
.otl-btn { padding:3px 8px; background:#2c2c2c; color:#ddd; border:1px solid #3d3d3d; border-radius:4px; cursor:pointer; font:inherit; }
.otl-btn:hover:not(:disabled) { background:#383838; }
.otl-btn:disabled { opacity:.4; cursor:not-allowed; }
.otl-btn.on { background:#3b5b87; border-color:#5b86c0; color:#fff; }
.otl-zoom { width:90px; }
.otl-scroll { flex:1 1 auto; min-height:150px; position:relative; overflow:auto; background:#141414; border:1px solid #2d2d2d; border-radius:4px; }
.otl-inner { position:relative; }
.otl-row { display:flex; position:relative; }
.otl-head { position:sticky; left:0; z-index:5; flex:none; box-sizing:border-box; padding:0 8px; display:flex; align-items:center;
  background:#202020; border-right:1px solid #333; border-bottom:1px solid #2a2a2a; color:#bbb; overflow:hidden; white-space:nowrap; text-overflow:ellipsis; }
.otl-head-name { flex:1; min-width:0; overflow:hidden; text-overflow:ellipsis; }
.otl-mute { flex:none; width:20px; height:20px; padding:0; margin-left:4px; display:inline-flex; align-items:center; justify-content:center; background:transparent;
  border:0; border-radius:3px; color:#8a8a8a; cursor:pointer; }
.otl-mute:hover { background:#333; color:#eee; }
.otl-mute.on { color:#e2a93b; }
.otl-row.muted .otl-clip { opacity:.4; }
.otl-head.dim { color:#777; font-size:11px; }
.otl-lane { position:relative; flex:none; border-bottom:1px solid #232323; background:repeating-linear-gradient(90deg,#161616 0,#161616 1px,transparent 1px,transparent 100%); }
.otl-ruler { position:sticky; top:0; z-index:6; background:#1d1d1d; cursor:ew-resize; }
.otl-ruler .otl-head { z-index:7; top:0; }
.otl-tick { position:absolute; top:0; bottom:0; border-left:1px solid #3a3a3a; padding-left:3px; font:10px ui-monospace, monospace; color:#8a8a8a; pointer-events:none; display:flex; align-items:center; }
.otl-band { position:absolute; top:2px; bottom:2px; box-sizing:border-box; border-radius:3px; padding:0 6px; overflow:hidden; white-space:nowrap;
  text-overflow:ellipsis; font-size:10.5px; line-height:16px; color:#111; font-weight:600; cursor:pointer; opacity:.9; }
.otl-clip { position:absolute; top:3px; bottom:3px; box-sizing:border-box; border-radius:4px; overflow:hidden; padding:2px 7px; cursor:grab;
  border:1px solid rgba(0,0,0,.45); color:#101010; display:flex; flex-direction:column; justify-content:center; touch-action:none; }
.otl-clip.dragging { cursor:grabbing; opacity:.85; }
.otl-clip.selected { outline:2px solid #fff; outline-offset:-2px; z-index:3; }
.otl-clip.off { opacity:.4; background-image:repeating-linear-gradient(135deg,rgba(0,0,0,.25) 0 4px,transparent 4px 8px); }
.otl-clip .wave, .otl-clip .otl-wave { position:absolute; inset:2px 0; width:100%; height:calc(100% - 4px); pointer-events:none; }
.otl-clip .n, .otl-clip .d { position:relative; }
.otl-clip .n { font-weight:600; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.otl-clip .d { font-size:10px; opacity:.75; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.otl-clip .h { position:absolute; top:0; bottom:0; width:${EDGE_PX}px; cursor:ew-resize; }
.otl-clip .h.l { left:0; } .otl-clip .h.r { right:0; }
.otl-clip:hover .h { background:rgba(255,255,255,.35); }
.otl-playhead { position:absolute; top:0; bottom:0; width:0; border-left:2px solid #ff4d4d; z-index:8; pointer-events:none; }
.otl-playhead::before { content:''; position:absolute; top:0; left:-6px; border:5px solid transparent; border-top:8px solid #ff4d4d; }
.otl-snapline { position:absolute; top:0; bottom:0; width:0; border-left:2px solid #ffd24d; box-shadow:0 0 8px rgba(255,210,77,.9); z-index:7; pointer-events:none; }
.otl-details { flex:none; min-height:176px; box-sizing:border-box; display:grid; grid-template-columns:auto 1fr auto 1fr; gap:6px 8px; align-items:center; padding:8px; background:#222; border-radius:4px; }
.otl-details.empty { display:block; color:#777; }
.otl-details label { color:#999; font-size:11px; }
.otl-details input[type=checkbox] { justify-self:start; }
.otl-details input[type=text], .otl-details input[type=number], .otl-details textarea { width:100%; box-sizing:border-box; background:#161616; color:#ddd;
  border:1px solid #3a3a3a; border-radius:3px; padding:3px 5px; font:inherit; user-select:text; }
.otl-details textarea { grid-column:2 / 5; min-height:48px; resize:vertical; }
.otl-details .wide { grid-column:2 / 5; }
.otl-details .info { grid-column:1 / 5; color:#888; font-size:11px; }
.otl-empty { padding:24px; text-align:center; color:#888; }

.otl-toolbar .otl-grow { flex:1; }
.otl-viewer { flex:none; display:flex; flex-direction:column; gap:4px; min-height:0; }
.otl-screen-wrap { flex:1 1 auto; min-height:0; display:flex; justify-content:center; background:#0b0b0b; border-radius:4px; overflow:hidden; }
.otl-screen { height:100%; aspect-ratio:16 / 9; max-width:100%; container-type:size; position:relative; background:#121216; overflow:hidden; }
.otl-slate { position:absolute; inset:0; padding:4cqh 5cqw 4cqh 6cqw; display:flex; flex-direction:column; color:#eee; }
.otl-s-progress { position:absolute; left:0; right:0; bottom:0; height:1.2cqh; background:rgba(0,0,0,.55); display:none; z-index:3; }
.otl-s-progress.on { display:block; }
.otl-s-progress-fill { height:100%; width:0; background:#d6ac5c; transition:width .4s linear; }
.otl-video { position:absolute; inset:0; width:100%; height:100%; object-fit:contain; background:#000; display:none; }
.otl-screen.has-video .otl-video { display:block; }
.otl-screen.has-video .otl-s-bar, .otl-screen.has-video .otl-s-title, .otl-screen.has-video .otl-s-desc, .otl-screen.has-video .otl-s-where { display:none; }
.otl-slate { z-index:1; pointer-events:none; }
.otl-s-bar { position:absolute; left:0; top:0; bottom:0; width:1.4cqw; }
.otl-s-top { display:flex; justify-content:space-between; align-items:flex-start; gap:2cqw; min-height:5cqh; }
.otl-s-seq { font-size:max(9px, 4.4cqh); color:#d6ac5c; font-weight:600; }
.otl-s-chips { display:flex; flex-wrap:wrap; gap:1cqw; justify-content:flex-end; }
.otl-chip { font-size:max(9px, 3.6cqh); padding:.4cqh 1.2cqw; border-radius:3cqh; color:#111; font-weight:600; }
.otl-s-title { font-size:max(14px, 11cqh); font-weight:700; margin-top:2cqh; line-height:1.05; }
.otl-s-title.dim { color:#666; }
.otl-s-desc { font-size:max(10px, 5.4cqh); color:#b9b9c0; margin-top:3cqh; line-height:1.3; overflow:hidden; display:-webkit-box; -webkit-box-orient:vertical; -webkit-line-clamp:4; }
.otl-s-subs { margin-top:auto; display:flex; flex-direction:column; gap:1cqh; align-items:center; text-align:center; }
.otl-sub { font-size:max(11px, 6.2cqh); background:rgba(0,0,0,.62); padding:.8cqh 2cqw; border-radius:1cqh; max-width:92%; line-height:1.25; }
.otl-sub b { color:#d6ac5c; }
.otl-s-where { margin-top:2cqh; font:max(8px, 3.4cqh) ui-monospace, monospace; color:#7d7d86; }
.otl-transport { display:flex; align-items:center; gap:6px; }
.otl-transport .otl-time { margin-left:auto; }
.otl-play { min-width:34px; }

.otl-clip.stale { border:1px dashed rgba(255,255,255,.95); }
.otl-screen.stale::after { content:''; position:absolute; inset:0; border:2px dashed #e2a93b; pointer-events:none; z-index:2; }
.otl-s-right { display:flex; flex-direction:column; align-items:flex-end; gap:.8cqh; min-width:0; }
.otl-s-stale { display:none; padding:.5cqh 1.3cqw; border-radius:1cqh; background:rgba(0,0,0,.7); color:#e2a93b; font-size:max(9px, 3.4cqh);
  line-height:1.25; white-space:nowrap; border:1px dashed #e2a93b; }
.otl-screen.stale .otl-s-stale { display:block; }
.otl-details .media-row { grid-column:2 / 5; display:flex; gap:6px; align-items:center; }
.otl-details .media-row input { flex:1; min-width:0; }
.otl-root.otl-full .otl-details .media-row { grid-column:1 / -1; }
.otl-details .warn { grid-column:1 / -1; color:#e2a93b; font-size:11px; border:1px dashed #e2a93b; border-radius:4px; padding:4px 8px; }

/* The bar above the timeline: tools on the left, play controls in the middle, the time on the right. */
.otl-bar { flex:none; display:grid; grid-template-columns:minmax(0,1fr) auto minmax(0,1fr); align-items:center; gap:8px; }
.otl-bar-group { display:flex; align-items:center; gap:4px; min-width:0; }
.otl-bar-left { justify-content:flex-start; flex-wrap:wrap; }
.otl-bar-right { justify-content:flex-end; flex-wrap:wrap; }
.otl-ico { width:28px; height:28px; padding:0; display:inline-flex; align-items:center; justify-content:center; flex:none; }
.otl-bar .otl-sep, .otl-toolbar .otl-sep { height:18px; align-self:center; }

/* Expanded: a modal like the annotate widget's. The clip details sit on the right. */
.otl-modal-backdrop { position:fixed; inset:0; z-index:9998; background:rgba(0,0,0,.6); backdrop-filter:blur(6px); -webkit-backdrop-filter:blur(6px);
  display:flex; align-items:center; justify-content:center; }
.otl-modal { position:relative; width:90%; height:90%; background:var(--background,#1a1a1a); border:1px solid var(--border,#333); border-radius:8px;
  overflow:hidden; display:flex; flex-direction:column; box-shadow:0 10px 40px rgba(0,0,0,.5), 0 0 0 1px rgba(255,255,255,.04); }
.otl-modal-head { display:flex; align-items:center; justify-content:space-between; padding:0 16px; height:48px; flex-shrink:0;
  border-bottom:1px solid var(--border,#333); background:var(--card,#222); }
.otl-modal-title { font:600 13px system-ui, sans-serif; color:var(--foreground,#eee); letter-spacing:.01em; }
.otl-modal-close { display:flex; align-items:center; justify-content:center; width:28px; height:28px; padding:0; border:none; border-radius:6px;
  background:transparent; color:var(--muted-foreground,#999); opacity:.7; cursor:pointer; transition:opacity .15s; }
.otl-modal-close:hover { opacity:1; }
.otl-root.otl-full { flex:1 1 auto; min-height:0; width:100%; height:auto; border-radius:0; flex-direction:row; padding:10px; }
.otl-root.otl-full .otl-main { flex:1 1 auto; }
.otl-root.otl-full .otl-details { flex:none; width:340px; display:grid; grid-template-columns:auto 1fr; align-content:start; overflow:auto; min-height:0; }
.otl-root.otl-full .otl-details textarea, .otl-root.otl-full .otl-details .wide, .otl-root.otl-full .otl-details .info { grid-column:1 / -1; }
.otl-root.otl-full .otl-details textarea { min-height:120px; }
.otl-root.otl-full .otl-details.empty { display:block; }
`;

// Put the stylesheet in the page. A page that stays open while the library is reloaded still holds the stylesheet an
// older version of the widget added, so an existing tag is updated when its content differs instead of being kept.
export function ensureStyles(doc = document) {
  let style = doc.getElementById(STYLE_ID);
  if (!style) {
    style = doc.createElement('style');
    style.id = STYLE_ID;
    doc.head.appendChild(style);
  }
  if (style.textContent !== CSS) style.textContent = CSS;
}
