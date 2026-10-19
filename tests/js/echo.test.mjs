import assert from 'node:assert/strict';
import { test } from 'node:test';

import { classifyIncoming, heldEntry, takePreviews } from '../../otio_nodes/widgets/TimelineEditor/_echo.js';

const timeline = (start, extra = {}) => ({ rate: 24, tracks: [{ id: 't', clips: [{ id: 'a', start, duration: 24 }] }], markers: [], ...extra });

// The widget sent the timeline with the clip at 0, then dropped it at 100 and sent that.
const state = (overrides = {}) => ({
  model: timeline(100),
  held: [heldEntry(timeline(0)), heldEntry(timeline(100))],
  awaitingEcho: true,
  lastSendAt: 1000,
  now: 1100,
  ...overrides,
});

test('the timeline the widget holds comes back unchanged', () => {
  assert.equal(classifyIncoming({ ...state(), incoming: timeline(100) }), 'same');
});

test('the same timeline with new preview progress only brings the previews', () => {
  const incoming = timeline(100, { preparing: { 'plate.mov': 0.4 } });
  assert.equal(classifyIncoming({ ...state(), incoming }), 'previews');
});

test('an older timeline arriving after a drop is ignored', () => {
  assert.equal(classifyIncoming({ ...state(), incoming: timeline(0) }), 'stale');
});

test('an older timeline carrying new preview progress keeps the widget timeline and takes the progress', () => {
  const incoming = timeline(0, { preparing: { 'plate.mov': 0.4 } });
  assert.equal(classifyIncoming({ ...state(), incoming }), 'stalePreviews');
});

test('an older timeline is taken once the latest send has come back', () => {
  assert.equal(classifyIncoming({ ...state({ awaitingEcho: false }), incoming: timeline(0) }), 'replace');
});

test('an older timeline is taken after the wait has run out', () => {
  assert.equal(classifyIncoming({ ...state({ now: 5000 }), incoming: timeline(0) }), 'replace');
});

test('a timeline the widget never sent replaces its own', () => {
  assert.equal(classifyIncoming({ ...state(), incoming: timeline(300) }), 'replace');
});

test('with no timeline yet, anything is taken', () => {
  assert.equal(classifyIncoming({ ...state({ model: null }), incoming: timeline(0) }), 'replace');
});

test('previews are copied over and missing ones are removed', () => {
  const model = timeline(100, { previews: { a: 'x' }, preparing: { b: 0.1 } });
  takePreviews(model, { previews: { a: 'y' } });
  assert.deepEqual(model.previews, { a: 'y' });
  assert.equal('preparing' in model, false);
});

test('an older timeline with preview progress is ignored even after the latest send came back', () => {
  const incoming = timeline(0, { preparing: { 'plate.mov': 0.4 } });
  assert.equal(classifyIncoming({ ...state({ awaitingEcho: false, now: 3000 }), incoming }), 'stalePreviews');
});

test('an older timeline with preview progress is taken once enough time has passed', () => {
  const incoming = timeline(0, { preparing: { 'plate.mov': 0.4 } });
  assert.equal(classifyIncoming({ ...state({ awaitingEcho: false, now: 9000 }), incoming }), 'replace');
});

test('a late echo of an older send does not roll back newer preview state', () => {
  // Both sends carried preparing {a}. The preview thread then finished the copy, so the widget holds previews {a}.
  const sentPreparing = (start) => timeline(start, { preparing: { a: 0.5 } });
  const held = [heldEntry(sentPreparing(0)), heldEntry(sentPreparing(100))];
  const model = timeline(100, { previews: { a: 'http://x/a.mp4' } });
  const echo = classifyIncoming({ incoming: sentPreparing(0), model, held, awaitingEcho: true, lastSendAt: 1000, now: 1100 });
  assert.equal(echo, 'stale', 'ignored whole, so its older preview keys are not taken');
});
