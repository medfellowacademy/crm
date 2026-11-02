// Celebration sound for the office TV, synthesised with the Web Audio API so there is no file to host
// or license: a short fanfare, then applause. A target milestone gets the longer, bigger version.
// `ctx` is any AudioContext (an OfflineAudioContext works too, which is how it is tested).

const NOTE = { C4: 261.63, E4: 329.63, G4: 392, C5: 523.25, E5: 659.25, G5: 783.99, C6: 1046.5, E6: 1318.5, G6: 1568 };

function tone(ctx, out, freq, start, dur, { type = 'triangle', gain = 0.22 } = {}) {
  const o = ctx.createOscillator();
  const g = ctx.createGain();
  o.type = type;
  o.frequency.value = freq;
  g.gain.setValueAtTime(0.0001, start);
  g.gain.exponentialRampToValueAtTime(gain, start + 0.03);
  g.gain.exponentialRampToValueAtTime(0.0001, start + dur);
  o.connect(g);
  g.connect(out);
  o.start(start);
  o.stop(start + dur + 0.05);
}

// Crowd clapping: filtered noise made of many tiny random bursts, swelling then fading.
function applause(ctx, out, start, seconds) {
  const rate = ctx.sampleRate;
  const len = Math.floor(rate * seconds);
  const buf = ctx.createBuffer(1, len, rate);
  const d = buf.getChannelData(0);
  let clap = 0;
  for (let i = 0; i < len; i += 1) {
    if (Math.random() < 0.0016) clap = 1;               // a new clap
    clap *= 0.9965;                                     // dies away quickly
    d[i] = (Math.random() * 2 - 1) * clap;
  }
  const src = ctx.createBufferSource();
  src.buffer = buf;
  const band = ctx.createBiquadFilter();
  band.type = 'bandpass';
  band.frequency.value = 2200;
  band.Q.value = 0.6;
  const g = ctx.createGain();
  g.gain.setValueAtTime(0.0001, start);
  g.gain.exponentialRampToValueAtTime(0.9, start + seconds * 0.2);
  g.gain.setValueAtTime(0.9, start + seconds * 0.6);
  g.gain.exponentialRampToValueAtTime(0.0001, start + seconds);
  src.connect(band);
  band.connect(g);
  g.connect(out);
  src.start(start);
}

// Returns how long the sound lasts, in seconds.
export function playCelebration(ctx, { big = false } = {}) {
  const t0 = ctx.currentTime + 0.05;
  const master = ctx.createGain();
  master.gain.value = 0.6;
  master.connect(ctx.destination);

  // run-up: C E G C
  [NOTE.C5, NOTE.E5, NOTE.G5, NOTE.C6].forEach((f, i) => tone(ctx, master, f, t0 + i * 0.11, 0.35, { type: 'triangle', gain: 0.24 }));

  // the hit: a full major chord with a low root underneath
  const hit = t0 + 0.5;
  [NOTE.C4, NOTE.E4, NOTE.G4].forEach((f) => tone(ctx, master, f, hit, 1.3, { type: 'sawtooth', gain: 0.07 }));
  [NOTE.C5, NOTE.E5, NOTE.G5, NOTE.C6].forEach((f) => tone(ctx, master, f, hit, 1.4, { type: 'triangle', gain: 0.18 }));

  let end = hit + 1.4;
  if (big) {                                            // second flourish going up, held longer
    [NOTE.G5, NOTE.C6, NOTE.E6, NOTE.G6].forEach((f, i) => tone(ctx, master, f, hit + 1.2 + i * 0.12, 0.5, { type: 'triangle', gain: 0.22 }));
    const finale = hit + 1.8;
    [NOTE.C4, NOTE.E4, NOTE.G4].forEach((f) => tone(ctx, master, f, finale, 2, { type: 'sawtooth', gain: 0.08 }));
    [NOTE.C5, NOTE.E5, NOTE.G5, NOTE.C6, NOTE.E6].forEach((f) => tone(ctx, master, f, finale, 2.1, { type: 'triangle', gain: 0.17 }));
    end = finale + 2.1;
  }

  const clapSeconds = big ? 5 : 3;
  applause(ctx, master, hit + 0.05, clapSeconds);
  return Math.max(end, hit + clapSeconds) - t0;
}
