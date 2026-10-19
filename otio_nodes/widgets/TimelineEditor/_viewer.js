// The viewer above the timeline: a monitor that shows the slate for whatever is under the playhead, or the linked video
// when the shot has one the browser can play, with the spoken lines as subtitles and the SFX and audio clips as chips. It draws from the timeline model, so it follows edits as
// they happen. The play controls live in the bar above the timeline. Text is always set with textContent, never as HTML.

import { el } from './_dom.js?v=966565b0';
import { activeAt, isLinked, isStale } from './_ops.js?v=966565b0';
import { formatSeconds } from './_time.js?v=966565b0';

export function createViewer() {
  const bar = el('div', { class: 'otl-s-bar' });
  const seq = el('div', { class: 'otl-s-seq' });
  const chips = el('div', { class: 'otl-s-chips' });
  const title = el('div', { class: 'otl-s-title' });
  const desc = el('div', { class: 'otl-s-desc' });
  const subs = el('div', { class: 'otl-s-subs' });
  const where = el('div', { class: 'otl-s-where' });
  const stale = el('div', {
    class: 'otl-s-stale',
    text: 'Preview differs from the media file',
    title: 'The clip text has changed since its slate file was made. A new slate is made when the node runs.',
  });
  const slate = el('div', { class: 'otl-slate' }, [
    bar,
    el('div', { class: 'otl-s-top' }, [seq, el('div', { class: 'otl-s-right' }, [stale, chips])]),
    title,
    desc,
    subs,
    where,
  ]);
  const video = el('video', { class: 'otl-video', preload: 'auto' });
  video.muted = true;
  video.playsInline = true;
  const unplayable = new Map(); // address -> why the browser gave up on it
  const retried = new Set();
  let loaded = '';
  let lastSeek = 0;
  let want = { time: 0, playing: false }; // where the video should be, whatever it is doing now

  // Move the video to `want`. Scrubbing asks for a new time on every mouse move. A video that is still working on one
  // seek is left alone, and the latest wish is applied when it lands, so seeks never pile up. Piled-up seeks make some
  // hardware decoders fail. A video that is playing keeps its own time and is only pulled back when it is far off.
  function apply() {
    if (!loaded || video.seeking) return;
    const off = Math.abs(video.currentTime - want.time);
    const now = performance.now();
    if (want.playing) {
      if (video.paused && off > 0.05) {
        video.currentTime = want.time;
        lastSeek = now;
      }
      if (video.paused) video.play().catch(() => {});
      else if (video.readyState >= 3 && off > 0.75 && now - lastSeek > 1500) {
        video.currentTime = want.time;
        lastSeek = now;
      }
    } else {
      if (!video.paused) video.pause();
      if (off > 0.01) {
        video.currentTime = want.time;
        lastSeek = now;
      }
    }
  }
  video.addEventListener('seeked', () => {
    retried.delete(loaded); // it is working, so a later failure gets a fresh retry
    apply();
  });
  video.addEventListener('loadedmetadata', apply);
  video.addEventListener('error', () => {
    // a file the browser cannot play, or cannot fetch, so the slate stays on screen and says why
    if (loaded && !retried.has(loaded)) {
      // A decoder can fail on a stream that plays fine on a second try, so reload before giving up
      retried.add(loaded);
      const again = loaded;
      video.removeAttribute('src');
      video.load();
      video.src = again;
      return;
    }
    if (loaded) unplayable.set(loaded, (video.error && video.error.message) || `media error ${video.error ? video.error.code : '?'}`);
    screen.classList.remove('has-video');
  });
  const progress = el('div', { class: 'otl-s-progress' }, [el('div', { class: 'otl-s-progress-fill' })]);
  const screen = el('div', { class: 'otl-screen' }, [video, slate, progress]);
  const element = el('div', { class: 'otl-viewer' }, [el('div', { class: 'otl-screen-wrap' }, [screen])]);

  // Show the linked video for the shot, at the frame under the playhead. Returns why it cannot, or "" when it can.
  function showVideo(model, shot, frame, rate, playing) {
    const address = shot && isLinked(shot.media) ? shot.media.url : '';
    const url = address && model.previews ? model.previews[address] : '';
    const done = address && model.preparing ? model.preparing[address] : undefined;
    progress.classList.toggle('on', done !== undefined);
    if (done !== undefined) progress.firstChild.style.width = `${Math.round(done * 100)}%`;
    if (!url || unplayable.has(url)) {
      if (!video.paused) video.pause();
      screen.classList.remove('has-video');
      if (!address) return '';
      if (url) return `no preview: the browser could not play it (${unplayable.get(url)})`;
      if (done !== undefined) return `making a preview copy for the viewer, ${Math.round(done * 100)}%`;
      const failed = model.preview_errors ? model.preview_errors[address] : '';
      return failed ? `no preview: the copy could not be made (${failed})` : 'no preview: the node has not made a playable URL for this file';
    }
    if (loaded !== url) {
      loaded = url;
      video.src = url;
    }
    screen.classList.add('has-video');
    let time = ((shot.media.start || 0) + (frame - shot.start)) / rate;
    if (Number.isFinite(video.duration)) time = Math.min(time, Math.max(0, video.duration - 0.04));
    want = { time, playing };
    apply();
    return '';
  }

  function update(model, frame, { rate, playing = false }) {
    const now = activeAt(model, frame);
    const shot = now.shot;
    const meta = shot ? shot.meta || {} : {};
    const whyNot = showVideo(model, shot, frame, rate, playing);
    bar.style.background = shot ? shot.color || '#888' : 'transparent';
    seq.textContent = shot ? [meta.sequence ? `SQ${String(meta.sequence).padStart(2, '0')}` : '', meta.heading || ''].filter(Boolean).join('  ·  ') : '';
    screen.classList.toggle('stale', !!shot && isStale(shot));
    title.textContent = shot ? shot.name : 'No shot here';
    title.classList.toggle('dim', !shot);
    desc.textContent = shot ? shot.description || '' : '';
    where.textContent = shot
      ? `Shot ${now.shotIndex + 1} of ${now.shotCount}   ${formatSeconds(frame - shot.start, rate)} / ${formatSeconds(shot.duration, rate)}${
          isLinked(shot.media) ? `   linked: ${String(shot.media.url).split(/[\\/]/).pop()}${whyNot ? `  (${whyNot})` : ''}` : ''
        }`
      : '';

    subs.replaceChildren(
      ...now.lines.map((line) => {
        const m = line.meta || {};
        const who = `${m.character || line.name}${m.extension ? ` (${m.extension})` : ''}`;
        return el('div', { class: 'otl-sub' }, [el('b', { text: `${who}  ` }), el('span', { text: line.description || line.name })]);
      }),
    );
    chips.replaceChildren(
      ...now.effects.map((clip) =>
        el('span', { class: 'otl-chip', style: `background:${clip.color || '#888'}`, text: clip.name }),
      ),
    );
  }

  return { element, update, video };
}
