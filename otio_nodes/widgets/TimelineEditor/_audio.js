// Sound for the editor: plays the audio files linked to clips on the audio tracks while the timeline plays. Each clip
// that is sounding gets its own audio element. Only linked files make sound, because the placeholder audio is silent.
// A muted track is skipped. Nothing plays while paused or scrubbing.

import { audibleAt } from './_ops.js?v=2578900f';

const MAX_DRIFT = 0.5; // seconds a playing clip may be off before it is pulled back
const MIN_SEEK_GAP = 1500; // milliseconds between corrections, so seeks never pile up

export function createAudio(doc) {
  const players = new Map(); // clip id -> {audio, url, lastSeek}

  function player(clip, url) {
    let found = players.get(clip.id);
    if (!found) {
      found = { audio: doc.createElement('audio'), url: '', lastSeek: 0 };
      found.audio.preload = 'none';
      players.set(clip.id, found);
    }
    if (found.url !== url) {
      found.url = url;
      found.audio.src = url;
    }
    return found;
  }

  function sync(model, frame, rate, playing) {
    const heard = playing ? audibleAt(model, frame) : [];
    const ids = new Set(heard.map(({ clip }) => clip.id));
    for (const [id, found] of players) if (!ids.has(id) && !found.audio.paused) found.audio.pause();
    const now = performance.now();
    for (const { clip, url } of heard) {
      const found = player(clip, url);
      const { audio } = found;
      const time = ((clip.media.start || 0) + (frame - clip.start)) / rate;
      const off = Math.abs(audio.currentTime - time);
      if (audio.paused) {
        if (off > 0.05 && !audio.seeking) {
          audio.currentTime = time;
          found.lastSeek = now;
        }
        audio.play().catch(() => {});
      } else if (!audio.seeking && audio.readyState >= 3 && off > MAX_DRIFT && now - found.lastSeek > MIN_SEEK_GAP) {
        audio.currentTime = time;
        found.lastSeek = now;
      }
    }
  }

  function stop() {
    for (const { audio } of players.values()) audio.pause();
  }

  return { sync, stop };
}
