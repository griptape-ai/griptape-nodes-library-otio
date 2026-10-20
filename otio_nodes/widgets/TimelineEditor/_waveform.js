// Waveforms for the audio clips. The viewer copy of a linked file is fetched and decoded once, then reduced to a peak
// per small slice of time. A clip draws the part of those peaks that it shows, so trimming and zooming never decode
// again. A file that cannot be fetched or decoded gets no waveform.

const PEAKS_PER_SECOND = 200; // the aim. The real rate depends on the file's sample rate and is stored with the peaks
const MAX_CANVAS_WIDTH = 8192;
const CURVE = 0.6; // below 1 lifts the quiet parts so speech between loud peaks stays visible
const WAVE_COLOR = 'rgba(0,0,0,.55)';

export function createWaveforms(onReady) {
  const cache = new Map(); // url -> {peaks: Float32Array, rate: peaks per second} when decoded, null when it failed, or 'loading'

  async function load(url) {
    cache.set(url, 'loading');
    try {
      const response = await fetch(url);
      const bytes = await response.arrayBuffer();
      const buffer = await new OfflineAudioContext(1, 1, 44100).decodeAudioData(bytes);
      const slice = Math.max(1, Math.floor(buffer.sampleRate / PEAKS_PER_SECOND));
      const peaks = new Float32Array(Math.ceil(buffer.length / slice));
      for (let channel = 0; channel < buffer.numberOfChannels; channel++) {
        const data = buffer.getChannelData(channel);
        for (let i = 0; i < peaks.length; i++) {
          const end = Math.min(data.length, (i + 1) * slice);
          for (let j = i * slice; j < end; j++) {
            const value = Math.abs(data[j]);
            if (value > peaks[i]) peaks[i] = value;
          }
        }
      }
      // Scale so the loudest slice fills the clip. A quiet file would otherwise draw as a thin line.
      const loudest = peaks.reduce((max, value) => Math.max(max, value), 0);
      if (loudest > 0) for (let i = 0; i < peaks.length; i++) peaks[i] = Math.pow(peaks[i] / loudest, CURVE);
      cache.set(url, { peaks, rate: buffer.sampleRate / slice });
    } catch {
      cache.set(url, null);
    }
    onReady();
  }

  // A canvas showing `seconds` of the file from `offset`, or null while the file is not decoded yet.
  function canvasFor(doc, url, offset, seconds, width, height) {
    if (!url) return null;
    const found = cache.get(url);
    if (found === undefined) load(url);
    if (!found || found === 'loading') return null;
    const canvas = doc.createElement('canvas');
    canvas.className = 'otl-wave';
    canvas.width = Math.max(1, Math.min(MAX_CANVAS_WIDTH, Math.round(width)));
    canvas.height = height;
    const context = canvas.getContext('2d');
    context.fillStyle = WAVE_COLOR;
    const mid = height / 2;
    const { peaks, rate } = found;
    for (let x = 0; x < canvas.width; x++) {
      const from = Math.floor((offset + (x / canvas.width) * seconds) * rate);
      const to = Math.max(from + 1, Math.floor((offset + ((x + 1) / canvas.width) * seconds) * rate));
      let peak = 0;
      for (let i = from; i < to && i < peaks.length; i++) if (peaks[i] > peak) peak = peaks[i];
      const half = Math.max(peak > 0 ? 1 : 0, peak * mid);
      context.fillRect(x, mid - half, 1, half * 2);
    }
    return canvas;
  }

  return { canvasFor };
}
