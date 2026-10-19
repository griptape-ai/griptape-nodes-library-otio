// Editing operations on the timeline model. Pure functions: each takes a model and returns a new model, or null when
// the edit would break the timeline (overlapping clips, negative times). The model shape is documented in model.py.
//
//   {rate, tracks: [{id, name, kind, role, clips: [{id, name, start, duration, description, color, enabled, meta,
//   media}]}], markers}
//
// Options: `ripple` makes a shot's new length push everything after it, `link` keeps a shot's dialogue with it.

export const ROLE_SHOTS = 'shots';
export const ROLE_DIALOGUE = 'dialogue';
export const FREE_ROLES = ['sfx', 'audio'];
const FREE_CLIP_COLORS = { sfx: '#c27ad6', audio: '#5aa0d6' };
const DEFAULT_FREE_SECONDS = 2;

const clone = (model) => structuredClone(model);

// Media a person linked to a clip: a file the placeholder maker did not create. Placeholder slates have a key that
// starts with "griptape:".
export const isLinked = (media) => !!media && !String(media.key || '').startsWith('griptape:');

export function findClip(model, id) {
  for (const track of model.tracks) {
    const index = track.clips.findIndex((c) => c.id === id);
    if (index >= 0) return { track, clip: track.clips[index], index };
  }
  return null;
}

export function trackByRole(model, role) {
  return model.tracks.find((t) => t.role === role) || null;
}

export function endOf(clip) {
  return clip.start + clip.duration;
}

export function totalFrames(model) {
  let end = 0;
  for (const track of model.tracks) for (const clip of track.clips) end = Math.max(end, endOf(clip));
  return end;
}

export function sortedClips(track) {
  return [...track.clips].sort((a, b) => a.start - b.start);
}

// The space around a clip on its own track: where the previous clip ends and the next one starts.
export function neighbors(track, clip) {
  let prevEnd = 0;
  let nextStart = Infinity;
  for (const other of track.clips) {
    if (other.id === clip.id) continue;
    if (endOf(other) <= clip.start) prevEnd = Math.max(prevEnd, endOf(other));
    else if (other.start >= endOf(clip)) nextStart = Math.min(nextStart, other.start);
  }
  return { prevEnd, nextStart };
}

export function validate(model) {
  const problems = [];
  const ids = new Set();
  for (const track of model.tracks) {
    let end = 0;
    for (const clip of sortedClips(track)) {
      if (!Number.isInteger(clip.start) || !Number.isInteger(clip.duration)) problems.push(`${clip.name}: not whole frames`);
      if (clip.start < 0 || clip.duration < 1) problems.push(`${clip.name}: bad start or duration`);
      if (clip.start < end) problems.push(`${clip.name}: overlaps the previous clip`);
      if (ids.has(clip.id)) problems.push(`${clip.name}: duplicate id`);
      ids.add(clip.id);
      end = Math.max(end, endOf(clip));
    }
  }
  return problems;
}

// A linked clip cannot run past the end of its file, when the file's length is known.
const fitsMedia = (clip) =>
  !isLinked(clip.media) || !Number.isInteger(clip.media.duration) || clip.media.start + clip.duration <= clip.media.duration;

const checked = (model) => (validate(model).length === 0 ? model : null);

function dialogueOf(model, shotId) {
  const lines = [];
  for (const track of model.tracks) {
    for (const clip of track.clips) if (clip.meta && clip.meta.kind === 'dialogue' && clip.meta.shot === shotId) lines.push(clip);
  }
  return lines;
}

// Shift every clip on every track that starts at or after `from` by `delta` frames.
function shiftAfter(model, from, delta, exceptIds) {
  for (const track of model.tracks) {
    for (const clip of track.clips) {
      if (!exceptIds.has(clip.id) && clip.start >= from) clip.start += delta;
    }
  }
}

// Frames worth snapping to: the start, the playhead, and the edges of every clip except the ones being dragged.
export function snapPoints(model, excludeIds, playhead) {
  const points = new Set([0, Math.max(0, Math.round(playhead))]);
  for (const track of model.tracks) {
    for (const clip of track.clips) {
      if (excludeIds.has(clip.id)) continue;
      points.add(clip.start);
      points.add(endOf(clip));
    }
  }
  return [...points].sort((a, b) => a - b);
}

export function snapFrame(frame, points, threshold) {
  let best = frame;
  let bestDistance = threshold + 1;
  for (const point of points) {
    const distance = Math.abs(point - frame);
    if (distance < bestDistance) {
      best = point;
      bestDistance = distance;
    }
  }
  return bestDistance <= threshold ? best : frame;
}

export function moveClip(model, id, newStart, opts = {}) {
  const next = clone(model);
  const found = findClip(next, id);
  if (!found) return null;
  const { track, clip } = found;
  const { prevEnd, nextStart } = neighbors(track, clip);
  let start = Math.max(prevEnd, Math.round(newStart));
  if (nextStart !== Infinity) start = Math.min(start, nextStart - clip.duration);
  if (start < prevEnd) return null;
  const delta = start - clip.start;
  clip.start = start;
  if (delta !== 0 && opts.link && clip.meta && clip.meta.kind === 'shot') {
    for (const line of dialogueOf(next, id)) line.start += delta;
  }
  return checked(next);
}

export function trimClip(model, id, edge, frame, opts = {}) {
  const next = clone(model);
  const found = findClip(next, id);
  if (!found) return null;
  const { track, clip } = found;
  const { prevEnd, nextStart } = neighbors(track, clip);
  const oldEnd = endOf(clip);
  const target = Math.round(frame);

  if (edge === 'start') {
    let start = Math.min(Math.max(target, prevEnd), oldEnd - 1);
    if (isLinked(clip.media)) start = Math.max(start, clip.start - clip.media.start); // cannot go before the file's start
    if (isLinked(clip.media)) clip.media.start += start - clip.start; // the clip still shows the same part of the file
    clip.start = start;
    clip.duration = oldEnd - start;
    return checked(next);
  }

  let end = Math.max(clip.start + 1, target);
  if (isLinked(clip.media) && Number.isInteger(clip.media.duration)) {
    end = Math.min(end, clip.start + clip.media.duration - clip.media.start); // cannot run past the file's end
  }
  const rippling = opts.ripple && track.role === ROLE_SHOTS;
  if (!rippling && nextStart !== Infinity) end = Math.min(end, nextStart);
  const delta = end - oldEnd;
  clip.duration = end - clip.start;
  if (rippling && delta !== 0) shiftAfter(next, oldEnd, delta, new Set([id]));
  return checked(next);
}

export function splitClip(model, id, frame) {
  const next = clone(model);
  const found = findClip(next, id);
  if (!found) return null;
  const { track, clip } = found;
  const at = Math.round(frame);
  if (at <= clip.start || at >= endOf(clip)) return null;

  const used = new Set(next.tracks.flatMap((t) => t.clips.map((c) => c.id)));
  let newId = `${id}-b`;
  for (let n = 2; used.has(newId); n += 1) newId = `${id}-b${n}`;

  const second = structuredClone(clip);
  second.id = newId;
  second.name = `${clip.name} b`;
  second.start = at;
  second.duration = endOf(clip) - at;
  second.media = isLinked(clip.media) ? { ...structuredClone(clip.media), start: clip.media.start + (at - clip.start) } : null;
  clip.duration = at - clip.start;
  track.clips.push(second);

  if (clip.meta && clip.meta.kind === 'shot') {
    for (const line of dialogueOf(next, id)) {
      if (line.start >= at) line.meta.shot = newId;
    }
  }
  return checked(next);
}

export function deleteClip(model, id, opts = {}) {
  const next = clone(model);
  const found = findClip(next, id);
  if (!found) return null;
  const { track, clip, index } = found;
  const gone = new Set([id]);
  track.clips.splice(index, 1);
  if (opts.link && clip.meta && clip.meta.kind === 'shot') {
    for (const line of dialogueOf(next, id)) gone.add(line.id);
    for (const t of next.tracks) t.clips = t.clips.filter((c) => !gone.has(c.id));
  }
  if (opts.ripple && track.role === ROLE_SHOTS) shiftAfter(next, endOf(clip), -clip.duration, gone);
  return checked(next);
}

// Add an SFX or audio clip at `start`, moved later if something is already there. Returns {model, id}.
export function addClip(model, role, start, duration, name) {
  if (!FREE_ROLES.includes(role)) return null;
  const next = clone(model);
  let track = trackByRole(next, role);
  if (!track) {
    track = { id: `track-${role}`, name: role === 'sfx' ? 'SFX' : 'Audio', kind: 'audio', role, clips: [] };
    next.tracks.push(track);
  }
  const length = Math.max(1, Math.round(duration || DEFAULT_FREE_SECONDS * next.rate));
  let at = Math.max(0, Math.round(start));
  for (const other of sortedClips(track)) {
    if (at < endOf(other) && at + length > other.start) at = endOf(other);
  }
  const used = new Set(next.tracks.flatMap((t) => t.clips.map((c) => c.id)));
  let n = track.clips.length + 1;
  while (used.has(`${role}-${n}`)) n += 1;
  const id = `${role}-${n}`;
  track.clips.push({
    id,
    name: name || (role === 'sfx' ? 'New SFX' : 'New audio'),
    start: at,
    duration: length,
    description: '',
    color: FREE_CLIP_COLORS[role],
    enabled: true,
    media: null,
    meta: { kind: role },
  });
  const result = checked(next);
  return result ? { model: result, id } : null;
}

// What a clip's placeholder slate shows. This matches how the slate is drawn when the timeline is saved (media.py).
export function slateText(clip) {
  const meta = clip.meta || {};
  const sequence = Number.isInteger(meta.sequence) ? `SQ${String(meta.sequence).padStart(2, '0')}` : '';
  return {
    title: clip.name,
    subtitle: [sequence, meta.heading || ''].filter(Boolean).join('  '),
    body: clip.description || '',
  };
}

// True when the clip's text has changed since its placeholder slate file was made, so the preview, which draws the
// current text, no longer matches the file on disk. A slate with no record of what it shows, linked media and clips
// with no media are never flagged.
export function isStale(clip) {
  const media = clip.media;
  if (!media || isLinked(media) || !media.shown) return false;
  const now = slateText(clip);
  return now.title !== media.shown.title || now.subtitle !== media.shown.subtitle || now.body !== media.shown.body;
}

// Link a clip to a file. `url` is whatever was typed: a path, a file:// address or a project macro. The file is checked
// and measured when the node runs, so its length is unknown here. `startFrames` is where in the file the clip begins.
export function setMedia(model, id, url, startFrames = 0) {
  const text = String(url || '').trim();
  const next = clone(model);
  const found = findClip(next, id);
  if (!found || !text) return null;
  found.clip.media = { url: text, start: Math.max(0, Math.round(startFrames)), duration: null, key: '' };
  return checked(next);
}

// Go back to the placeholder slate. It is made again when the timeline is saved.
export function clearMedia(model, id) {
  const next = clone(model);
  const found = findClip(next, id);
  if (!found) return null;
  found.clip.media = null;
  return checked(next);
}

const EDITABLE = ['name', 'description', 'color', 'enabled', 'start', 'duration'];

export function updateClip(model, id, patch) {
  const next = clone(model);
  const found = findClip(next, id);
  if (!found) return null;
  for (const key of EDITABLE) {
    if (!(key in patch)) continue;
    found.clip[key] = key === 'start' || key === 'duration' ? Math.round(patch[key]) : patch[key];
  }
  if ('duration' in patch && !fitsMedia(found.clip)) return null; // other edits to an over-long clip are still allowed
  return checked(next);
}

// Every frame where a clip starts or ends, in order. These are the edit points the up and down arrows jump between.
export function editPoints(model) {
  const frames = new Set();
  for (const track of model.tracks) {
    for (const clip of track.clips) {
      frames.add(clip.start);
      frames.add(endOf(clip));
    }
  }
  return [...frames].sort((a, b) => a - b);
}

// The nearest edit point before `frame`, or null if there is none.
export function previousEdit(points, frame) {
  for (let i = points.length - 1; i >= 0; i -= 1) if (points[i] < frame) return points[i];
  return null;
}

// The nearest edit point after `frame`, or null if there is none.
export function nextEdit(points, frame) {
  return points.find((p) => p > frame) ?? null;
}

// The clip before (direction -1) or after (1) a clip on its own track, or null at the end of the track.
export function siblingClip(model, id, direction) {
  const found = findClip(model, id);
  if (!found) return null;
  const clips = sortedClips(found.track);
  return clips[clips.findIndex((c) => c.id === id) + direction] || null;
}

// Bands for the sequence and scene lanes: runs of neighbouring shots with the same sequence (or sequence and scene).
export function deriveBands(model) {
  const shots = model.tracks
    .filter((t) => t.role === ROLE_SHOTS)
    .flatMap((t) => t.clips)
    .filter((c) => c.meta && c.meta.kind === 'shot')
    .sort((a, b) => a.start - b.start);

  const runs = (keyOf, labelOf, colorOf) => {
    const bands = [];
    for (const clip of shots) {
      const key = keyOf(clip);
      const last = bands[bands.length - 1];
      if (last && last.key === key) last.end = endOf(clip);
      else bands.push({ key, label: labelOf(clip), color: colorOf(clip), start: clip.start, end: endOf(clip) });
    }
    return bands;
  };
  const pad = (n) => String(n).padStart(2, '0');
  const sequences = runs(
    (c) => `${c.meta.sequence}`,
    (c) => `SQ${pad(c.meta.sequence)}`,
    () => '#8f6fc7',
  );
  const scenes = runs(
    (c) => `${c.meta.sequence}/${c.meta.scene}`,
    (c) => c.meta.heading || '(no heading)',
    (c) => (String(c.meta.int_ext).toUpperCase() === 'EXT' ? '#4f9d69' : '#d9a441'),
  );
  return { sequences, scenes };
}

// What is on screen at `frame`: the shot, the spoken lines, and the SFX and audio clips. Disabled clips are skipped.
export function activeAt(model, frame) {
  const shots = model.tracks
    .filter((t) => t.role === ROLE_SHOTS)
    .flatMap((t) => t.clips)
    .sort((a, b) => a.start - b.start);
  const at = (clip) => clip.enabled !== false && clip.start <= frame && frame < endOf(clip);
  const result = { shot: null, shotIndex: -1, shotCount: shots.length, lines: [], effects: [] };
  shots.forEach((clip, index) => {
    if (at(clip)) {
      result.shot = clip;
      result.shotIndex = index;
    }
  });
  for (const track of model.tracks) {
    if (track.role === ROLE_DIALOGUE) result.lines.push(...track.clips.filter(at));
    else if (FREE_ROLES.includes(track.role)) result.effects.push(...track.clips.filter(at));
  }
  result.lines.sort((a, b) => a.start - b.start);
  return result;
}

// Muting a track only silences it in the editor's playback. It is kept with the editor's timeline, and is not written
// to the OTIO. Returns a new model, or null when there is no such track.
export function setTrackMuted(model, trackId, muted) {
  const next = clone(model);
  const track = next.tracks.find((t) => t.id === trackId);
  if (!track) return null;
  if (muted) track.muted = true;
  else delete track.muted;
  return next;
}

// The clips that should be heard at `frame`: enabled clips on audio tracks that are not muted and have a linked file
// the browser can play (`previews` maps what was typed in the clip to a URL). Returns [{clip, url}].
export function audibleAt(model, frame) {
  const heard = [];
  for (const track of model.tracks) {
    if (track.kind !== 'audio' || track.muted) continue;
    for (const clip of track.clips) {
      if (clip.enabled === false || clip.start > frame || frame >= endOf(clip)) continue;
      const url = isLinked(clip.media) && model.previews ? model.previews[clip.media.url] : '';
      if (url) heard.push({ clip, url });
    }
  }
  return heard;
}
