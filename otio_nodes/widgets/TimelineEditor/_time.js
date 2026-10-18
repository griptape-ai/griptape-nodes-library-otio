// Time helpers for the timeline editor. All times are whole frames.

export function frameToTimecode(frame, rate) {
  const fps = Math.max(1, Math.round(rate));
  const total = Math.max(0, Math.round(frame));
  const ff = total % fps;
  const seconds = Math.floor(total / fps);
  const ss = seconds % 60;
  const mm = Math.floor(seconds / 60) % 60;
  const hh = Math.floor(seconds / 3600);
  const pad = (n) => String(n).padStart(2, '0');
  return `${pad(hh)}:${pad(mm)}:${pad(ss)}:${pad(ff)}`;
}

export function formatSeconds(frames, rate) {
  const seconds = frames / rate;
  const minutes = Math.floor(seconds / 60);
  const rest = seconds - minutes * 60;
  return minutes > 0 ? `${minutes}:${rest.toFixed(1).padStart(4, '0')}` : `${rest.toFixed(1)} s`;
}

const STEPS_SECONDS = [0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300, 600];

// Pick the spacing between ruler labels, in frames, so labels sit at least minPx apart.
export function rulerStepFrames(pxPerFrame, rate, minPx = 90) {
  for (const seconds of STEPS_SECONDS) {
    const frames = Math.round(seconds * rate);
    if (frames * pxPerFrame >= minPx) return frames;
  }
  return Math.round(STEPS_SECONDS[STEPS_SECONDS.length - 1] * rate);
}

export function clamp(value, low, high) {
  return Math.min(high, Math.max(low, value));
}
