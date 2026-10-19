// Deciding what to do with a timeline the node sends to the widget. No DOM code.
//
// The node hands back what the widget sends, a little later. Until the latest message has come back, it may first hand
// back an older one, and adopting that would pull the timeline back to where it was for a moment (a dropped clip
// jumping back, then forward). The node also reports the progress of viewer copies inside the same value, and such an
// update can be built from the timeline as it was just before a drop. So an incoming value is compared without the
// preview keys: the preview keys are always taken, and the rest of the timeline is only replaced when the value is not
// an older one this widget sent.

export const PREVIEW_KEYS = ['previews', 'preparing', 'preview_errors'];
export const STALE_ECHO_MS = 2000;

// The timeline as text, without the preview keys. This is what the widget remembers about what it sent.
export const withoutPreviews = (model) => JSON.stringify({ ...model, previews: undefined, preparing: undefined, preview_errors: undefined });

// What to do with `incoming`:
//   'same'     it is the timeline the widget holds, preview keys included.
//   'previews' it is the timeline the widget holds, with different preview keys. Take the preview keys.
//   'stale'    it is an older timeline this widget sent, while the latest send has not come back. Keep the widget's
//              timeline and take the preview keys.
//   'replace'  anything else. The node sent a timeline of its own, so it replaces the widget's.
// `held` lists withoutPreviews() of what the widget has sent, oldest first, the latest last.
export function classifyIncoming({ incoming, model, held, awaitingEcho, lastSendAt, now }) {
  if (!model) return 'replace';
  const bare = withoutPreviews(incoming);
  if (bare === withoutPreviews(model)) return JSON.stringify(incoming) === JSON.stringify(model) ? 'same' : 'previews';
  if (awaitingEcho && now - lastSendAt < STALE_ECHO_MS && held.slice(0, -1).includes(bare)) return 'stale';
  return 'replace';
}

// Copy the preview keys of `incoming` onto `model`, removing the ones `incoming` does not have.
export function takePreviews(model, incoming) {
  for (const key of PREVIEW_KEYS) {
    if (incoming[key]) model[key] = structuredClone(incoming[key]);
    else delete model[key];
  }
}
