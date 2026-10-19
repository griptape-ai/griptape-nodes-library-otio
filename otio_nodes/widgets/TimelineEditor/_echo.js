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
// An update carrying preview keys comes from the node's preview thread, not from the echo of a send. It is built from
// the timeline as the node had it, and it can arrive any time after an edit, even after the echo has come back.
export const STALE_PREVIEW_MS = 5000;

// The timeline as text, without the preview keys.
export const withoutPreviews = (model) => JSON.stringify({ ...model, previews: undefined, preparing: undefined, preview_errors: undefined });

// The preview keys of a timeline, as text.
export const previewsOf = (model) => JSON.stringify(PREVIEW_KEYS.map((key) => model[key] || null));

// What the widget remembers about a timeline it sent: the timeline without its preview keys, and the preview keys it
// had then. An echo of that send carries both unchanged. An update from the node's preview thread carries the same
// timeline with different preview keys.
export const heldEntry = (model) => ({ bare: withoutPreviews(model), previews: previewsOf(model) });

// What to do with `incoming`:
//   'same'          it is the timeline the widget holds, preview keys included.
//   'previews'      it is the timeline the widget holds, with different preview keys. Take the preview keys.
//   'stale'         it is the echo of an older send, exactly as sent, and either the latest send has not come back or
//                   it was sent soon after an edit. Ignore it. Its preview keys are older than the widget's.
//   'stalePreviews' it is an older timeline the widget sent but with preview keys it never sent, so it comes from the
//                   node's preview thread. Keep the widget's timeline and take the preview keys.
//   'replace'       anything else. The node sent a timeline of its own, so it replaces the widget's.
// `held` lists heldEntry() of what the widget has sent, oldest first, the latest last.
export function classifyIncoming({ incoming, model, held, awaitingEcho, lastSendAt, now }) {
  if (!model) return 'replace';
  const bare = withoutPreviews(incoming);
  if (bare === withoutPreviews(model)) return JSON.stringify(incoming) === JSON.stringify(model) ? 'same' : 'previews';
  const older = held.slice(0, -1).filter((entry) => entry.bare === bare);
  if (older.length === 0) return 'replace';
  const sinceSend = now - lastSendAt;
  const fromPreviewThread = PREVIEW_KEYS.some((key) => incoming[key]);
  const recent = (awaitingEcho && sinceSend < STALE_ECHO_MS) || (fromPreviewThread && sinceSend < STALE_PREVIEW_MS);
  if (!recent) return 'replace';
  const sent = older.some((entry) => entry.previews === previewsOf(incoming));
  return sent ? 'stale' : 'stalePreviews';
}

// Copy the preview keys of `incoming` onto `model`, removing the ones `incoming` does not have.
export function takePreviews(model, incoming) {
  for (const key of PREVIEW_KEYS) {
    if (incoming[key]) model[key] = structuredClone(incoming[key]);
    else delete model[key];
  }
}
