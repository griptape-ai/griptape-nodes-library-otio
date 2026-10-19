import assert from 'node:assert/strict';
import { test } from 'node:test';

import { classifyIncoming, takePreviews, withoutPreviews } from '../../otio_nodes/widgets/TimelineEditor/_echo.js';

const timeline = (start, extra = {}) => ({ rate: 24, tracks: [{ id: 't', clips: [{ id: 'a', start, duration: 24 }] }], markers: [], ...extra });

// The widget sent the timeline with the clip at 0, then dropped it at 100 and sent that.
const state = (overrides = {}) => ({
  model: timeline(100),
  held: [withoutPreviews(timeline(0)), withoutPreviews(timeline(100))],
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

test('an older timeline carrying new preview progress is still ignored', () => {
  const incoming = timeline(0, { preparing: { 'plate.mov': 0.4 } });
  assert.equal(classifyIncoming({ ...state(), incoming }), 'stale');
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
