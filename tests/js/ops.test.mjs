import assert from 'node:assert/strict';
import { test } from 'node:test';

import {
  activeAt,
  addClip,
  audibleAt,
  deleteClip,
  deriveBands,
  findClip,
  moveClip,
  neighbors,
  snapFrame,
  snapPoints,
  setTrackMuted,
  splitClip,
  totalFrames,
  trimClip,
  updateClip,
  validate,
} from '../../otio_nodes/widgets/TimelineEditor/_ops.js';
import { frameToTimecode, formatSeconds, rulerStepFrames } from '../../otio_nodes/widgets/TimelineEditor/_time.js';

function clip(id, start, duration, meta = {}) {
  return { id, name: id, start, duration, description: '', color: '#888', enabled: true, media: null, meta };
}

function shotMeta(sequence, scene, heading = 'INT. ROOM - DAY', intExt = 'INT') {
  return { kind: 'shot', sequence, scene, heading, int_ext: intExt, notes: [] };
}

// Three shots end to end (0-100, 100-200, 200-300), two spoken lines, empty SFX and Audio tracks.
function model() {
  return {
    title: 'T',
    rate: 24,
    tracks: [
      {
        id: 'track-shots',
        name: 'Shots',
        kind: 'video',
        role: 'shots',
        clips: [
          clip('shot-001', 0, 100, shotMeta(1, 0)),
          clip('shot-002', 100, 100, shotMeta(1, 1, 'INT. HALL - DAY')),
          clip('shot-003', 200, 100, shotMeta(2, 2, 'EXT. YARD - DAY', 'EXT')),
        ],
      },
      {
        id: 'track-jack',
        name: 'JACK',
        kind: 'audio',
        role: 'dialogue',
        clips: [
          clip('line-001', 10, 50, { kind: 'dialogue', shot: 'shot-001' }),
          clip('line-002', 110, 40, { kind: 'dialogue', shot: 'shot-002' }),
        ],
      },
      { id: 'track-sfx', name: 'SFX', kind: 'audio', role: 'sfx', clips: [] },
      { id: 'track-audio', name: 'Audio', kind: 'audio', role: 'audio', clips: [] },
    ],
    markers: [],
  };
}

const start = (m, id) => findClip(m, id).clip.start;
const duration = (m, id) => findClip(m, id).clip.duration;

test('total frames and validation', () => {
  const m = model();
  assert.equal(totalFrames(m), 300);
  assert.deepEqual(validate(m), []);
  m.tracks[0].clips[1].start = 90;
  assert.match(validate(m)[0], /overlaps/);
});

test('moving is clamped by the neighbours', () => {
  const m = model();
  const moved = moveClip(m, 'line-001', 500);
  assert.equal(start(moved, 'line-001'), 60, 'stops where line-002 begins');
  assert.equal(start(moveClip(m, 'line-001', -20), 'line-001'), 0);
  assert.equal(start(moveClip(m, 'line-002', 60), 'line-002'), 60);
  assert.equal(start(m, 'line-001'), 10, 'the original model is not changed');
});

test('moving a shot with link takes its dialogue along', () => {
  const m = model();
  m.tracks[0].clips[0].duration = 80; // leave a gap so shot-001 can move
  const moved = moveClip(m, 'shot-001', 20, { link: true });
  assert.equal(start(moved, 'shot-001'), 20);
  assert.equal(start(moved, 'line-001'), 30);
  const unlinked = moveClip(m, 'shot-001', 20, { link: false });
  assert.equal(start(unlinked, 'line-001'), 10);
});

test('trimming the end without ripple stops at the next clip', () => {
  const m = model();
  assert.equal(duration(trimClip(m, 'shot-001', 'end', 60), 'shot-001'), 60);
  assert.equal(duration(trimClip(m, 'shot-001', 'end', 150), 'shot-001'), 100);
  assert.equal(duration(trimClip(m, 'shot-001', 'end', -5), 'shot-001'), 1);
  assert.equal(start(trimClip(m, 'shot-001', 'end', 60), 'shot-002'), 100);
});

test('trimming a shot with ripple moves everything after it', () => {
  const m = model();
  const longer = trimClip(m, 'shot-001', 'end', 130, { ripple: true });
  assert.equal(duration(longer, 'shot-001'), 130);
  assert.equal(start(longer, 'shot-002'), 130);
  assert.equal(start(longer, 'shot-003'), 230);
  assert.equal(start(longer, 'line-002'), 140);
  assert.equal(start(longer, 'line-001'), 10);

  const shorter = trimClip(m, 'shot-001', 'end', 70, { ripple: true });
  assert.equal(start(shorter, 'shot-002'), 70);
  assert.equal(start(shorter, 'line-002'), 80);
  assert.deepEqual(validate(shorter), []);
});

test('ripple is refused when it would crush a line into the next one', () => {
  const m = model();
  m.tracks[1].clips[0].duration = 95; // line-001 now runs to 105, past the end of shot-001
  assert.equal(trimClip(m, 'shot-001', 'end', 60, { ripple: true }), null);
});

test('ripple only applies to the shots track', () => {
  const m = addClip(model(), 'sfx', 0, 24, 'bang').model;
  const trimmed = trimClip(m, 'sfx-1', 'end', 10, { ripple: true });
  assert.equal(duration(trimmed, 'sfx-1'), 10);
  assert.equal(start(trimmed, 'shot-002'), 100);
});

test('trimming the start keeps the end and stops at the previous clip', () => {
  const m = model();
  const t = trimClip(m, 'shot-002', 'start', 130);
  assert.equal(start(t, 'shot-002'), 130);
  assert.equal(duration(t, 'shot-002'), 70);
  assert.equal(start(trimClip(m, 'shot-002', 'start', 20), 'shot-002'), 100);
  assert.equal(start(trimClip(m, 'shot-002', 'start', 500), 'shot-002'), 199);
});

test('splitting a shot hands the later dialogue to the new shot', () => {
  const m = model();
  const s = splitClip(m, 'shot-001', 40);
  assert.equal(duration(s, 'shot-001'), 40);
  const second = findClip(s, 'shot-001-b').clip;
  assert.equal(second.start, 40);
  assert.equal(second.duration, 60);
  assert.equal(second.media, null);
  assert.equal(findClip(s, 'line-001').clip.meta.shot, 'shot-001', 'a line that starts before the cut stays');
  const s2 = splitClip(m, 'shot-001', 5);
  assert.equal(findClip(s2, 'line-001').clip.meta.shot, 'shot-001-b');
  assert.equal(splitClip(m, 'shot-001', 0), null);
  assert.equal(splitClip(m, 'shot-001', 100), null);
});

test('splitting twice gives unique ids', () => {
  let m = splitClip(model(), 'shot-001', 30);
  m = splitClip(m, 'shot-001', 20);
  const ids = m.tracks[0].clips.map((c) => c.id);
  assert.equal(new Set(ids).size, ids.length);
});

test('deleting a shot removes its dialogue and closes the gap with ripple', () => {
  const m = model();
  const plain = deleteClip(m, 'shot-002', {});
  assert.equal(findClip(plain, 'shot-002'), null);
  assert.ok(findClip(plain, 'line-002'));
  assert.equal(start(plain, 'shot-003'), 200);

  const full = deleteClip(m, 'shot-002', { ripple: true, link: true });
  assert.equal(findClip(full, 'line-002'), null);
  assert.equal(start(full, 'shot-003'), 100);
  assert.equal(totalFrames(full), 200);
});

test('adding SFX and audio clips', () => {
  const m = model();
  const { model: withSfx, id } = addClip(m, 'sfx', 50, 24, 'car crash');
  assert.equal(id, 'sfx-1');
  assert.equal(findClip(withSfx, id).clip.name, 'car crash');
  assert.equal(start(withSfx, id), 50);

  const second = addClip(withSfx, 'sfx', 60, 24);
  assert.equal(start(second.model, second.id), 74, 'moved past the clip already there');
  assert.equal(findClip(second.model, second.id).clip.name, 'New SFX');

  assert.equal(addClip(m, 'dialogue', 0, 24), null);
  const defaults = addClip(m, 'audio', 0);
  assert.equal(findClip(defaults.model, defaults.id).clip.duration, 48);
});

test('adding a clip creates the track when it is missing', () => {
  const m = model();
  m.tracks = m.tracks.filter((t) => t.role !== 'sfx');
  const added = addClip(m, 'sfx', 0, 24);
  assert.ok(added.model.tracks.some((t) => t.role === 'sfx' && t.clips.length === 1));
});

test('updating a clip', () => {
  const m = model();
  const u = updateClip(m, 'shot-001', { name: 'Opening', description: 'New text', enabled: false, duration: 90.4 });
  const c = findClip(u, 'shot-001').clip;
  assert.deepEqual([c.name, c.description, c.enabled, c.duration], ['Opening', 'New text', false, 90]);
  assert.equal(updateClip(m, 'shot-001', { duration: 150 }), null, 'would overlap');
  assert.equal(updateClip(m, 'nope', { name: 'x' }), null);
  assert.equal(findClip(updateClip(m, 'shot-001', { id: 'hack' }), 'shot-001').clip.id, 'shot-001');
});

test('snapping', () => {
  const m = model();
  const points = snapPoints(m, new Set(['shot-002']), 137);
  assert.ok(points.includes(0) && points.includes(137) && points.includes(300));
  assert.ok(points.includes(100) && points.includes(200), 'edges of the other clips are included');
  assert.ok(points.includes(0));
  assert.equal(snapFrame(134, points, 5), 137);
  assert.equal(snapFrame(120, points, 5), 120);
  assert.equal(snapFrame(2, points, 5), 0);
});

test('neighbours', () => {
  const m = model();
  const { track, clip: c } = findClip(m, 'shot-002');
  assert.deepEqual(neighbors(track, c), { prevEnd: 100, nextStart: 200 });
  const first = findClip(m, 'shot-001');
  assert.deepEqual(neighbors(first.track, first.clip), { prevEnd: 0, nextStart: 100 });
});

test('bands group neighbouring shots', () => {
  const { sequences, scenes } = deriveBands(model());
  assert.deepEqual(
    sequences.map((b) => [b.label, b.start, b.end]),
    [
      ['SQ01', 0, 200],
      ['SQ02', 200, 300],
    ],
  );
  assert.deepEqual(
    scenes.map((b) => [b.label, b.start, b.end, b.color]),
    [
      ['INT. ROOM - DAY', 0, 100, '#d9a441'],
      ['INT. HALL - DAY', 100, 200, '#d9a441'],
      ['EXT. YARD - DAY', 200, 300, '#4f9d69'],
    ],
  );
});

test('bands follow a ripple edit', () => {
  const m = trimClip(model(), 'shot-001', 'end', 130, { ripple: true });
  assert.deepEqual(deriveBands(m).sequences.map((b) => [b.start, b.end]), [[0, 230], [230, 330]]);
});

test('timecode, seconds and ruler steps', () => {
  assert.equal(frameToTimecode(0, 24), '00:00:00:00');
  assert.equal(frameToTimecode(24 * 83 + 12, 24), '00:01:23:12');
  assert.equal(frameToTimecode(24 * 3600, 24), '01:00:00:00');
  assert.equal(formatSeconds(36, 24), '1.5 s');
  assert.equal(formatSeconds(24 * 127 + 6, 24), '2:07.3');
  assert.ok(rulerStepFrames(4, 24) * 4 >= 90);
  assert.ok(rulerStepFrames(0.01, 24) > rulerStepFrames(1, 24));
});

test('what is on screen at a frame', () => {
  const m = addClip(model(), 'sfx', 20, 30, 'bang').model;
  let now = activeAt(m, 20);
  assert.equal(now.shot.id, 'shot-001');
  assert.equal(now.shotIndex, 0);
  assert.equal(now.shotCount, 3);
  assert.deepEqual(now.lines.map((c) => c.id), ['line-001']);
  assert.deepEqual(now.effects.map((c) => c.id), ['sfx-1']);

  now = activeAt(m, 100);
  assert.equal(now.shot.id, 'shot-002', 'a shot ends one frame before the next begins');
  assert.deepEqual(now.lines, []);

  assert.equal(activeAt(m, 300).shot, null, 'nothing is on screen past the end');
  assert.equal(activeAt(m, 300).shotIndex, -1);
});

test('disabled clips are not on screen', () => {
  const m = updateClip(model(), 'shot-001', { enabled: false });
  assert.equal(activeAt(m, 20).shot, null);
  const quiet = updateClip(model(), 'line-001', { enabled: false });
  assert.deepEqual(activeAt(quiet, 20).lines, []);
});

import { clearMedia, isLinked, setMedia } from '../../otio_nodes/widgets/TimelineEditor/_ops.js';

test('linking a clip to a file and going back to the placeholder', () => {
  const m = model();
  const linked = setMedia(m, 'shot-002', '  /media/plate.mov  ', 48);
  const media = findClip(linked, 'shot-002').clip.media;
  assert.deepEqual(media, { url: '/media/plate.mov', start: 48, duration: null, key: '' });
  assert.ok(isLinked(media));
  assert.equal(findClip(m, 'shot-002').clip.media, null, 'the original model is not changed');

  assert.equal(setMedia(m, 'shot-002', '   '), null, 'an empty path links nothing');
  assert.equal(setMedia(m, 'nope', '/a.mov'), null);
  assert.equal(findClip(setMedia(m, 'shot-002', '/a.mov', -5), 'shot-002').clip.media.start, 0);
  assert.equal(findClip(setMedia(m, 'shot-002', '/a.mov', 2.6), 'shot-002').clip.media.start, 3);

  assert.equal(findClip(clearMedia(linked, 'shot-002'), 'shot-002').clip.media, null);
  assert.equal(clearMedia(linked, 'nope'), null);
});

test('a placeholder slate is not linked media', () => {
  assert.equal(isLinked(null), false);
  assert.equal(isLinked({ url: 'file:///x/slate.mov', start: 0, duration: 10, key: 'griptape:slate:abc' }), false);
  assert.equal(isLinked({ url: '/x/plate.mov', start: 0, duration: null, key: '' }), true);
});

test('trimming the start of a linked clip moves where it begins in the file', () => {
  const m = setMedia(model(), 'shot-002', '/media/plate.mov', 100);
  const trimmed = trimClip(m, 'shot-002', 'start', 130);
  const clip = findClip(trimmed, 'shot-002').clip;
  assert.equal(clip.start, 130);
  assert.equal(clip.media.start, 130, 'it began 100 frames in, and the clip start moved later by 30');
  const earlier = trimClip(m, 'shot-002', 'start', 100, {});
  assert.equal(findClip(earlier, 'shot-002').clip.media.start, 100, 'nothing moved, so nothing changed');
});

test('a linked clip cannot be trimmed earlier than the start of its file', () => {
  const base = model();
  findClip(base, 'shot-001').clip.duration = 50; // leave a gap before shot-002, so it has room to grow earlier
  const m = setMedia(base, 'shot-002', '/media/plate.mov', 10); // 10 frames into the file
  const t = trimClip(m, 'shot-002', 'start', 60);
  assert.equal(findClip(t, 'shot-002').clip.start, 100 - 10, 'it can only grow back by 10 frames');
  assert.equal(findClip(t, 'shot-002').clip.media.start, 0);
});

test('trimming the start of a placeholder clip leaves its media alone', () => {
  const m = model();
  findClip(m, 'shot-002').clip.media = { url: 'file:///x/slate.mov', start: 24, duration: 200, key: 'griptape:slate:abc' };
  const t = trimClip(m, 'shot-002', 'start', 130);
  assert.equal(findClip(t, 'shot-002').clip.media.start, 24);
});

test('splitting a linked clip keeps the link, and the second half starts later in the file', () => {
  const m = setMedia(model(), 'shot-001', '/media/plate.mov', 20);
  const s = splitClip(m, 'shot-001', 40);
  const first = findClip(s, 'shot-001').clip;
  const second = findClip(s, 'shot-001-b').clip;
  assert.equal(first.media.url, '/media/plate.mov');
  assert.equal(first.media.start, 20);
  assert.equal(second.media.url, '/media/plate.mov');
  assert.equal(second.media.start, 60, 'the cut was 40 frames in, so it begins 40 frames later in the file');
});

test('splitting a placeholder clip still gives the second half no media', () => {
  const m = model();
  findClip(m, 'shot-001').clip.media = { url: 'file:///x/slate.mov', start: 24, duration: 200, key: 'griptape:slate:abc' };
  assert.equal(findClip(splitClip(m, 'shot-001', 40), 'shot-001-b').clip.media, null);
});

import { isStale, slateText } from '../../otio_nodes/widgets/TimelineEditor/_ops.js';

function withSlate(m, id, shown) {
  findClip(m, id).clip.media = { url: 'file:///x/slate.mov', start: 0, duration: 200, key: 'griptape:slate:abc', shown };
  return m;
}

test('the slate text is the name, the sequence and heading, and the description', () => {
  const m = model();
  const c = findClip(m, 'shot-001').clip;
  c.name = '001 Shot';
  c.description = 'JONH jumps out of bed.';
  assert.deepEqual(slateText(c), { title: '001 Shot', subtitle: 'SQ01  INT. ROOM - DAY', body: 'JONH jumps out of bed.' });
  c.meta.sequence = null;
  assert.equal(slateText(c).subtitle, 'INT. ROOM - DAY');
});

test('a slate is stale once the text it was made from has changed', () => {
  const m = model();
  const c = findClip(m, 'shot-001').clip;
  withSlate(m, 'shot-001', slateText(c));
  assert.equal(isStale(c), false, 'up to date');

  c.description = 'New words.';
  assert.equal(isStale(c), true, 'the description changed');
  c.description = '';
  c.name = 'Renamed';
  assert.equal(isStale(c), true, 'the name changed');
});

test('only a placeholder slate that records its text can be stale', () => {
  const m = model();
  const c = findClip(m, 'shot-001').clip;
  c.description = 'Words that differ from anything recorded.';
  assert.equal(isStale(c), false, 'no media');
  c.media = { url: 'file:///x/slate.mov', start: 0, duration: 200, key: 'griptape:slate:abc' };
  assert.equal(isStale(c), false, 'a slate from before the text was recorded cannot be judged');
  c.media = { url: '/media/plate.mov', start: 0, duration: null, key: '', shown: { title: 'x', subtitle: 'x', body: 'x' } };
  assert.equal(isStale(c), false, 'linked media is a file of its own, not a drawing of the text');
});

test('a slate is up to date again once it is remade with the new text', () => {
  const m = model();
  const c = findClip(m, 'shot-001').clip;
  withSlate(m, 'shot-001', slateText(c));
  c.description = 'New words.';
  assert.equal(isStale(c), true);
  c.media.shown = slateText(c);
  assert.equal(isStale(c), false);
});

import { editPoints, nextEdit, previousEdit, siblingClip } from '../../otio_nodes/widgets/TimelineEditor/_ops.js';

test('edit points are every start and end, in order, once', () => {
  assert.deepEqual(editPoints(model()), [0, 10, 60, 100, 110, 150, 200, 300]);
  assert.deepEqual(editPoints({ tracks: [] }), []);
});

test('previous and next edit point are strictly before and after', () => {
  const points = editPoints(model());
  assert.equal(nextEdit(points, 0), 10);
  assert.equal(nextEdit(points, 10), 60, 'from a point, the next one is the point after it');
  assert.equal(nextEdit(points, 105), 110);
  assert.equal(nextEdit(points, 300), null, 'nothing after the end');
  assert.equal(previousEdit(points, 300), 200);
  assert.equal(previousEdit(points, 105), 100);
  assert.equal(previousEdit(points, 0), null, 'nothing before the start');
});

test('the previous and next clip are on the same track', () => {
  const m = model();
  assert.equal(siblingClip(m, 'shot-002', 1).id, 'shot-003');
  assert.equal(siblingClip(m, 'shot-002', -1).id, 'shot-001');
  assert.equal(siblingClip(m, 'shot-003', 1), null, 'no clip after the last one');
  assert.equal(siblingClip(m, 'shot-001', -1), null, 'no clip before the first one');
  assert.equal(siblingClip(m, 'line-001', 1).id, 'line-002', 'a dialogue clip steps along its own speaker track');
  assert.equal(siblingClip(m, 'nope', 1), null);
});

test('muting a track only marks that track, and unmuting removes the mark', () => {
  const m = model();
  const sfx = m.tracks.find((t) => t.role === 'sfx');
  const muted = setTrackMuted(m, sfx.id, true);
  assert.equal(muted.tracks.find((t) => t.id === sfx.id).muted, true);
  assert.equal(muted.tracks.filter((t) => t.muted).length, 1);
  assert.equal('muted' in m.tracks.find((t) => t.id === sfx.id), false, 'the input is not changed');
  const back = setTrackMuted(muted, sfx.id, false);
  assert.equal('muted' in back.tracks.find((t) => t.id === sfx.id), false);
  assert.equal(setTrackMuted(m, 'no-such-track', true), null);
});

test('only unmuted, enabled, linked audio clips under the playhead are heard', () => {
  const m = model();
  const track = m.tracks.find((t) => t.role === 'dialogue');
  const clip = track.clips[0];
  clip.media = { url: '{inputs}/line.wav', start: 24, duration: null, key: '' };
  assert.deepEqual(audibleAt(m, clip.start), [], 'no preview URL yet');
  m.previews = { '{inputs}/line.wav': 'http://x/line.m4a' };
  const heard = audibleAt(m, clip.start + 1);
  assert.equal(heard.length, 1);
  assert.equal(heard[0].url, 'http://x/line.m4a');
  assert.deepEqual(audibleAt(m, clip.start + clip.duration), [], 'not after the clip ends');
  clip.enabled = false;
  assert.deepEqual(audibleAt(m, clip.start + 1), []);
  clip.enabled = true;
  track.muted = true;
  assert.deepEqual(audibleAt(m, clip.start + 1), [], 'a muted track is silent');
  track.muted = false;
  clip.media = { url: 'slate.mov', start: 0, duration: 9, key: 'griptape:silence' };
  m.previews['slate.mov'] = 'http://x/slate.mp4';
  assert.deepEqual(audibleAt(m, clip.start + 1), [], 'placeholder media makes no sound');
  const shot = m.tracks[0].clips[0];
  shot.media = { url: '{inputs}/plate.mov', start: 0, duration: null, key: '' };
  m.previews['{inputs}/plate.mov'] = 'http://x/plate.mp4';
  assert.deepEqual(audibleAt(m, shot.start + 1), [], 'video tracks are not played as sound');
});

test('a linked clip cannot be trimmed past the end of its file', () => {
  const linked = clip('a', 0, 24);
  linked.media = { url: '/plate.mov', start: 10, duration: 50, key: '' };
  const model = { rate: 24, tracks: [{ id: 't', name: 'T', kind: 'video', role: 'shots', clips: [linked] }], markers: [] };
  const trimmed = trimClip(model, 'a', 'end', 500);
  assert.equal(findClip(trimmed, 'a').clip.duration, 40);
  assert.ok(validate({ ...model, tracks: [{ ...model.tracks[0], clips: [{ ...linked, duration: 41 }] }] }).length > 0);
});

test('a placeholder slate may be outgrown, because saving makes a new one', () => {
  const slate = clip('a', 0, 24);
  slate.media = { url: 'file:///s.mov', start: 0, duration: 24, key: 'griptape:slate:abc' };
  const model = { rate: 24, tracks: [{ id: 't', name: 'T', kind: 'video', role: 'shots', clips: [slate] }], markers: [] };
  assert.equal(findClip(trimClip(model, 'a', 'end', 100), 'a').clip.duration, 100);
});
