// TimelineEditor: a small NLE-style timeline for the shots, dialogue, SFX and audio of a script.
//
// A viewer above the timeline plays back what is under the playhead. The tools for the selected clip, the play controls
// and the time sit in one bar just above the timeline. Expand opens the editor in a modal, with the clip details on
// the right.
//
// `value` is the timeline model described in model.py. The widget edits a copy and calls onChange(model) once per
// finished edit (on pointer up, button press or field change), never while a drag is still in progress. Editing rules
// live in _ops.js, which has no DOM code.

import {
  addClip,
  clearMedia,
  deleteClip,
  deriveBands,
  editPoints,
  endOf,
  findClip,
  isLinked,
  isStale,
  moveClip,
  nextEdit,
  previousEdit,
  setMedia,
  setTrackMuted,
  siblingClip,
  snapFrame,
  snapPoints,
  splitClip,
  totalFrames,
  trimClip,
  updateClip,
} from './_ops.js?v=14318a8d';
import {
  BAND_HEIGHT,
  EDGE_PX,
  HEAD_WIDTH,
  LANE_HEIGHT,
  MAX_ZOOM,
  MIN_ZOOM,
  RULER_HEIGHT,
  SHOT_LANE_HEIGHT,
  SNAP_PX,
  ensureStyles,
} from './_styles.js?v=14318a8d';
import { clamp, formatSeconds, frameToTimecode, rulerStepFrames } from './_time.js?v=14318a8d';
import { el, readableOn } from './_dom.js?v=14318a8d';
import { createViewer } from './_viewer.js?v=14318a8d';
import { createAudio } from './_audio.js?v=14318a8d';
import { FOLDER_PATH, icon } from './_icons.js?v=14318a8d';
import { createTooltip } from './_tooltip.js?v=14318a8d';

const WIDGET_VERSION = '0.2.0';
const sameModel = (a, b) => JSON.stringify(a) === JSON.stringify(b);
const PREVIEW_KEYS = ['previews', 'preparing', 'preview_errors'];
const withoutPreviews = (model) => JSON.stringify({ ...model, previews: undefined, preparing: undefined, preview_errors: undefined });
const onlyPreviewsDiffer = (a, b) => withoutPreviews(a) === withoutPreviews(b);

export default function TimelineEditor(container, props) {
  if (container._instance?.wrapper?.isConnected) {
    container._instance.handleUpdate(props);
    return { cleanup: container._instance.cleanup, update: container._instance.handleUpdate };
  }
  ensureStyles(container.ownerDocument || document);

  let { value, onChange, disabled, height, nodeName } = props;
  const state = {
    model: value && Array.isArray(value.tracks) ? structuredClone(value) : null,
    preview: null,
    selectedId: null,
    playhead: 0,
    zoom: 0,
    snap: true,
    ripple: true,
    link: true,
    drag: null,
    snapLine: null,
    playing: false,
    looping: false,
    playPos: 0,
    lastTs: null,
    userZoomed: false,
    notice: '',
  };

  // The editor hands back what the widget sends, a little later. Until the latest message has come back, it may first
  // hand back an older one, and adopting that would pull the timeline back to where it was for a moment (a dropped clip
  // jumping back, then forward). So the values this widget has held are remembered, and an older one arriving soon
  // after a send, and while the latest send has not come back yet, is ignored. Once it has come back, whatever the node
  // sends is taken, so a reset from the node is never mistaken for an old echo.
  const STALE_ECHO_MS = 2000;
  const held = [];
  let lastSendAt = 0;
  let awaitingEcho = false;
  const remember = (model) => {
    const json = JSON.stringify(model);
    if (held[held.length - 1] !== json) held.push(json);
    if (held.length > 16) held.shift();
  };
  const markSent = () => {
    remember(state.model);
    lastSendAt = performance.now();
    awaitingEcho = true;
  };

  // The selected clip's id is kept in the timeline the widget edits, as "selected". The node's media file picker needs
  // it to know which clip to link, because a widget cannot open the editor's own file picker. It is sent to the node
  // shortly after the selection changes, and only when it has changed.
  if (state.model && state.model.selected && findClip(state.model, state.model.selected)) state.selectedId = state.model.selected;
  if (state.model) remember(state.model);
  let lastSentSelection = state.selectedId;
  let selectionTimer = 0;

  function setSelected(id) {
    state.selectedId = id || null;
    if (!state.model) return;
    state.model.selected = state.selectedId;
    clearTimeout(selectionTimer);
    selectionTimer = setTimeout(sendSelection, 250);
  }

  function sendSelection() {
    selectionTimer = 0;
    if (state.drag && state.drag.id) {
      // A drag sends its own message when it ends, with the selection in it. Sending one now would carry the clip's old
      // position, and its echo would arrive after the drop.
      selectionTimer = setTimeout(sendSelection, 250);
      return;
    }
    if (disabled || !onChange || !state.model || state.model.selected === lastSentSelection) return;
    lastSentSelection = state.model.selected ?? null;
    markSent();
    onChange(structuredClone(state.model));
  }

  const root = el('div', { class: 'otl-root nodrag nowheel', tabindex: '0', 'data-widget-version': WIDGET_VERSION });
  const toolbar = el('div', { class: 'otl-toolbar' });
  const bar = el('div', { class: 'otl-bar' });
  const tip = createTooltip(container.ownerDocument || document);
  // The pieces of the bar that change while playing, set when the bar is built.
  const transport = { play: null, loop: null, time: null, playing: null };
  const scroll = el('div', { class: 'otl-scroll' });
  const details = el('div', { class: 'otl-details empty' });
  const viewer = createViewer();
  const audio = createAudio(root.ownerDocument);
  const main = el('div', { class: 'otl-main' }, [toolbar, viewer.element, bar, scroll]);
  root.append(main, details);
  container.appendChild(root);

  const current = () => state.preview || state.model;
  const rate = () => (state.model ? Number(state.model.rate) || 24 : 24);

  // ---- sizing and zoom -------------------------------------------------------------------------------------------

  function contentFrames(model) {
    return Math.max(totalFrames(model), Math.round(rate() * 10)) + Math.round(rate() * 10);
  }

  function fitZoom() {
    const width = (scroll.clientWidth || container.clientWidth || 900) - HEAD_WIDTH - 24;
    return clamp(width / contentFrames(state.model), MIN_ZOOM, MAX_ZOOM);
  }

  function setZoom(zoom, anchorFrame, byUser = true) {
    const old = state.zoom;
    state.userZoomed = byUser;
    state.zoom = clamp(zoom, MIN_ZOOM, MAX_ZOOM);
    renderTimeline();
    syncZoomUi();
    if (anchorFrame !== undefined && old) {
      // Keep the frame under the cursor in the same place on screen.
      const offset = HEAD_WIDTH + anchorFrame * old - scroll.scrollLeft;
      scroll.scrollLeft = HEAD_WIDTH + anchorFrame * state.zoom - offset;
    }
  }

  // The slider is moved in place when the zoom changes. Rebuilding it would destroy the element being dragged.
  const zoomUi = { slider: null };
  const zoomToSlider = (zoom) => String(Math.round((Math.log(zoom / MIN_ZOOM) / Math.log(MAX_ZOOM / MIN_ZOOM)) * 100));

  function syncZoomUi() {
    if (zoomUi.slider) zoomUi.slider.value = zoomToSlider(state.zoom);
  }

  const frameX = (frame) => HEAD_WIDTH + frame * state.zoom;

  // The editor canvas can be zoomed, which scales this widget with a CSS transform. Pointer positions are in screen
  // pixels and the timeline's own units are not, so every pointer distance is divided by this scale.
  function pxScale() {
    const inner = scroll.firstChild;
    return inner && inner.offsetWidth ? inner.getBoundingClientRect().width / inner.offsetWidth : 1;
  }

  function eventFrame(event) {
    const inner = scroll.firstChild;
    const rect = inner.getBoundingClientRect();
    return Math.round(((event.clientX - rect.left) / pxScale() - HEAD_WIDTH) / state.zoom);
  }

  // Follow the pointer on the document for the length of a drag. The timeline is redrawn while dragging, so the
  // element that was pressed may no longer exist, and a listener on it would be lost.
  let stopTracking = null;

  function trackPointer(onMove, onUp, onCancel = onUp) {
    const doc = root.ownerDocument;
    const end = () => {
      doc.removeEventListener('pointermove', move);
      doc.removeEventListener('pointerup', up);
      doc.removeEventListener('pointercancel', cancel);
      stopTracking = null;
    };
    const move = (event) => onMove(event);
    const up = (event) => {
      end();
      onUp(event);
    };
    const cancel = (event) => {
      end();
      onCancel(event);
    };
    doc.addEventListener('pointermove', move);
    doc.addEventListener('pointerup', up);
    doc.addEventListener('pointercancel', cancel);
    stopTracking = end;
  }

  // ---- committing edits --------------------------------------------------------------------------------------------

  function commit(next) {
    if (!next || disabled) return false;
    state.model = next;
    state.preview = null;
    if (state.selectedId && !findClip(next, state.selectedId)) state.selectedId = null;
    state.model.selected = state.selectedId; // an edit carries the current selection, so it needs no message of its own
    lastSentSelection = state.selectedId;
    clearTimeout(selectionTimer);
    markSent();
    if (onChange) onChange(structuredClone(next));
    renderAll();
    return true;
  }

  // Reloading throws every edit away, so it asks first, with the browser's own confirm dialog. The node does the
  // reload: the request travels in the value, and the node answers with the timeline from its input.
  function actionReload() {
    if (!state.model || disabled) return;
    const view = root.ownerDocument.defaultView;
    const question = 'Reload the timeline from the node input?\n\nEvery edit made in this editor (timing, names, linked media) will be lost.';
    if (!view.confirm(question)) return;
    if (onChange) onChange({ ...structuredClone(state.model), reload: Date.now() });
  }

  function selected() {
    return state.selectedId && state.model ? findClip(state.model, state.selectedId) : null;
  }

  const opts = () => ({ ripple: state.ripple, link: state.link });

  // ---- actions -----------------------------------------------------------------------------------------------------

  function actionSplit() {
    const found = selected();
    if (found) commit(splitClip(state.model, found.clip.id, state.playhead));
  }

  function actionDelete() {
    const found = selected();
    if (found) commit(deleteClip(state.model, found.clip.id, opts()));
  }

  function actionAdd(role) {
    const result = addClip(state.model, role, state.playhead, 0);
    if (result && commit(result.model)) {
      setSelected(result.id);
      renderAll();
    }
  }

  function toggleMute(track) {
    const next = setTrackMuted(state.model, track.id, !track.muted);
    if (next) commit(next);
    updateViewer();
  }

  function actionNudge(frames) {
    const found = selected();
    if (found) commit(moveClip(state.model, found.clip.id, found.clip.start + frames, opts()));
  }

  // ---- toolbar -----------------------------------------------------------------------------------------------------

  // An icon button with a quick tooltip. `on` shows a toggle as switched on.
  function iconButton(name, tipText, onClick, { on = false, off = false } = {}) {
    const node = el('button', { class: `otl-btn otl-ico${on ? ' on' : ''}`, type: 'button', disabled: off, onclick: onClick });
    node.appendChild(icon(name, 16));
    tip.attach(node, tipText);
    return node;
  }

  const divider = () => el('span', { class: 'otl-sep' });

  // The top row: the title and Expand.
  function renderHeader() {
    toolbar.replaceChildren();
    if (!state.model) return;
    const full = isFull();
    toolbar.append(
      el('span', { class: 'otl-title', text: state.model.title || 'Timeline' }),
      el('span', { class: 'otl-grow' }),
      iconButton(full ? 'contract' : 'expand', full ? 'Close the modal (Esc)' : 'Expand to a modal, with the clip details on the right (F)', toggleFullscreen, { on: full }),
    );
  }

  // The bar above the timeline: tools on the left, play controls in the middle, the time on the right.
  function renderBar() {
    tip.hide();
    bar.replaceChildren();
    if (!state.model) return;
    const hasSelection = !!selected();
    const left = el('div', { class: 'otl-bar-group otl-bar-left' }, [
      iconButton('split', 'Split the selected clip at the playhead (S)', actionSplit, { off: disabled || !hasSelection }),
      iconButton('delete', 'Delete the selected clip (Delete)', actionDelete, { off: disabled || !hasSelection }),
      divider(),
      iconButton('sfx', 'Add a sound effect clip at the playhead', () => actionAdd('sfx'), { off: disabled }),
      iconButton('audio', 'Add an audio clip at the playhead', () => actionAdd('audio'), { off: disabled }),
      divider(),
      iconButton('snap', 'Snap to the playhead and to the edges of other clips', () => { state.snap = !state.snap; renderBar(); }, { on: state.snap }),
      iconButton('ripple', 'Ripple: a shot that gets longer or shorter moves everything after it', () => { state.ripple = !state.ripple; renderBar(); }, { on: state.ripple }),
      iconButton('link', 'Link: dialogue moves and is deleted with its shot', () => { state.link = !state.link; renderBar(); }, { on: state.link }),
      divider(),
      iconButton('reload', 'Reload the timeline from the node input, discarding every edit', actionReload, { off: disabled }),
    ]);

    transport.playing = null;
    transport.play = iconButton('play', 'Play or pause (Space)', () => (state.playing ? pause() : play()));
    transport.loop = iconButton('loop', 'Loop', () => {
      state.looping = !state.looping;
      updateTransport();
    });
    const middle = el('div', { class: 'otl-bar-group otl-bar-middle' }, [
      iconButton('start', 'Go to the start (Home)', () => seek(0)),
      iconButton('stepBack', 'Back one frame (←)', () => seek(state.playhead - 1)),
      transport.play,
      iconButton('stepForward', 'Forward one frame (→)', () => seek(state.playhead + 1)),
      iconButton('end', 'Go to the end (End)', () => seek(Math.max(0, totalFrames(state.model) - 1))),
      transport.loop,
    ]);

    transport.time = el('span', { class: 'otl-readout otl-time' });
    tip.attach(transport.time, 'Playhead time, and the length of the whole timeline');
    const zoomSlider = el('input', {
      class: 'otl-zoom',
      type: 'range',
      min: '0',
      max: '100',
      value: zoomToSlider(state.zoom),
      oninput: (e) => setZoom(MIN_ZOOM * (MAX_ZOOM / MIN_ZOOM) ** (Number(e.target.value) / 100), state.playhead),
    });
    tip.attach(zoomSlider, 'Zoom the timeline');
    zoomUi.slider = zoomSlider;
    const right = el('div', { class: 'otl-bar-group otl-bar-right' }, [
      iconButton('zoomOut', 'Zoom out (-)', () => setZoom(state.zoom / 1.4, state.playhead)),
      zoomSlider,
      iconButton('zoomIn', 'Zoom in (+)', () => setZoom(state.zoom * 1.4, state.playhead)),
      iconButton('fit', 'Fit the whole timeline', () => {
        setZoom(fitZoom(), undefined, false);
        scroll.scrollLeft = 0;
      }),
      divider(),
      transport.time,
    ]);
    bar.append(left, middle, right);
    updateTransport();
  }

  // Refresh the parts of the bar that change while playing, without rebuilding it.
  function updateTransport() {
    if (!transport.play || !state.model) return;
    if (transport.playing !== state.playing) {
      transport.play.replaceChildren(icon(state.playing ? 'pause' : 'play', 16));
      transport.play.classList.toggle('on', state.playing);
      transport.playing = state.playing;
    }
    transport.loop.classList.toggle('on', state.looping);
    const total = totalFrames(state.model);
    transport.time.textContent = `${frameToTimecode(state.playhead, rate())} / ${frameToTimecode(total, rate())}`;
  }

  function renderToolbar() {
    renderHeader();
    renderBar();
  }

  // ---- timeline ----------------------------------------------------------------------------------------------------

  function rulerLabel(frame, step) {
    const fps = Math.round(rate());
    const seconds = Math.floor(frame / fps);
    const base = `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`;
    return step < fps ? `${base}:${String(frame % fps).padStart(2, '0')}` : base;
  }

  function clipElement(clip, track) {
    const width = Math.max(2, clip.duration * state.zoom);
    const isShot = track.role === 'shots';
    const dragging = state.drag && state.drag.id === clip.id && state.drag.moved;
    const node = el(
      'div',
      {
        class: `otl-clip${clip.id === state.selectedId ? ' selected' : ''}${clip.enabled === false ? ' off' : ''}${dragging ? ' dragging' : ''}${isStale(clip) ? ' stale' : ''}`,
        'data-clip': clip.id,
        title: `${clip.name}\n${clip.description || ''}\n${frameToTimecode(clip.start, rate())} + ${clip.duration} frames${
          isStale(clip) ? '\nThe slate file still shows the old text. A new one is made when the node runs.' : ''
        }`.trim(),
        style: `left:${clip.start * state.zoom}px; width:${width}px; background:${clip.color || '#8a8a8a'}; color:${readableOn(clip.color)};`,
      },
      [el('span', { class: 'h l', 'data-edge': 'start' }), el('span', { class: 'h r', 'data-edge': 'end' })],
    );
    if (width > 36) {
      node.append(el('span', { class: 'n', text: clip.name }));
      if (isShot && clip.description && width > 90) node.append(el('span', { class: 'd', text: clip.description }));
      else if (width > 60) node.append(el('span', { class: 'd', text: formatSeconds(clip.duration, rate()) }));
    }
    node.addEventListener('pointerdown', (event) => onClipPointerDown(event, clip));
    return node;
  }

  function laneRow(track, laneWidth) {
    const isShot = track.role === 'shots';
    const rowHeight = isShot ? SHOT_LANE_HEIGHT : LANE_HEIGHT;
    const lane = el('div', { class: 'otl-lane', style: `width:${laneWidth}px; height:${rowHeight}px;` });
    for (const clip of track.clips) lane.appendChild(clipElement(clip, track));
    const head = el('div', { class: 'otl-head', style: `width:${HEAD_WIDTH}px; height:${rowHeight}px;` }, [
      el('span', { class: 'otl-head-name', title: track.name, text: track.name }),
    ]);
    if (track.kind === 'audio') {
      // Mute silences the track in playback only. It is not saved to the OTIO.
      const mute = el('button', { class: `otl-mute${track.muted ? ' on' : ''}`, type: 'button', onclick: () => toggleMute(track) });
      mute.appendChild(icon(track.muted ? 'volumeOff' : 'volume', 14));
      tip.attach(mute, track.muted ? 'Unmute this track' : 'Mute this track in playback');
      head.appendChild(mute);
    }
    return el('div', { class: `otl-row${track.muted ? ' muted' : ''}` }, [head, lane]);
  }

  function bandRow(label, bands, laneWidth) {
    const lane = el('div', { class: 'otl-lane otl-band-lane', style: `width:${laneWidth}px; height:${BAND_HEIGHT}px;` });
    for (const band of bands) {
      lane.appendChild(
        el('div', {
          class: 'otl-band',
          title: band.label,
          text: band.label,
          style: `left:${band.start * state.zoom}px; width:${Math.max(2, (band.end - band.start) * state.zoom - 1)}px; background:${band.color};`,
          onpointerdown: () => setPlayhead(band.start),
        }),
      );
    }
    return el('div', { class: 'otl-row' }, [
      el('div', { class: 'otl-head dim', style: `width:${HEAD_WIDTH}px; height:${BAND_HEIGHT}px;`, text: label }),
      lane,
    ]);
  }

  function rulerRow(laneWidth, frames) {
    const lane = el('div', { class: 'otl-lane', style: `width:${laneWidth}px; height:${RULER_HEIGHT}px;` });
    const step = rulerStepFrames(state.zoom, rate());
    for (let frame = 0; frame <= frames; frame += step) {
      lane.appendChild(el('div', { class: 'otl-tick', style: `left:${frame * state.zoom}px;`, text: rulerLabel(frame, step) }));
    }
    const row = el('div', { class: 'otl-row otl-ruler' }, [
      el('div', { class: 'otl-head dim', style: `width:${HEAD_WIDTH}px; height:${RULER_HEIGHT}px;`, text: 'Timeline' }),
      lane,
    ]);
    row.addEventListener('pointerdown', (event) => {
      if (event.target.closest('.otl-head') || event.button !== 0) return;
      state.drag = { type: 'scrub' };
      setPlayhead(eventFrame(event));
      trackPointer(
        (move) => scrubTo(move),
        () => {
          state.drag = null;
        },
      );
    });
    return row;
  }

  function setPlayhead(frame) {
    state.playhead = clamp(Math.round(frame), 0, contentFrames(current()));
    state.playPos = state.playhead;
    positionOverlays();
    updateViewer();
  }

  function seek(frame) {
    setPlayhead(frame);
    followPlayhead();
  }

  // ---- viewer and playback -----------------------------------------------------------------------------------------

  function updateViewer() {
    if (!state.model) return;
    viewer.update(current(), state.playhead, { rate: rate(), playing: state.playing });
    audio.sync(current(), state.playhead, rate(), state.playing);
    updateTransport();
  }

  let raf = 0;

  function play() {
    if (!state.model || state.playing) return;
    if (state.playhead >= totalFrames(state.model) - 1) setPlayhead(0);
    state.playing = true;
    state.lastTs = null;
    state.playPos = state.playhead;
    raf = requestAnimationFrame(tick);
    updateViewer();
  }

  function pause() {
    state.playing = false;
    cancelAnimationFrame(raf);
    updateViewer();
  }

  function tick(ts) {
    if (!state.playing) return;
    if (state.lastTs !== null) state.playPos += ((ts - state.lastTs) / 1000) * rate();
    state.lastTs = ts;
    const total = totalFrames(state.model);
    if (state.playPos >= total) {
      if (state.looping && total > 0) {
        state.playPos = 0;
      } else {
        state.playhead = Math.max(0, total - 1);
        positionOverlays();
        pause();
        return;
      }
    }
    state.playhead = Math.floor(state.playPos);
    positionOverlays();
    followPlayhead();
    updateViewer();
    raf = requestAnimationFrame(tick);
  }

  // Up and down arrows, as in Premiere and Resolve. With a clip selected they select the previous or next clip on its
  // track and put the playhead at its start. With nothing selected they jump the playhead to the previous or next edit
  // point, which is wherever any clip starts or ends.
  function jumpClip(direction) {
    if (!state.model) return;
    const found = selected();
    if (found) {
      const next = siblingClip(state.model, found.clip.id, direction);
      if (!next) return;
      setSelected(next.id);
      seek(next.start);
      renderAll();
      return;
    }
    const points = editPoints(state.model);
    const target = direction < 0 ? previousEdit(points, state.playhead) : nextEdit(points, state.playhead);
    if (target !== null) seek(target);
  }

  // Scroll the timeline sideways when the playhead leaves the visible part.
  function followPlayhead() {
    const x = frameX(state.playhead);
    const visible = scroll.clientWidth;
    if (!visible) return;
    if (x < scroll.scrollLeft + HEAD_WIDTH || x > scroll.scrollLeft + visible - 30) {
      scroll.scrollLeft = Math.max(0, x - HEAD_WIDTH - 40);
    }
  }

  // ---- layout and the expanded modal ---------------------------------------------------------------------------------------

  let modal = null;
  const isFull = () => modal !== null;

  // The timeline takes whatever height is left, so a taller node gives it more room. The viewer gets a share of the
  // space once the toolbar, the details panel and a minimum timeline height are accounted for.
  const MIN_TIMELINE_PX = 190;

  function layout() {
    const full = isFull();
    root.style.height = !full && height && height > 0 ? `${height}px` : '';
    const view = root.ownerDocument.defaultView;
    const total = full ? root.clientHeight || (view ? view.innerHeight : 900) : height && height > 0 ? height : 600;
    const chrome = toolbar.offsetHeight + bar.offsetHeight + (full ? 0 : details.offsetHeight) + 16 + 24;
    const room = total - chrome - MIN_TIMELINE_PX;
    const share = Math.round(total * (full ? 0.5 : 0.4));
    viewer.element.style.height = `${clamp(Math.min(room, share), 130, full ? 800 : 440)}px`;
  }

  function afterModeChange() {
    layout();
    if (!state.userZoomed && state.model) state.zoom = fitZoom();
    renderAll();
    root.focus({ preventScroll: true });
  }

  // Expanding moves the editor into a modal on the page body: a dimmed backdrop with a centred dialog, like the
  // annotate widget. The editor is put back where it was when the modal closes.
  function buildModal() {
    const closeButton = el('button', {
      class: 'otl-modal-close',
      type: 'button',
      title: 'Close (Esc)',
      'aria-label': 'Close',
      onclick: leaveFull,
    });
    closeButton.appendChild(icon('close', 16));
    const title = state.model && state.model.title ? `${state.model.title}  ·  Timeline Editor` : 'Timeline Editor';
    const dialog = el('div', { class: 'otl-modal', role: 'dialog', 'aria-label': 'Timeline editor' }, [
      el('div', { class: 'otl-modal-head' }, [el('span', { class: 'otl-modal-title', text: title }), closeButton]),
    ]);
    const backdrop = el('div', { class: 'otl-modal-backdrop' }, [dialog]);
    backdrop.addEventListener('pointerdown', (event) => {
      if (event.target === backdrop) leaveFull();
    });
    return { backdrop, dialog };
  }

  function onModalKey(event) {
    if (event.key !== 'Escape') return;
    event.preventDefault();
    event.stopPropagation();
    if (state.drag && state.drag.id) onDragCancel();
    else leaveFull();
  }

  function enterFull() {
    if (isFull() || !state.model) return;
    const { backdrop, dialog } = buildModal();
    dialog.appendChild(root);
    root.ownerDocument.body.appendChild(backdrop);
    modal = backdrop;
    root.classList.add('otl-full');
    root.ownerDocument.addEventListener('keydown', onModalKey, true);
    afterModeChange();
  }

  function leaveFull() {
    if (!modal) return;
    root.ownerDocument.removeEventListener('keydown', onModalKey, true);
    root.classList.remove('otl-full');
    container.appendChild(root);
    modal.remove();
    modal = null;
    afterModeChange();
  }

  function toggleFullscreen() {
    if (isFull()) leaveFull();
    else enterFull();
  }

  let lastSize = '';
  const observer = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(() => {
    // The editor gives the container a fixed height from the node's height and does not call update() when only the
    // height changes (it only does so when the value changes), so read the height from the container itself.
    if (container.style.height && container.clientHeight > 0) height = container.clientHeight;
    const size = `${root.clientWidth}x${root.clientHeight}x${height}`;
    if (size === lastSize) return;
    lastSize = size;
    requestAnimationFrame(() => {
      layout();
      if (!state.userZoomed && state.model) {
        state.zoom = fitZoom();
        renderTimeline();
        syncZoomUi();
      }
    });
  });
  if (observer) {
    observer.observe(root);
    observer.observe(container);
  }

  // The track names are a sticky column that the timeline scrolls under. A line scrolled out of the lanes is hidden, or
  // it would show through over the names.
  const underNames = (frame) => frameX(frame) - scroll.scrollLeft < HEAD_WIDTH;

  function positionOverlays() {
    const inner = scroll.firstChild;
    if (!inner) return;
    const playhead = inner.querySelector('.otl-playhead');
    playhead.style.left = `${frameX(state.playhead)}px`;
    playhead.style.display = underNames(state.playhead) ? 'none' : '';
    const line = inner.querySelector('.otl-snapline');
    if (state.snapLine === null || underNames(state.snapLine)) line.style.display = 'none';
    else {
      line.style.display = 'block';
      line.style.left = `${frameX(state.snapLine)}px`;
    }
  }

  // Dragging on the ruler follows the pointer, but stops at the edges of the lanes. Past an edge the timeline scrolls
  // that way, so the playhead can go on to earlier or later frames instead of vanishing under the track names.
  function scrubTo(event) {
    const rect = scroll.getBoundingClientRect();
    const scale = pxScale();
    const laneLeft = rect.left + HEAD_WIDTH * scale;
    if (event.clientX < laneLeft) scroll.scrollLeft -= Math.min(60, (laneLeft - event.clientX) / scale / 2 + 4);
    else if (event.clientX > rect.right) scroll.scrollLeft += Math.min(60, (event.clientX - rect.right) / scale / 2 + 4);
    setPlayhead(eventFrame({ clientX: clamp(event.clientX, laneLeft, rect.right) }));
  }

  function renderTimeline() {
    const view = current();
    const left = scroll.scrollLeft;
    const top = scroll.scrollTop;
    scroll.replaceChildren();
    if (!view) return;
    if (!state.zoom) state.zoom = fitZoom();
    const frames = contentFrames(view);
    const laneWidth = Math.round(frames * state.zoom);
    const bands = deriveBands(view);
    const inner = el('div', { class: 'otl-inner', style: `width:${HEAD_WIDTH + laneWidth}px;` });
    inner.append(rulerRow(laneWidth, frames));
    if (bands.sequences.length) {
      inner.append(bandRow('Sequences', bands.sequences, laneWidth), bandRow('Scenes', bands.scenes, laneWidth));
    }
    for (const track of view.tracks) inner.append(laneRow(track, laneWidth));
    inner.append(el('div', { class: 'otl-playhead' }), el('div', { class: 'otl-snapline', style: 'display:none' }));
    scroll.appendChild(inner);
    scroll.scrollLeft = left;
    scroll.scrollTop = top;
    positionOverlays();
  }

  // ---- details panel -----------------------------------------------------------------------------------------------

  // Open the editor's own file picker for the node's Media File field. A widget has no way to open it directly, but
  // the field is on the same page and the editor tags it with the node and parameter name, so the widget presses its
  // folder button. If the editor's markup is not what is expected, say so and point at the node's field.
  function findPickerButton() {
    const doc = root.ownerDocument;
    for (const field of doc.querySelectorAll('[data-parameter-name="media_file"]')) {
      if (nodeName && field.getAttribute('data-param-node') !== nodeName) continue;
      if (!field.offsetParent) continue;
      const buttons = [...field.querySelectorAll('button')];
      const folder = buttons.find((b) => [...b.querySelectorAll('svg path')].some((p) => p.getAttribute('d') === FOLDER_PATH));
      const found = folder || (buttons.length === 1 ? buttons[0] : null);
      if (found) return found;
    }
    return null;
  }

  function showNotice(text) {
    state.notice = text;
    renderDetails();
    setTimeout(() => {
      if (state.notice === text) {
        state.notice = '';
        renderDetails();
      }
    }, 6000);
  }

  // The expanded window sits above the editor's own dialogs, so the picker would open behind it. Hide the window while
  // the picker is up and bring it back when the dialog it opened is gone. The editor's markup is not known here, so a
  // dialog is anything new and fixed-position (or marked as a dialog) that appears after the press. If nothing
  // appears within a moment, the picker is the system's own dialog and the window comes straight back.
  function pressPicker(button) {
    if (!isFull() || !modal) {
      button.click();
      return;
    }
    const doc = root.ownerDocument;
    const shown = new Set();
    const isDialog = (node) =>
      node.nodeType === 1 &&
      !modal.contains(node) &&
      !root.contains(node) &&
      (node.matches('[role="dialog"], [aria-modal="true"], dialog') ||
        !!node.querySelector('[role="dialog"], [aria-modal="true"]') ||
        doc.defaultView.getComputedStyle(node).position === 'fixed');
    const watcher = new doc.defaultView.MutationObserver((records) => {
      for (const record of records) for (const node of record.addedNodes) if (isDialog(node)) shown.add(node);
    });
    const started = performance.now();
    const finish = () => {
      watcher.disconnect();
      clearInterval(poll);
      modal.style.visibility = '';
      takeFocus(); // the picker took the focus away
    };
    const poll = setInterval(() => {
      for (const node of shown) if (!node.isConnected) shown.delete(node);
      const waited = performance.now() - started;
      if (!modal.isConnected || (waited > 1500 && shown.size === 0) || waited > 300000) finish();
    }, 250);
    watcher.observe(doc.body, { childList: true, subtree: true });
    modal.style.visibility = 'hidden';
    button.click();
  }

  function browseMedia() {
    if (!selected() || disabled) return;
    clearTimeout(selectionTimer);
    sendSelection(); // the node has to know which clip is selected before a file is chosen
    const button = findPickerButton();
    if (button) pressPicker(button);
    else showNotice('The file picker could not be opened from here. Use "Media File" on the node, or paste a path.');
  }

  function renderDetails() {
    details.replaceChildren();
    const found = selected();
    if (!found) {
      details.className = 'otl-details empty';
      details.textContent = state.model ? 'Select a clip to see and edit its details.' : '';
      layout();
      return;
    }
    details.className = 'otl-details';
    const { clip, track } = found;
    const seconds = (frames) => Number((frames / rate()).toFixed(3));
    const apply = (patch) => commit(updateClip(state.model, clip.id, patch));
    const meta = clip.meta || {};

    const nameInput = el('input', { type: 'text', value: clip.name, disabled, onchange: (e) => apply({ name: e.target.value }) });
    const durationInput = el('input', {
      type: 'number', min: '0.04', step: '0.05', value: String(seconds(clip.duration)), disabled,
      onchange: (e) => apply({ duration: Math.max(1, Math.round(Number(e.target.value) * rate())) }),
    });
    const startInput = el('input', {
      type: 'number', min: '0', step: '0.05', value: String(seconds(clip.start)), disabled,
      onchange: (e) => apply({ start: Math.max(0, Math.round(Number(e.target.value) * rate())) }),
    });
    const description = el('textarea', { disabled, onchange: (e) => apply({ description: e.target.value }) });
    description.value = clip.description || '';
    const enabled = el('input', { type: 'checkbox', disabled, onchange: (e) => apply({ enabled: e.target.checked }) });
    enabled.checked = clip.enabled !== false;
    const color = el('input', { type: 'color', value: /^#[0-9a-f]{6}$/i.test(clip.color) ? clip.color : '#888888', disabled, onchange: (e) => apply({ color: e.target.value }) });

    // Media: the file this clip shows or plays. Empty means the placeholder slate, which is made when the timeline is
    // saved. A path, a file:// address or a project macro links real media. The file is checked and its length measured
    // when the node runs, because this panel cannot read files.
    const linked = isLinked(clip.media);
    const fileName = (url) => String(url || '').split(/[\\/]/).pop();
    const mediaInput = el('input', {
      type: 'text',
      value: linked ? clip.media.url : '',
      placeholder: clip.media ? `Placeholder slate (${fileName(clip.media.url)})` : 'Placeholder slate. Paste a file path to link real media',
      disabled,
      onchange: (e) => {
        const text = e.target.value.trim();
        commit(text ? setMedia(state.model, clip.id, text, linked ? clip.media.start : 0) : clearMedia(state.model, clip.id));
      },
    });
    const sourceStart = linked
      ? el('input', {
          type: 'number', min: '0', step: '0.05', value: String(seconds(clip.media.start)), disabled,
          onchange: (e) => commit(setMedia(state.model, clip.id, clip.media.url, Math.max(0, Math.round(Number(e.target.value) * rate())))),
        })
      : null;
    const usePlaceholder = linked
      ? el('button', { class: 'otl-btn', type: 'button', disabled, text: 'Use placeholder', onclick: () => commit(clearMedia(state.model, clip.id)) })
      : null;

    const infoParts = [`Track: ${track.name}`, `${frameToTimecode(clip.start, rate())} to ${frameToTimecode(endOf(clip), rate())}`];
    if (meta.heading) infoParts.push(meta.heading);
    if (meta.line_start) infoParts.push(`script lines ${meta.line_start}-${meta.line_end}`);
    if (meta.notes && meta.notes.length) infoParts.push(`notes: ${meta.notes.join('; ')}`);

    details.append(
      el('label', { text: 'Name' }), nameInput,
      el('label', { text: 'Duration (s)' }), durationInput,
      el('label', { text: 'Description' }), description,
      el('label', { text: 'Media' }),
      el('div', { class: 'media-row' }, [
        mediaInput,
        iconButton('folder', "Choose a media file with the editor's file picker for this clip", browseMedia, { off: disabled }),
      ]),
      ...(state.notice ? [el('div', { class: 'warn', text: state.notice })] : []),
      ...(isStale(clip)
        ? [el('div', { class: 'warn', text: 'The slate file on disk still shows the old text. The preview shows the new text. A new slate is made when the node runs.' })]
        : []),
      ...(linked
        ? [el('label', { text: 'Source start (s)' }), sourceStart, usePlaceholder]
        : []),
      el('div', {
        class: 'info',
        text: `${linked ? 'To use a different file' : 'To replace the placeholder'}, paste a path, a file:// address or a project path such as {inputs}/plate.mov, or choose a file with "Media File" on the node${isFull() ? ' (close this window first)' : ''}. It is checked and measured when the node runs.`,
      }),
      el('label', { text: 'Start (s)' }), startInput,
      el('label', { text: 'Color' }), color,
      el('label', { text: 'Enabled' }), enabled,
      el('div', { class: 'info', text: infoParts.join('   |   ') }),
    );
    layout();
  }

  function renderAll() {
    viewer.element.style.display = '';
    renderToolbar();
    renderTimeline();
    renderDetails();
    updateViewer();
  }

  // ---- dragging ----------------------------------------------------------------------------------------------------

  function onClipPointerDown(event, clip) {
    if (event.button !== 0) return;
    event.stopPropagation();
    root.focus({ preventScroll: true });
    const selectionChanged = state.selectedId !== clip.id;
    setSelected(clip.id);
    const edge = event.target.dataset ? event.target.dataset.edge : undefined;
    if (selectionChanged) {
      renderToolbar();
      renderDetails();
    }
    if (disabled) {
      seek(clip.start);
      renderTimeline();
      return;
    }
    const type = edge === 'start' ? 'trimStart' : edge === 'end' ? 'trimEnd' : 'move';
    state.drag = { type, id: clip.id, scale: pxScale(), originX: event.clientX, start: clip.start, end: endOf(clip), moved: false, pointerId: event.pointerId };
    trackPointer(onDragMove, onDragEnd, onDragCancel);
    renderTimeline();
  }

  function onDragMove(event) {
    const drag = state.drag;
    if (!drag || !drag.id) return;
    const delta = Math.round((event.clientX - drag.originX) / drag.scale / state.zoom);
    if (delta !== 0) drag.moved = true;
    if (!drag.moved) return;
    const base = state.model;
    const exclude = new Set([drag.id]);
    const points = state.snap ? snapPoints(base, exclude, state.playhead) : [];
    const threshold = Math.max(1, Math.round(SNAP_PX / drag.scale / state.zoom));
    let snappedTo = null;
    const snapped = (frame) => {
      const result = state.snap ? snapFrame(frame, points, threshold) : frame;
      if (result !== frame) snappedTo = result;
      return result;
    };

    let next = null;
    if (drag.type === 'move') {
      const startCandidate = drag.start + delta;
      const endCandidate = drag.end + delta;
      const a = snapped(startCandidate);
      const aMoved = Math.abs(a - startCandidate);
      snappedTo = null;
      const b = snapped(endCandidate) - (drag.end - drag.start);
      const bMoved = Math.abs(b - startCandidate);
      const useStart = aMoved !== 0 && (bMoved === 0 || aMoved <= bMoved);
      const newStart = useStart ? a : b;
      snappedTo = useStart ? a : bMoved ? b + (drag.end - drag.start) : null;
      next = moveClip(base, drag.id, newStart, opts());
    } else if (drag.type === 'trimEnd') {
      next = trimClip(base, drag.id, 'end', snapped(drag.end + delta), opts());
    } else {
      next = trimClip(base, drag.id, 'start', snapped(drag.start + delta), opts());
    }
    if (next) {
      state.preview = next;
      state.snapLine = snappedTo;
    }
    renderTimeline();
    updateViewer();
  }

  function onDragEnd() {
    const drag = state.drag;
    state.snapLine = null;
    state.drag = null;
    if (drag && drag.moved && state.preview) commit(state.preview);
    else {
      state.preview = null;
      // A click that did not drag puts the playhead at the start of the clip, so the viewer shows it.
      const clicked = drag && drag.id ? findClip(state.model, drag.id) : null;
      if (clicked) seek(clicked.clip.start);
      renderAll();
    }
  }

  function onDragCancel() {
    if (stopTracking) stopTracking();
    state.snapLine = null;
    state.drag = null;
    state.preview = null;
    renderAll();
  }

  // ---- keyboard and wheel ------------------------------------------------------------------------------------------

  // The keys only work while the editor has focus. Pressing anywhere in it gives it focus, and a button that was pressed
  // hands focus back, because the toolbar is rebuilt and the button would take the focus with it.
  const typing = (node) => !!node && (node.tagName === 'INPUT' || node.tagName === 'TEXTAREA' || node.tagName === 'SELECT');
  const takeFocus = () => {
    if (!typing(root.ownerDocument.activeElement)) root.focus({ preventScroll: true });
  };
  root.addEventListener(
    'pointerdown',
    (event) => {
      if (!typing(event.target)) root.focus({ preventScroll: true });
    },
    true,
  );
  root.addEventListener('click', () => setTimeout(takeFocus, 0));

  root.addEventListener('keydown', (event) => {
    const tag = event.target.tagName;
    if (tag === 'INPUT' || tag === 'TEXTAREA') return;
    const step = event.shiftKey ? 10 : 1;
    const handled = (fn) => {
      event.preventDefault();
      event.stopPropagation();
      fn();
    };
    switch (event.key) {
      case ' ': return handled(() => (state.playing ? pause() : play()));
      case 'ArrowUp': return handled(() => jumpClip(-1));
      case 'ArrowDown': return handled(() => jumpClip(1));
      case 'Home': return handled(() => seek(0));
      case 'End': return handled(() => seek(Math.max(0, totalFrames(state.model) - 1)));
      case 'f':
      case 'F': return handled(toggleFullscreen);
      case 'Delete':
      case 'Backspace': return handled(actionDelete);
      case 's':
      case 'S': return handled(actionSplit);
      case 'ArrowLeft': return handled(() => (selected() ? actionNudge(-step) : setPlayhead(state.playhead - step)));
      case 'ArrowRight': return handled(() => (selected() ? actionNudge(step) : setPlayhead(state.playhead + step)));
      case 'Escape':
        return handled(() => {
          if (state.drag && state.drag.id) onDragCancel();
          else if (isFull()) leaveFull();
          else { setSelected(null); renderAll(); }
        });
      case '+':
      case '=': return handled(() => setZoom(state.zoom * 1.4, state.playhead));
      case '-': return handled(() => setZoom(state.zoom / 1.4, state.playhead));
      default:
    }
  });

  // The scroll wheel works as in Nuke Studio and Hiero: the wheel zooms around the cursor, Option and the wheel pans
  // sideways, and Shift and the wheel scrolls the lanes up and down. A trackpad's sideways swipe still pans. Ctrl or
  // Cmd and the wheel also zoom, because that is how a trackpad pinch arrives.
  scroll.addEventListener(
    'wheel',
    (event) => {
      if (!state.model) return;
      const unit = event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? scroll.clientWidth : 1;
      const amount = (event.deltaY || event.deltaX) * unit;
      if (event.altKey) {
        event.preventDefault();
        scroll.scrollLeft += amount;
      } else if (event.shiftKey) {
        event.preventDefault();
        scroll.scrollTop += amount;
      } else if (event.ctrlKey || event.metaKey || Math.abs(event.deltaY) >= Math.abs(event.deltaX)) {
        event.preventDefault();
        setZoom(state.zoom * clamp(Math.exp(-amount * 0.0015), 0.7, 1.4), eventFrame(event));
      }
    },
    { passive: false },
  );

  scroll.addEventListener('scroll', positionOverlays);

  scroll.addEventListener('pointerdown', (event) => {
    // empty track space deselects. The ruler and the bands move the playhead and keep the selection
    const onTrack = event.target.classList.contains('otl-lane') && !event.target.closest('.otl-ruler, .otl-band-lane');
    if (event.target === scroll || onTrack) {
      setSelected(null);
      renderAll();
    }
  });

  // ---- lifecycle ---------------------------------------------------------------------------------------------------

  function renderEmpty() {
    toolbar.replaceChildren();
    bar.replaceChildren();
    viewer.element.style.display = 'none';
    scroll.replaceChildren(el('div', { class: 'otl-empty', text: 'No timeline yet. Connect a timeline from Script to Timeline.' }));
    details.className = 'otl-details empty';
    details.textContent = '';
  }

  function handleUpdate(newProps) {
    const wasDisabled = disabled;
    onChange = newProps.onChange;
    disabled = newProps.disabled;
    height = newProps.height;
    nodeName = newProps.nodeName ?? nodeName;
    layout();
    let incoming = newProps.value && Array.isArray(newProps.value.tracks) ? newProps.value : null;
    if (incoming && incoming.reload) {
      incoming = { ...incoming };
      delete incoming.reload; // a reload request coming back is not part of the timeline
    }
    if (!incoming) {
      if (state.model) { state.model = null; renderEmpty(); }
      return;
    }
    const same = !!state.model && sameModel(incoming, state.model);
    if (same) awaitingEcho = false; // the latest send has come back
    else if (state.model && awaitingEcho && performance.now() - lastSendAt < STALE_ECHO_MS && held.slice(0, -1).includes(JSON.stringify(incoming))) {
      if (wasDisabled !== disabled) renderToolbar();
      return; // an older value coming back. The latest is on its way
    }
    if (state.model && !same && onlyPreviewsDiffer(incoming, state.model)) {
      // The node is making viewer copies of linked files and reporting how far it has got. That changes nothing the
      // user edits, so only the preview information is taken and nothing is redrawn but the viewer.
      for (const key of PREVIEW_KEYS) {
        if (incoming[key]) state.model[key] = structuredClone(incoming[key]);
        else delete state.model[key];
      }
      held.length = 0;
      remember(state.model);
      updateViewer();
      return;
    }
    if (!state.model || !sameModel(incoming, state.model)) {
      const first = !state.model;
      state.model = structuredClone(incoming);
      state.preview = null;
      if (state.selectedId && !findClip(state.model, state.selectedId)) state.selectedId = null;
      setSelected(state.selectedId); // the incoming timeline may carry an older selection
      if (first) state.zoom = 0;
      held.length = 0;
      remember(state.model);
      renderAll();
    } else if (wasDisabled !== disabled) {
      renderToolbar(); // only the buttons' enabled state can have changed, and a rebuild would interrupt a slider drag
    }
  }

  function cleanup() {
    clearTimeout(selectionTimer);
    tip.hide();
    pause();
    viewer.video.pause();
    audio.stop();
    if (stopTracking) stopTracking();
    if (observer) observer.disconnect();
    if (modal) {
      root.ownerDocument.removeEventListener('keydown', onModalKey, true);
      modal.remove();
      modal = null;
    }
    root.remove();
    delete container._instance;
  }

  layout();
  if (state.model) renderAll();
  else renderEmpty();

  container._instance = { handleUpdate, cleanup, wrapper: root, getState: () => state, tick };
  return { cleanup, update: handleUpdate };
}
