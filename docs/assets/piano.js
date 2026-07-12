/* Disco piano — playable, oscillator-synth (no external samples).
   Builds keys, handles pointer + keyboard input, draws a little disco-floor
   pulse on press. */
(function () {
  const piano = document.getElementById('piano');
  if (!piano) return;

  const OCTAVES = 3;
  const START_OCTAVE = 4; // keyboard now spans C4..B6 to match the song's range
  const WHITE = ['C', 'D', 'E', 'F', 'G', 'A', 'B'];
  const BLACK = ['C#', 'D#', null, 'F#', 'G#', 'A#', null];
  const SEMI = { 'C': -9, 'C#': -8, 'D': -7, 'D#': -6, 'E': -5, 'F': -4,
                 'F#': -3, 'G': -2, 'G#': -1, 'A': 0, 'A#': 1, 'B': 2 };
  const midi = (n, o) => 60 + SEMI[n] + (o - 4) * 12;
  const freq = m => 440 * Math.pow(2, (m - 69) / 12);

  const COLORS = ['#FF2D8E', '#FF6B1A', '#F5B711', '#0CC4D9', '#7B2CBF', '#D81B60'];

  let idx = 0;
  for (let o = 0; o < OCTAVES; o++) {
    for (let i = 0; i < WHITE.length; i++) {
      const oct = START_OCTAVE + o;
      const el = document.createElement('div');
      el.className = 'key white';
      el.dataset.midi = midi(WHITE[i], oct);
      el.dataset.note = WHITE[i] + oct;
      el.style.setProperty('--key-color', COLORS[idx % COLORS.length]);
      el.setAttribute('tabindex', '0');
      el.setAttribute('role', 'button');
      el.setAttribute('aria-label', WHITE[i] + oct);
      piano.appendChild(el);
      idx++;
    }
  }

  // Black keys absolutely positioned over the whites.
  // Must stay in sync with .key.white / .key.black widths in CSS.
  const WHITE_W = 68, BLACK_W = 42;
  let bIdx = 0;
  for (let o = 0; o < OCTAVES; o++) {
    for (let i = 0; i < BLACK.length; i++) {
      const note = BLACK[i];
      if (!note) continue;
      const oct = START_OCTAVE + o;
      const wAbs = o * 7 + i;
      const left = (wAbs + 1) * WHITE_W - BLACK_W / 2;
      const el = document.createElement('div');
      el.className = 'key black';
      el.dataset.midi = midi(note, oct);
      el.dataset.note = note + oct;
      el.style.left = left + 'px';
      el.style.setProperty('--key-color', COLORS[(bIdx + 3) % COLORS.length]);
      el.setAttribute('tabindex', '0');
      el.setAttribute('role', 'button');
      el.setAttribute('aria-label', note + oct);
      piano.appendChild(el);
      bIdx++;
    }
  }

  // ─── Audio ───
  // `muted` = user explicitly muted via the mute button.
  // `audioReady` = browser's autoplay policy unlocked AND the AudioContext is
  // running. Until the first user gesture, audioReady is false and the mute
  // button shows "tap to start" rather than the lying "sound on".
  let ctx = null, muted = false, audioReady = false;
  let reverbBus = null; // shared wet send — connect each note's gain here
  const getCtx = () => {
    if (!ctx) {
      ctx = new (window.AudioContext || window.webkitAudioContext)();
      setupReverb();
    }
    return ctx;
  };
  function markAudioReady() {
    if (audioReady) return;
    audioReady = true;
    const btn = document.getElementById('muteBtn');
    if (btn && !muted) btn.textContent = 'sound on';
  }

  // Synthetic impulse-response convolution reverb. Generates a stereo noise
  // burst with exponential decay — sounds like a smallish hall. No IR file
  // needed. Tune REVERB_* constants below to taste.
  const REVERB_SECONDS = 2.4;  // decay tail length
  const REVERB_DECAY   = 2.5;  // larger = faster decay
  const REVERB_WET     = 0;    // 0 = bone dry, 1 = drenched
  const REVERB_LOWPASS = 5200; // Hz — tames metallic high tail
  function setupReverb() {
    const c = ctx;
    // Build the IR
    const len = Math.floor(REVERB_SECONDS * c.sampleRate);
    const ir = c.createBuffer(2, len, c.sampleRate);
    for (let ch = 0; ch < 2; ch++) {
      const data = ir.getChannelData(ch);
      for (let i = 0; i < len; i++) {
        data[i] = (Math.random() * 2 - 1) * Math.pow(1 - i / len, REVERB_DECAY);
      }
    }
    const convolver = c.createConvolver();
    convolver.buffer = ir;
    const lp = c.createBiquadFilter();
    lp.type = 'lowpass';
    lp.frequency.value = REVERB_LOWPASS;
    const wet = c.createGain();
    wet.gain.value = REVERB_WET;
    // Per-note gains will connect here; this bus pipes into the wet chain.
    reverbBus = c.createGain();
    reverbBus.gain.value = 1;
    reverbBus.connect(convolver);
    convolver.connect(lp);
    lp.connect(wet);
    wet.connect(c.destination);
  }

  // ─── Voice switching: oscillator synth (default) or one of several
  // multisampled instruments. Samples lazy-load; in-between notes use Web
  // Audio playbackRate (semitone-shift via 2^(diff/12)). ───
  const NOTE_NAMES_FLAT = ['C','Cs','D','Ds','E','F','Fs','G','Gs','A','As','B'];
  const noteName = m => `${NOTE_NAMES_FLAT[m%12]}${Math.floor(m/12)-1}.mp3`;
  // Each voice declares a base URL and the MIDI numbers it has samples for.
  // nbrosowsky/tonejs-instruments hosts the public-domain pack.
  const TJI = 'https://nbrosowsky.github.io/tonejs-instruments/samples/';
  // `gain` per voice normalizes sample loudness. Measured via ffmpeg
  // volumedetect on each voice's middle sample; chosen so all voices land
  // around the same perceived loudness without clipping.
  const VOICES = {
    salamander: {
      base: 'https://tonejs.github.io/audio/salamander/',
      midis: [48,51,54,57,60,63,66,69,72,75,78,81,84],
      nameFor: noteName,
      gain: 1.33, // measured -34.7dB mean at C3
    },
    xylophone: {
      base: TJI + 'xylophone/',
      // Only G4(67), C5(72), G5(79), C6(84), G6(91), C7(96). Sparse — big pitch shifts below G4.
      midis: [67,72,79,84,91,96],
      nameFor: noteName,
      gain: 0.6, // measured -32.2dB mean at G4, but transient peaks read loud
    },
    harp: {
      base: TJI + 'harp/',
      // Only A2(45), A4(69), A6(93). Very sparse — expect chipmunk artefacts on outliers.
      midis: [45,69,93],
      nameFor: noteName,
      gain: 0.38, // measured -23.7dB mean at A2
    },
    guitarElectric: {
      base: TJI + 'guitar-electric/',
      // A2,A3,A4,A5,C3,C4,C5,C6,Cs2,Ds3,Ds4,Ds5,E2,Fs2,Fs3,Fs4,Fs5
      midis: [37,40,42,45,48,51,54,57,60,63,66,69,72,75,78,81,84],
      nameFor: noteName,
      gain: 0.62, // measured -28dB mean at C3
    },
  };
  const sampleBuffers = {};
  const sampleLoading = {};
  Object.keys(VOICES).forEach(v => { sampleBuffers[v] = {}; sampleLoading[v] = null; });
  let currentVoice = 'salamander';

  async function loadVoice(voice) {
    if (voice === 'synth' || !VOICES[voice]) return;
    // Marketing-site CSP (`connect-src 'self' https://calendly.com`) blocks
    // external sample CDNs. Short-circuit here so voice buttons cleanly fall
    // through to the per-voice synth profiles below instead of spewing
    // ERR_BLOCKED_BY_CSP warnings. Each voice now sounds distinct via
    // SYNTH_PROFILES — no CDN dependency.
    return;
  }

  function nearestSampleMidi(target, midis) {
    let best = midis[0], bestDiff = Math.abs(target - best);
    for (const m of midis) {
      const d = Math.abs(target - m);
      if (d < bestDiff) { best = m; bestDiff = d; }
    }
    return best;
  }

  function playSample(voice, midi, releaseS, gainScale) {
    const cfg = VOICES[voice];
    const buffers = sampleBuffers[voice];
    const nearest = nearestSampleMidi(midi, cfg.midis);
    const buf = buffers[nearest];
    if (!buf) return; // not yet loaded — silently skip this note
    const c = getCtx();
    if (c.state === 'suspended') c.resume();
    const now = c.currentTime;
    const gs = gainScale == null ? 1 : gainScale;
    // base 0.45 leaves headroom for chord stacking; cfg.gain normalizes
    // across voices; gs differentiates melody (1.0) vs chord notes (~0.22).
    const peak = 0.45 * (cfg.gain ?? 1) * gs;
    // Per-voice release shortens sustain for naturally-long samples (organ).
    const effRelease = releaseS != null ? releaseS * (cfg.releaseMul ?? 1) : null;
    const src = c.createBufferSource();
    src.buffer = buf;
    src.playbackRate.value = Math.pow(2, (midi - nearest) / 12);
    const g = c.createGain();
    g.gain.setValueAtTime(peak, now);
    const duration = effRelease != null ? effRelease : buf.duration;
    if (effRelease != null && effRelease < buf.duration) {
      g.gain.setValueAtTime(peak, now + Math.max(0, effRelease - 0.08));
      g.gain.linearRampToValueAtTime(0, now + effRelease);
    }
    src.connect(g);
    g.connect(c.destination);
    if (reverbBus) g.connect(reverbBus); // wet send
    src.start(now);
    src.stop(now + duration + 0.1);
  }

  // Per-voice synth profiles. Each voice picks distinct oscillator stack +
  // envelope + optional filter so xylophone ≠ harp ≠ guitarElectric ≠
  // salamander piano. No CDN dependency — CSP stays tight.
  //   oscs[].type: 'sine' | 'square' | 'sawtooth' | 'triangle'
  //   oscs[].mult: frequency multiplier (1=fundamental, 2=octave-up, 0.5=down)
  //   oscs[].gain: mix level (relative to master peak)
  //   attack:     seconds to reach peak
  //   percussive: true = ramp to silence within `decay` sec (xylo/harp/guitar)
  //               false = sustain until `releaseMul * releaseS` (piano)
  //   filter:     optional biquad — frequency = f * mult (clamped 18kHz)
  const SYNTH_PROFILES = {
    salamander: {
      oscs: [
        { type: 'triangle', mult: 1.0,  gain: 1.00 },
        { type: 'sine',     mult: 2.01, gain: 0.08 },
        { type: 'sine',     mult: 0.5,  gain: 0.18 },
      ],
      attack: 0.012, percussive: false, releaseMul: 1.0, peak: 0.28,
      filter: null,
    },
    xylophone: {
      // Bright wooden bar — fast square attack + high triangle partial +
      // metallic sine shimmer, narrow bandpass = pingy, percussive decay.
      oscs: [
        { type: 'square',   mult: 1.0,  gain: 0.55 },
        { type: 'triangle', mult: 3.0,  gain: 0.32 },
        { type: 'sine',     mult: 5.99, gain: 0.16 },
      ],
      attack: 0.001, percussive: true, decay: 0.42, releaseMul: 0.35,
      peak: 0.34, filter: { type: 'bandpass', mult: 4, Q: 5 },
    },
    harp: {
      // Plucked string — sine fundamental + sawtooth high partial + sine
      // fifth, gentle lowpass, plucky percussive decay (longer than xylo).
      oscs: [
        { type: 'sine',     mult: 1.0,  gain: 1.00 },
        { type: 'sawtooth', mult: 2.0,  gain: 0.10 },
        { type: 'sine',     mult: 3.0,  gain: 0.05 },
      ],
      attack: 0.003, percussive: true, decay: 1.4, releaseMul: 1.0,
      peak: 0.28, filter: { type: 'lowpass', mult: 6, Q: 1.5 },
    },
    guitarElectric: {
      // Dirty sawtooth fundamental + square sub-octave + triangle upper grit,
      // resonant lowpass (Q=7) for filter-sweep electric character.
      oscs: [
        { type: 'sawtooth', mult: 1.0,  gain: 0.85 },
        { type: 'square',   mult: 0.5,  gain: 0.18 },
        { type: 'triangle', mult: 2.0,  gain: 0.20 },
      ],
      attack: 0.005, percussive: true, decay: 0.9, releaseMul: 0.7,
      peak: 0.24, filter: { type: 'lowpass', mult: 4, Q: 7 },
    },
    synth: {
      // Classic analog lead — sawtooth + square detuned unison, no filter,
      // sustained release. Bright, buzzy, distinct from the warm-piano voice.
      oscs: [
        { type: 'sawtooth', mult: 1.0,    gain: 0.65 },
        { type: 'square',   mult: 1.005,  gain: 0.30 },
        { type: 'sawtooth', mult: 0.5,    gain: 0.22 },
      ],
      attack: 0.008, percussive: false, releaseMul: 0.85, peak: 0.22,
      filter: null,
    },
  };

  function playSynth(m, releaseS, gainScale) {
    const r = Math.max(0.18, releaseS == null ? 1.6 : releaseS);
    const gs = gainScale == null ? 1 : gainScale;
    const profile = SYNTH_PROFILES[currentVoice] || SYNTH_PROFILES.salamander;
    const c = getCtx();
    if (c.state === 'suspended') c.resume();
    const now = c.currentTime;
    const f = freq(m);
    const effR = r * profile.releaseMul;
    const peak = profile.peak * gs;

    // Master gain with ADR envelope. Percussive = ramp to silence within
    // `decay` sec; sustained = exponential decay across full release window.
    const g = c.createGain();
    g.gain.setValueAtTime(0.0001, now);
    g.gain.exponentialRampToValueAtTime(Math.max(0.001, peak), now + profile.attack);
    let totalLen;
    if (profile.percussive) {
      g.gain.exponentialRampToValueAtTime(0.0001, now + profile.attack + profile.decay);
      totalLen = profile.attack + profile.decay;
    } else {
      g.gain.exponentialRampToValueAtTime(0.0001, now + effR);
      totalLen = effR;
    }

    // Optional filter sits between master gain and destination/reverb send.
    let outNode = g;
    if (profile.filter) {
      const filt = c.createBiquadFilter();
      filt.type = profile.filter.type;
      filt.frequency.value = Math.min(18000, f * profile.filter.mult);
      filt.Q.value = profile.filter.Q;
      g.connect(filt);
      outNode = filt;
    }

    // Oscillator stack — each osc routed through its own gain into master.
    const oscs = [];
    for (const o of profile.oscs) {
      const osc = c.createOscillator();
      osc.type = o.type;
      osc.frequency.value = f * o.mult;
      const og = c.createGain();
      og.gain.value = o.gain;
      osc.connect(og);
      og.connect(g);
      oscs.push(osc);
    }

    outNode.connect(c.destination);
    if (reverbBus) outNode.connect(reverbBus); // wet send

    const stopAt = now + totalLen + 0.15;
    oscs.forEach(o => { o.start(now); o.stop(stopAt); });
  }

  function play(m, releaseS, gainScale) {
    if (muted) return;
    if (currentVoice === 'synth' || !sampleBuffers[currentVoice] ||
        Object.keys(sampleBuffers[currentVoice]).length === 0) {
      playSynth(m, releaseS, gainScale);
    } else {
      playSample(currentVoice, m, releaseS, gainScale);
    }
  }

  // Browsers gate AudioContext until first user gesture. Unlock as soon as
  // ANY interaction lands on the page so the looping melody picks up sound
  // mid-cycle without requiring a key press specifically.
  const unlockAudio = () => {
    const c = getCtx();
    if (c.state === 'suspended') {
      c.resume().then(markAudioReady).catch(() => {});
    } else {
      markAudioReady();
    }
  };
  document.addEventListener('pointerdown', unlockAudio, { once: true, capture: true });
  document.addEventListener('keydown', unlockAudio, { once: true, capture: true });

  // ─── Floor pulse ───
  function pulseFloor(color) {
    const floor = document.getElementById('floor-pulse');
    if (!floor) return;
    floor.style.setProperty('--pulse-color', color);
    floor.classList.remove('on');
    // restart animation
    void floor.offsetWidth;
    floor.classList.add('on');
  }

  const hint = document.getElementById('piano-hint');
  let firstHit = true;
  function pressKey(el) {
    if (!el) return;
    stopDemo();
    const m = parseInt(el.dataset.midi, 10);
    play(m);
    el.classList.add('pressed');
    pulseFloor(getComputedStyle(el).getPropertyValue('--key-color').trim());
    setTimeout(() => el.classList.remove('pressed'), 320);
    if (firstHit) {
      firstHit = false;
      hint && hint.classList.add('gone');
    }
  }

  // ─── Section-based song loader, ~100 BPM, visual + audio. Each section
  // carries its own key+scale plus melody notes and (optionally) chords.
  // Chords play as a soft pad in the lower register under the melody. ───
  const BPM = 100;
  const BEAT_MS = 60000 / BPM;
  const TAIL_BEATS = 1; // breath at loop point only — sections are seamless

  const NOTE_OFFSETS = {
    'C':0,'C#':1,'Db':1,'D':2,'D#':3,'Eb':3,'E':4,
    'F':5,'F#':6,'Gb':6,'G':7,'G#':8,'Ab':8,'A':9,
    'A#':10,'Bb':10,'B':11,
  };
  const SCALES = {
    major:           [0,2,4,5,7,9,11],
    minor:           [0,2,3,5,7,8,10],
    dorian:          [0,2,3,5,7,9,10],
    phrygian:        [0,1,3,5,7,8,10],
    lydian:          [0,2,4,6,7,9,11],
    mixolydian:      [0,2,4,5,7,9,10],
    locrian:         [0,1,3,5,6,8,10],
    'harmonic minor':[0,2,3,5,7,8,11],
    'melodic minor': [0,2,3,5,7,9,11],
  };
  const OCTAVE_OFFSET = 0; // global pitch shift in octaves; -1 = drop one
  function tonicOct0(tonic) {
    return 60 + (NOTE_OFFSETS[tonic] ?? 0) + OCTAVE_OFFSET * 12;
  }
  function sdToMidi(sd, oct, tonic, scale) {
    const intervals = SCALES[(scale || 'major').toLowerCase()] || SCALES.major;
    return tonicOct0(tonic) + intervals[parseInt(sd, 10) - 1] + oct * 12;
  }
  // Chord type 5 = triad, 7 = seventh, etc. Voice in the octave BELOW
  // tonic-0 so the chord sits under the melody. Apply inversion last.
  function chordToMidis(ch, tonic, scale) {
    const intervals = SCALES[(scale || 'major').toLowerCase()] || SCALES.major;
    const tonicMidi = tonicOct0(tonic) - 12; // start one octave below
    const toneCount = ch.type >= 9 ? 4 : (ch.type === 7 ? 4 : 3);
    const tones = [];
    for (let i = 0; i < toneCount; i++) {
      const sdIdx = (ch.root - 1) + i * 2;          // root, third, fifth, (seventh)
      const oct = Math.floor(sdIdx / 7);
      const semi = intervals[sdIdx % 7];
      tones.push(tonicMidi + semi + oct * 12);
    }
    let voiced = tones.slice();
    const inv = ch.inversion || 0;
    for (let i = 0; i < inv; i++) {
      const head = voiced.shift();
      voiced.push(head + 12);
    }
    return voiced;
  }

  // Song sections in order. Add more by appending here.
  const HERO_SECTIONS = [
    // 1 — Intro (D major), sparse melody + sustained Bm-D-Bm-F#m-G-Bm-G-F#m
    {
      tonic: 'D', scale: 'major',
      notes: [
        {sd:'6',octave:0,beat:1,duration:0.75},{sd:'6',octave:0,beat:1.75,duration:0.75},
        {sd:'6',octave:0,beat:2.5,duration:1}, {sd:'5',octave:0,beat:3.5,duration:0.75},
        {sd:'5',octave:0,beat:4.25,duration:0.75},{sd:'6',octave:0,beat:5,duration:0.75},
        {sd:'6',octave:0,beat:5.75,duration:0.75},{sd:'6',octave:0,beat:6.5,duration:1},
        {sd:'3',octave:0,beat:7.5,duration:0.75},{sd:'3',octave:0,beat:8.25,duration:0.75},
        {sd:'4',octave:0,beat:9,duration:0.75},  {sd:'4',octave:0,beat:9.75,duration:0.75},
        {sd:'4',octave:0,beat:10.5,duration:1},  {sd:'3',octave:0,beat:11.5,duration:0.75},
        {sd:'3',octave:0,beat:12.25,duration:0.75},{sd:'4',octave:0,beat:13,duration:0.75},
        {sd:'4',octave:0,beat:13.75,duration:0.75},{sd:'4',octave:0,beat:14.5,duration:1},
        {sd:'3',octave:0,beat:15.5,duration:0.75},{sd:'3',octave:0,beat:16.25,duration:0.75},
      ],
      chords: [
        {root:6,beat:1,duration:2.5,type:5,inversion:1},
        {root:1,beat:3.5,duration:1.5,type:5,inversion:0},
        {root:6,beat:5,duration:2.5,type:5,inversion:1},
        {root:3,beat:7.5,duration:1.5,type:5,inversion:1},
        {root:4,beat:9,duration:2.5,type:5,inversion:1},
        {root:6,beat:11.5,duration:1.5,type:5,inversion:0},
        {root:4,beat:13,duration:2.5,type:5,inversion:1},
        {root:3,beat:15.5,duration:1.5,type:5,inversion:1},
      ],
    },
    // 2 — Verse / Pre-Chorus (D major) — full chord stabs underneath
    {
      tonic: 'D', scale: 'major',
      notes: [
        {sd:'1',octave:0,beat:1,duration:1,isRest:true},
        {sd:'1',octave:1,beat:2,duration:1},{sd:'7',octave:0,beat:3,duration:1},
        {sd:'5',octave:0,beat:4,duration:0.5},{sd:'5',octave:0,beat:4.5,duration:0.5},
        {sd:'3',octave:0,beat:5,duration:1},
        {sd:'1',octave:0,beat:6,duration:1.5,isRest:true},
        {sd:'1',octave:0,beat:7.5,duration:0.5},{sd:'1',octave:0,beat:8,duration:0.5},
        {sd:'1',octave:0,beat:8.5,duration:0.5},{sd:'5',octave:0,beat:9,duration:0.5},
        {sd:'5',octave:0,beat:9.5,duration:0.5},{sd:'1',octave:0,beat:10,duration:0.5},
        {sd:'1',octave:0,beat:10.5,duration:0.5},{sd:'5',octave:0,beat:11,duration:0.5},
        {sd:'5',octave:0,beat:11.5,duration:0.5},{sd:'7',octave:-1,beat:12,duration:1},
        {sd:'6',octave:-1,beat:13,duration:3},
        {sd:'1',octave:0,beat:16,duration:2,isRest:true},
        {sd:'1',octave:1,beat:18,duration:0.5},{sd:'1',octave:1,beat:18.5,duration:0.5},
        {sd:'7',octave:0,beat:19,duration:0.75},{sd:'5',octave:0,beat:19.75,duration:0.75},
        {sd:'5',octave:0,beat:20.5,duration:1},{sd:'3',octave:0,beat:21.5,duration:1},
        {sd:'1',octave:0,beat:22.5,duration:1,isRest:true},
        {sd:'1',octave:0,beat:23.5,duration:0.5},{sd:'1',octave:0,beat:24,duration:0.5},
        {sd:'1',octave:0,beat:24.5,duration:0.5},{sd:'5',octave:0,beat:25,duration:0.5},
        {sd:'5',octave:0,beat:25.5,duration:0.5},{sd:'1',octave:0,beat:26,duration:0.5},
        {sd:'1',octave:0,beat:26.5,duration:0.5},{sd:'5',octave:0,beat:27,duration:0.5},
        {sd:'5',octave:0,beat:27.5,duration:0.5},{sd:'6',octave:0,beat:28,duration:2},
        {sd:'5',octave:0,beat:30,duration:0.5},{sd:'1',octave:0,beat:30.5,duration:1.5},
        {sd:'1',octave:0,beat:32,duration:2,isRest:true},
        {sd:'1',octave:1,beat:34,duration:1},{sd:'7',octave:0,beat:35,duration:1},
        {sd:'5',octave:0,beat:36,duration:0.5},{sd:'5',octave:0,beat:36.5,duration:0.5},
      ],
      chords: [
        {root:6,beat:5,duration:0.75,type:5,inversion:1},
        {root:6,beat:5.75,duration:0.75,type:5,inversion:1},
        {root:6,beat:6.5,duration:1,type:5,inversion:1},
        {root:1,beat:7.5,duration:0.75,type:5,inversion:0},
        {root:1,beat:8.25,duration:0.75,type:5,inversion:0},
        {root:6,beat:9,duration:0.75,type:5,inversion:1},
        {root:6,beat:9.75,duration:0.75,type:5,inversion:1},
        {root:6,beat:10.5,duration:1,type:5,inversion:1},
        {root:3,beat:11.5,duration:0.75,type:5,inversion:1},
        {root:3,beat:12.25,duration:0.75,type:5,inversion:1},
        {root:4,beat:13,duration:0.75,type:5,inversion:1},
        {root:4,beat:13.75,duration:0.75,type:5,inversion:1},
        {root:4,beat:14.5,duration:1,type:5,inversion:1},
        {root:6,beat:15.5,duration:0.75,type:5,inversion:0},
        {root:6,beat:16.25,duration:0.75,type:5,inversion:0},
        {root:4,beat:17,duration:0.75,type:5,inversion:1},
        {root:4,beat:17.75,duration:0.75,type:5,inversion:1},
        {root:4,beat:18.5,duration:1,type:5,inversion:1},
        {root:3,beat:19.5,duration:0.75,type:5,inversion:1},
        {root:3,beat:20.25,duration:0.75,type:5,inversion:1},
        {root:6,beat:21,duration:0.75,type:5,inversion:1},
        {root:6,beat:21.75,duration:0.75,type:5,inversion:1},
        {root:6,beat:22.5,duration:1,type:5,inversion:1},
        {root:1,beat:23.5,duration:0.75,type:5,inversion:0},
        {root:1,beat:24.25,duration:0.75,type:5,inversion:0},
        {root:6,beat:25,duration:0.75,type:5,inversion:1},
        {root:6,beat:25.75,duration:0.75,type:5,inversion:1},
        {root:6,beat:26.5,duration:1,type:5,inversion:1},
        {root:3,beat:27.5,duration:0.75,type:5,inversion:1},
        {root:3,beat:28.25,duration:0.75,type:5,inversion:1},
        {root:4,beat:29,duration:0.75,type:5,inversion:1},
        {root:4,beat:29.75,duration:0.75,type:5,inversion:1},
        {root:4,beat:30.5,duration:1,type:5,inversion:1},
        {root:6,beat:31.5,duration:0.75,type:5,inversion:0},
        {root:6,beat:32.25,duration:0.75,type:5,inversion:0},
        {root:4,beat:33,duration:0.75,type:5,inversion:1},
        {root:4,beat:33.75,duration:0.75,type:5,inversion:1},
        {root:4,beat:34.5,duration:1,type:5,inversion:1},
        {root:3,beat:35.5,duration:0.75,type:5,inversion:1},
        {root:3,beat:36.25,duration:0.75,type:5,inversion:1},
      ],
    },
    // 3 — Chorus (D major) — V → vi → I → IV (A-Bm-D-G) hook
    {
      tonic: 'D', scale: 'major',
      notes: [
        {sd:'3',octave:0,beat:1,duration:1.5},{sd:'2',octave:0,beat:2.5,duration:1.5},
        {sd:'2',octave:0,beat:4,duration:0.5},{sd:'1',octave:0,beat:4.5,duration:0.5},
        {sd:'1',octave:0,beat:5,duration:0.5},{sd:'2',octave:0,beat:5.5,duration:0.5},
        {sd:'3',octave:0,beat:6,duration:0.5},{sd:'2',octave:0,beat:6.5,duration:1},
        {sd:'6',octave:-1,beat:7.5,duration:0.5},{sd:'1',octave:0,beat:8,duration:3},
        {sd:'1',octave:0,beat:11,duration:3,isRest:true},
        {sd:'1',octave:1,beat:14,duration:1},{sd:'7',octave:0,beat:15,duration:1},
        {sd:'5',octave:0,beat:16,duration:0.5},{sd:'5',octave:0,beat:16.5,duration:0.5},
        {sd:'3',octave:0,beat:17,duration:1.5},{sd:'2',octave:0,beat:18.5,duration:1.5},
        {sd:'2',octave:0,beat:20,duration:0.5},{sd:'1',octave:0,beat:20.5,duration:0.5},
        {sd:'1',octave:0,beat:21,duration:0.5},{sd:'2',octave:0,beat:21.5,duration:0.5},
        {sd:'3',octave:0,beat:22,duration:0.5},{sd:'2',octave:0,beat:22.5,duration:1},
        {sd:'6',octave:-1,beat:23.5,duration:0.5},{sd:'1',octave:0,beat:24,duration:3},
      ],
      chords: [
        {root:5,beat:1,duration:0.75,type:5,inversion:0},
        {root:5,beat:1.75,duration:0.75,type:5,inversion:0},
        {root:5,beat:2.5,duration:1,type:5,inversion:0},
        {root:5,beat:3.5,duration:0.75,type:5,inversion:0},
        {root:5,beat:4.25,duration:0.75,type:5,inversion:0},
        {root:6,beat:5,duration:0.75,type:5,inversion:0},
        {root:6,beat:5.75,duration:0.75,type:5,inversion:0},
        {root:6,beat:6.5,duration:1,type:5,inversion:0},
        {root:1,beat:7.5,duration:0.75,type:5,inversion:1},
        {root:1,beat:8.25,duration:0.75,type:5,inversion:1},
        {root:4,beat:9,duration:0.75,type:5,inversion:0},
        {root:4,beat:9.75,duration:0.75,type:5,inversion:0},
        {root:4,beat:10.5,duration:1,type:5,inversion:0},
        {root:1,beat:11.5,duration:0.75,type:5,inversion:1},
        {root:1,beat:12.25,duration:0.75,type:5,inversion:1},
        {root:4,beat:13,duration:0.75,type:5,inversion:0},
        {root:4,beat:13.75,duration:0.75,type:5,inversion:0},
        {root:4,beat:14.5,duration:1,type:5,inversion:0},
        {root:1,beat:15.5,duration:0.75,type:5,inversion:1},
        {root:1,beat:16.25,duration:0.75,type:5,inversion:0},
        {root:5,beat:17,duration:0.75,type:5,inversion:0},
        {root:5,beat:17.75,duration:0.75,type:5,inversion:0},
        {root:5,beat:18.5,duration:1,type:5,inversion:0},
        {root:5,beat:19.5,duration:0.75,type:5,inversion:0},
        {root:5,beat:20.25,duration:0.75,type:5,inversion:0},
        {root:6,beat:21,duration:0.75,type:5,inversion:0},
        {root:6,beat:21.75,duration:0.75,type:5,inversion:0},
        {root:6,beat:22.5,duration:1,type:5,inversion:0},
        {root:1,beat:23.5,duration:0.75,type:5,inversion:1},
        {root:1,beat:24.25,duration:0.75,type:5,inversion:1},
        {root:4,beat:25,duration:0.75,type:5,inversion:0},
        {root:4,beat:25.75,duration:0.75,type:5,inversion:0},
        {root:4,beat:26.5,duration:1,type:5,inversion:0},
        {root:1,beat:27.5,duration:0.75,type:5,inversion:1},
        {root:1,beat:28.25,duration:0.75,type:5,inversion:1},
        {root:4,beat:29,duration:0.75,type:5,inversion:0},
        {root:4,beat:29.75,duration:0.75,type:5,inversion:0},
        {root:4,beat:30.5,duration:1,type:5,inversion:0},
        {root:1,beat:31.5,duration:0.75,type:5,inversion:0},
        {root:1,beat:32.25,duration:0.75,type:5,inversion:0},
      ],
    },
    // 4 — Chorus hook "don't you worry / child" (D major, high register)
    {
      tonic: 'D', scale: 'major',
      notes: [
        {sd:'1',octave:0,beat:1,duration:2.5,isRest:true},
        {sd:'1',octave:1,beat:3.5,duration:0.5},{sd:'1',octave:1,beat:4,duration:0.5},
        {sd:'6',octave:0,beat:4.5,duration:0.5},{sd:'1',octave:1,beat:5,duration:0.5},
        {sd:'6',octave:0,beat:5.5,duration:0.5},{sd:'1',octave:1,beat:6,duration:0.5},
        {sd:'6',octave:0,beat:6.5,duration:0.5},{sd:'1',octave:1,beat:7,duration:1},
        {sd:'1',octave:1,beat:8,duration:0.5},{sd:'2',octave:1,beat:8.5,duration:2.5},
        {sd:'1',octave:0,beat:11,duration:0.5,isRest:true},
        {sd:'1',octave:1,beat:11.5,duration:0.5},{sd:'1',octave:1,beat:12,duration:0.5},
        {sd:'6',octave:0,beat:12.5,duration:0.5},{sd:'1',octave:1,beat:13,duration:0.5},
        {sd:'6',octave:0,beat:13.5,duration:0.5},{sd:'1',octave:1,beat:14,duration:1},
        {sd:'1',octave:1,beat:15,duration:1},{sd:'2',octave:1,beat:16,duration:1},
        {sd:'1',octave:1,beat:17,duration:0.5},{sd:'6',octave:0,beat:17.5,duration:1.5},
        {sd:'1',octave:0,beat:19,duration:0.5,isRest:true},
        {sd:'1',octave:1,beat:19.5,duration:0.5},{sd:'1',octave:1,beat:20,duration:0.5},
        {sd:'6',octave:0,beat:20.5,duration:0.5},{sd:'1',octave:1,beat:21,duration:0.5},
        {sd:'6',octave:0,beat:21.5,duration:0.5},{sd:'1',octave:1,beat:22,duration:0.5},
        {sd:'6',octave:0,beat:22.5,duration:0.5},{sd:'1',octave:1,beat:23,duration:1},
        {sd:'1',octave:1,beat:24,duration:0.5},{sd:'2',octave:1,beat:24.5,duration:4},
        {sd:'1',octave:1,beat:28.5,duration:1},
        {sd:'1',octave:0,beat:29.5,duration:1,isRest:true},
        {sd:'1',octave:1,beat:30.5,duration:0.5},{sd:'1',octave:1,beat:31,duration:0.5},
        {sd:'1',octave:1,beat:31.5,duration:0.5},{sd:'1',octave:1,beat:32,duration:1},
      ],
      chords: [
        {root:6,beat:1,duration:0.75,type:5,inversion:1},
        {root:6,beat:1.75,duration:0.75,type:5,inversion:1},
        {root:6,beat:2.5,duration:1,type:5,inversion:1},
        {root:1,beat:3.5,duration:0.75,type:5,inversion:0},
        {root:1,beat:4.25,duration:0.75,type:5,inversion:0},
        {root:6,beat:5,duration:0.75,type:5,inversion:1},
        {root:6,beat:5.75,duration:0.75,type:5,inversion:1},
        {root:6,beat:6.5,duration:1,type:5,inversion:1},
        {root:3,beat:7.5,duration:0.75,type:5,inversion:1},
        {root:3,beat:8.25,duration:0.75,type:5,inversion:1},
        {root:4,beat:9,duration:0.75,type:5,inversion:1},
        {root:4,beat:9.75,duration:0.75,type:5,inversion:1},
        {root:4,beat:10.5,duration:1,type:5,inversion:1},
        {root:6,beat:11.5,duration:0.75,type:5,inversion:0},
        {root:6,beat:12.25,duration:0.75,type:5,inversion:0},
        {root:4,beat:13,duration:0.75,type:5,inversion:1},
        {root:4,beat:13.75,duration:0.75,type:5,inversion:1},
        {root:4,beat:14.5,duration:1,type:5,inversion:1},
        {root:3,beat:15.5,duration:0.75,type:5,inversion:1},
        {root:3,beat:16.25,duration:0.75,type:5,inversion:1},
        {root:6,beat:17,duration:0.75,type:5,inversion:1},
        {root:6,beat:17.75,duration:0.75,type:5,inversion:1},
        {root:6,beat:18.5,duration:1,type:5,inversion:1},
        {root:1,beat:19.5,duration:0.75,type:5,inversion:0},
        {root:1,beat:20.25,duration:0.75,type:5,inversion:0},
        {root:6,beat:21,duration:0.75,type:5,inversion:1},
        {root:6,beat:21.75,duration:0.75,type:5,inversion:1},
        {root:6,beat:22.5,duration:1,type:5,inversion:1},
        {root:3,beat:23.5,duration:0.75,type:5,inversion:1},
        {root:3,beat:24.25,duration:0.75,type:5,inversion:1},
        {root:4,beat:25,duration:0.75,type:5,inversion:1},
        {root:4,beat:25.75,duration:0.75,type:5,inversion:1},
        {root:4,beat:26.5,duration:1,type:5,inversion:1},
        {root:6,beat:27.5,duration:0.75,type:5,inversion:0},
        {root:6,beat:28.25,duration:0.75,type:5,inversion:0},
        {root:4,beat:29,duration:0.75,type:5,inversion:1},
        {root:4,beat:29.75,duration:0.75,type:5,inversion:1},
        {root:4,beat:30.5,duration:1,type:5,inversion:1},
        {root:3,beat:31.5,duration:0.75,type:5,inversion:1},
        {root:3,beat:32.25,duration:0.75,type:5,inversion:1},
      ],
    },
    // 5 — Final chorus / outro pad (D major), V-vi-I-IV sustained, high melody
    {
      tonic: 'D', scale: 'major',
      notes: [
        {sd:'7',octave:0,beat:1,duration:1.5},
        {sd:'1',octave:0,beat:2.5,duration:1.5,isRest:true},
        {sd:'1',octave:1,beat:4,duration:0.5},{sd:'1',octave:1,beat:4.5,duration:0.5},
        {sd:'5',octave:1,beat:5,duration:0.5},{sd:'5',octave:1,beat:5.5,duration:0.5},
        {sd:'1',octave:1,beat:6,duration:0.5},{sd:'1',octave:1,beat:6.5,duration:0.5},
        {sd:'5',octave:1,beat:7,duration:0.5},{sd:'5',octave:1,beat:7.5,duration:0.5},
        {sd:'1',octave:1,beat:8,duration:1},  {sd:'6',octave:0,beat:9,duration:2},
        {sd:'1',octave:0,beat:11,duration:1.5,isRest:true},
        {sd:'1',octave:1,beat:12.5,duration:0.5},{sd:'1',octave:1,beat:13,duration:0.5},
        {sd:'1',octave:1,beat:13.5,duration:0.5},{sd:'1',octave:1,beat:14,duration:0.5},
        {sd:'1',octave:1,beat:14.5,duration:0.5},{sd:'4',octave:1,beat:15,duration:0.75},
        {sd:'3',octave:1,beat:15.75,duration:0.75},{sd:'2',octave:1,beat:16.5,duration:3},
        {sd:'1',octave:0,beat:19.5,duration:0.5,isRest:true},
        {sd:'1',octave:1,beat:20,duration:0.5},{sd:'1',octave:1,beat:20.5,duration:0.5},
        {sd:'5',octave:1,beat:21,duration:0.5},{sd:'5',octave:1,beat:21.5,duration:0.5},
        {sd:'1',octave:1,beat:22,duration:0.5},{sd:'1',octave:1,beat:22.5,duration:0.5},
        {sd:'5',octave:1,beat:23,duration:0.5},{sd:'5',octave:1,beat:23.5,duration:0.5},
        {sd:'1',octave:1,beat:24,duration:1},  {sd:'6',octave:0,beat:25,duration:3.5},
        {sd:'1',octave:1,beat:28.5,duration:4.5},
      ],
      chords: [
        {root:5,beat:1,duration:4,type:5,inversion:0},
        {root:6,beat:5,duration:2.5,type:5,inversion:0},
        {root:1,beat:7.5,duration:1.5,type:5,inversion:1},
        {root:4,beat:9,duration:2.5,type:5,inversion:0},
        {root:1,beat:11.5,duration:1.5,type:5,inversion:1},
        {root:4,beat:13,duration:2.5,type:5,inversion:0},
        {root:1,beat:15.5,duration:1.5,type:5,inversion:0},
        {root:5,beat:17,duration:4,type:5,inversion:0},
        {root:6,beat:21,duration:2.5,type:5,inversion:0},
        {root:1,beat:23.5,duration:1.5,type:5,inversion:1},
        {root:4,beat:25,duration:2.5,type:5,inversion:0},
        {root:1,beat:27.5,duration:1.5,type:5,inversion:1},
        {root:4,beat:29,duration:2.5,type:5,inversion:0},
        {root:1,beat:31.5,duration:1.5,type:5,inversion:0},
      ],
    },
    // 6 — Big final chorus payoff (D major), stabbed V-vi + I-IV, top-of-piano melody
    {
      tonic: 'D', scale: 'major',
      notes: [
        {sd:'7',octave:0,beat:1,duration:0.75},{sd:'7',octave:0,beat:1.75,duration:0.75},
        {sd:'7',octave:0,beat:2.5,duration:1}, {sd:'6',octave:0,beat:3.5,duration:0.75},
        {sd:'7',octave:0,beat:4.25,duration:0.75},{sd:'1',octave:1,beat:5,duration:0.75},
        {sd:'1',octave:1,beat:5.75,duration:0.75},{sd:'1',octave:1,beat:6.5,duration:1},
        {sd:'5',octave:0,beat:7.5,duration:0.75},{sd:'3',octave:0,beat:8.25,duration:0.75},
        {sd:'6',octave:0,beat:9,duration:0.75},  {sd:'6',octave:0,beat:9.75,duration:0.75},
        {sd:'6',octave:0,beat:10.5,duration:1},  {sd:'5',octave:0,beat:11.5,duration:0.75},
        {sd:'3',octave:0,beat:12.25,duration:0.75},{sd:'6',octave:0,beat:13,duration:0.75},
        {sd:'6',octave:0,beat:13.75,duration:0.75},{sd:'6',octave:0,beat:14.5,duration:1},
        {sd:'5',octave:0,beat:15.5,duration:0.75},{sd:'1',octave:1,beat:16.25,duration:0.75},
        {sd:'7',octave:0,beat:17,duration:0.75},  {sd:'7',octave:0,beat:17.75,duration:0.75},
        {sd:'7',octave:0,beat:18.5,duration:1},   {sd:'6',octave:0,beat:19.5,duration:0.75},
        {sd:'7',octave:0,beat:20.25,duration:0.75},{sd:'1',octave:1,beat:21,duration:0.75},
        {sd:'1',octave:1,beat:21.75,duration:0.75},{sd:'1',octave:1,beat:22.5,duration:1},
        {sd:'5',octave:1,beat:23.5,duration:0.75},{sd:'3',octave:1,beat:24.25,duration:0.75},
        {sd:'6',octave:1,beat:25,duration:0.75},  {sd:'6',octave:1,beat:25.75,duration:0.75},
        {sd:'6',octave:1,beat:26.5,duration:1},   {sd:'5',octave:1,beat:27.5,duration:0.75},
        {sd:'3',octave:1,beat:28.25,duration:0.75},{sd:'6',octave:1,beat:29,duration:0.75},
        {sd:'6',octave:1,beat:29.75,duration:0.75},{sd:'6',octave:1,beat:30.5,duration:1},
        {sd:'2',octave:1,beat:31.5,duration:0.75},{sd:'1',octave:1,beat:32.25,duration:0.75},
      ],
      chords: [
        {root:5,beat:1,duration:2.5,type:5,inversion:0},
        {root:6,beat:3.5,duration:0.75,type:5,inversion:2},
        {root:5,beat:4.25,duration:0.75,type:5,inversion:0},
        {root:6,beat:5,duration:2.5,type:5,inversion:0},
        {root:1,beat:7.5,duration:1.5,type:5,inversion:1},
        {root:4,beat:9,duration:2.5,type:5,inversion:0},
        {root:1,beat:11.5,duration:1.5,type:5,inversion:1},
        {root:4,beat:13,duration:2.5,type:5,inversion:0},
        {root:1,beat:15.5,duration:0.75,type:5,inversion:1},
        {root:1,beat:16.25,duration:0.75,type:5,inversion:0},
        {root:5,beat:17,duration:2.5,type:5,inversion:0},
        {root:6,beat:19.5,duration:0.75,type:5,inversion:2},
        {root:5,beat:20.25,duration:0.75,type:5,inversion:0},
        {root:6,beat:21,duration:2.5,type:5,inversion:0},
        {root:1,beat:23.5,duration:1.5,type:5,inversion:0},
        {root:4,beat:25,duration:2.5,type:5,inversion:0},
        {root:1,beat:27.5,duration:1.5,type:5,inversion:0},
        {root:4,beat:29,duration:2.5,type:5,inversion:0},
        {root:1,beat:31.5,duration:0.75,type:5,inversion:1},
        {root:1,beat:32.25,duration:0.75,type:5,inversion:0},
      ],
    },
    // 7 — Drop / final chorus arp (D major), sustained V-vi-I-IV with 8th-note lead (×2)
    {
      tonic: 'D', scale: 'major',
      repeat: 2,
      notes: [
        {sd:'7',octave:0,beat:1,duration:0.5},  {sd:'2',octave:0,beat:1.5,duration:0.5},
        {sd:'6',octave:0,beat:2,duration:0.5},  {sd:'7',octave:0,beat:2.5,duration:0.5},
        {sd:'2',octave:0,beat:3,duration:0.5},  {sd:'6',octave:0,beat:3.5,duration:0.5},
        {sd:'7',octave:0,beat:4,duration:0.5},  {sd:'2',octave:0,beat:4.5,duration:0.5},
        {sd:'7',octave:0,beat:5,duration:0.5},  {sd:'1',octave:1,beat:5.5,duration:0.5},
        {sd:'3',octave:0,beat:6,duration:0.5},  {sd:'7',octave:0,beat:6.5,duration:0.5},
        {sd:'1',octave:1,beat:7,duration:0.5},  {sd:'1',octave:0,beat:7.5,duration:0.5},
        {sd:'5',octave:0,beat:8,duration:0.5},  {sd:'6',octave:0,beat:8.5,duration:0.5},
        {sd:'1',octave:0,beat:9,duration:0.5},  {sd:'5',octave:0,beat:9.5,duration:0.5},
        {sd:'6',octave:0,beat:10,duration:0.5}, {sd:'1',octave:0,beat:10.5,duration:0.5},
        {sd:'5',octave:0,beat:11,duration:0.5}, {sd:'6',octave:0,beat:11.5,duration:0.5},
        {sd:'1',octave:0,beat:12,duration:0.5}, {sd:'6',octave:0,beat:12.5,duration:0.5},
        {sd:'1',octave:0,beat:13,duration:0.5}, {sd:'5',octave:0,beat:13.5,duration:0.5},
        {sd:'6',octave:0,beat:14,duration:0.5}, {sd:'1',octave:0,beat:14.5,duration:0.5},
        {sd:'5',octave:0,beat:15,duration:0.5}, {sd:'6',octave:0,beat:15.5,duration:0.5},
        {sd:'1',octave:0,beat:16,duration:0.5}, {sd:'1',octave:1,beat:16.5,duration:0.5},
        {sd:'7',octave:0,beat:17,duration:0.5}, {sd:'2',octave:0,beat:17.5,duration:0.5},
        {sd:'6',octave:0,beat:18,duration:0.5}, {sd:'7',octave:0,beat:18.5,duration:0.5},
        {sd:'2',octave:0,beat:19,duration:0.5}, {sd:'6',octave:0,beat:19.5,duration:0.5},
        {sd:'7',octave:0,beat:20,duration:0.5}, {sd:'2',octave:0,beat:20.5,duration:0.5},
        {sd:'7',octave:0,beat:21,duration:0.5}, {sd:'1',octave:1,beat:21.5,duration:0.5},
        {sd:'3',octave:0,beat:22,duration:0.5}, {sd:'7',octave:0,beat:22.5,duration:0.5},
        {sd:'1',octave:1,beat:23,duration:0.5}, {sd:'1',octave:0,beat:23.5,duration:0.5},
        {sd:'5',octave:0,beat:24,duration:0.5}, {sd:'6',octave:0,beat:24.5,duration:0.5},
        {sd:'1',octave:0,beat:25,duration:0.5}, {sd:'5',octave:0,beat:25.5,duration:0.5},
        {sd:'6',octave:0,beat:26,duration:0.5}, {sd:'1',octave:0,beat:26.5,duration:0.5},
        {sd:'5',octave:0,beat:27,duration:0.5}, {sd:'6',octave:0,beat:27.5,duration:0.5},
        {sd:'1',octave:0,beat:28,duration:0.5}, {sd:'6',octave:0,beat:28.5,duration:0.5},
        {sd:'1',octave:0,beat:29,duration:0.5}, {sd:'5',octave:0,beat:29.5,duration:0.5},
        {sd:'6',octave:0,beat:30,duration:0.5}, {sd:'1',octave:0,beat:30.5,duration:0.5},
        {sd:'5',octave:0,beat:31,duration:0.5}, {sd:'6',octave:0,beat:31.5,duration:0.5},
        {sd:'2',octave:1,beat:32,duration:0.5}, {sd:'1',octave:1,beat:32.5,duration:0.5},
      ],
      chords: [
        {root:5,beat:1,duration:4,type:5,inversion:0},
        {root:6,beat:5,duration:2.5,type:5,inversion:0},
        {root:1,beat:7.5,duration:1.5,type:5,inversion:1},
        {root:4,beat:9,duration:2.5,type:5,inversion:0},
        {root:1,beat:11.5,duration:1.5,type:5,inversion:1},
        {root:4,beat:13,duration:2.5,type:5,inversion:0},
        {root:1,beat:15.5,duration:1.5,type:5,inversion:0},
        {root:5,beat:17,duration:4,type:5,inversion:0},
        {root:6,beat:21,duration:2.5,type:5,inversion:0},
        {root:1,beat:23.5,duration:1.5,type:5,inversion:1},
        {root:4,beat:25,duration:2.5,type:5,inversion:0},
        {root:1,beat:27.5,duration:1.5,type:5,inversion:1},
        {root:4,beat:29,duration:2.5,type:5,inversion:0},
        {root:1,beat:31.5,duration:1.5,type:5,inversion:0},
      ],
    },
  ];

  // ─── Cover song — composite of 4 sections (F#, F#, F#, Ab) ───
  // Source: composer-tool blob exports concatenated sequentially.
  // Chord+melody only — no copyrightable material from original recordings.
  const COVER_SECTIONS = [
    // Cover 1 — F# major
    {
      label: 'Cover 1',
      tonic: 'F#', scale: 'major',
      notes: [
        {sd:'5',octave:-1,beat:2,duration:1},{sd:'5',octave:-1,beat:3,duration:1},{sd:'5',octave:-1,beat:4.5,duration:0.5},
        {sd:'5',octave:-1,beat:5,duration:1},{sd:'5',octave:-1,beat:6,duration:0.5},{sd:'6',octave:-1,beat:6.5,duration:0.25},
        {sd:'6',octave:-1,beat:6.75,duration:0.25},{sd:'7',octave:-1,beat:8,duration:0.5},{sd:'7',octave:-1,beat:8.5,duration:0.5},
        {sd:'1',octave:0,beat:9,duration:1},{sd:'7',octave:-1,beat:10,duration:0.5},{sd:'1',octave:0,beat:10.5,duration:1},
        {sd:'3',octave:0,beat:11.5,duration:1},{sd:'6',octave:-1,beat:12.5,duration:3},{sd:'5',octave:-1,beat:18,duration:0.75},
        {sd:'5',octave:-1,beat:18.75,duration:0.25},{sd:'6',octave:-1,beat:19,duration:0.5},{sd:'5',octave:-1,beat:19.5,duration:1},
        {sd:'5',octave:-1,beat:20.5,duration:0.5},{sd:'6',octave:-1,beat:21,duration:1},{sd:'5',octave:-1,beat:22,duration:0.5},
        {sd:'6',octave:-1,beat:22.5,duration:0.5},{sd:'7',octave:-1,beat:24,duration:0.5},{sd:'7',octave:-1,beat:24.5,duration:0.5},
        {sd:'1',octave:0,beat:25,duration:1},{sd:'7',octave:-1,beat:26,duration:0.5},{sd:'1',octave:0,beat:26.5,duration:1},
        {sd:'3',octave:0,beat:27.5,duration:1},{sd:'6',octave:-1,beat:28.5,duration:2.5},{sd:'4',octave:0,beat:33.5,duration:0.5},
        {sd:'4',octave:0,beat:34,duration:0.5},{sd:'4',octave:0,beat:34.5,duration:0.5},{sd:'4',octave:0,beat:35,duration:0.5},
        {sd:'3',octave:0,beat:35.5,duration:1},{sd:'3',octave:0,beat:36.5,duration:0.5},{sd:'2',octave:0,beat:37.5,duration:1},
        {sd:'2',octave:0,beat:38.5,duration:0.5},{sd:'5',octave:-1,beat:40,duration:0.5},{sd:'5',octave:-1,beat:40.5,duration:0.5},
        {sd:'3',octave:0,beat:41,duration:1},{sd:'3',octave:0,beat:42,duration:0.5},{sd:'5',octave:0,beat:42.5,duration:1},
        {sd:'3',octave:0,beat:43.5,duration:1},{sd:'2',octave:0,beat:44.5,duration:1},{sd:'1',octave:0,beat:45.5,duration:0.5},
        {sd:'2',octave:0,beat:46.5,duration:0.5},{sd:'1',octave:0,beat:47,duration:0.25},{sd:'6',octave:-1,beat:47.25,duration:0.25},
        {sd:'5',octave:-1,beat:48.5,duration:0.5},{sd:'4',octave:0,beat:49,duration:1},{sd:'4',octave:0,beat:50,duration:0.5},
        {sd:'3',octave:0,beat:50.5,duration:1},{sd:'2',octave:0,beat:51.5,duration:2},{sd:'3',octave:0,beat:54.5,duration:0.5},
        {sd:'2',octave:0,beat:55,duration:0.67},{sd:'2',octave:0,beat:55.67,duration:0.66},{sd:'3',octave:0,beat:56.33,duration:0.67},
        {sd:'1',octave:0,beat:57,duration:3},
      ],
      chords: [
        {root:5,beat:1,duration:8,type:5,inversion:0},{root:6,beat:9,duration:6,type:7,inversion:0},
        {root:2,beat:15,duration:1,type:7,inversion:0},{root:1,beat:16,duration:1,type:5,inversion:1},
        {root:5,beat:17,duration:8,type:5,inversion:0},{root:6,beat:25,duration:8,type:7,inversion:0},
        {root:2,beat:33,duration:3.5,type:7,inversion:0},{root:1,beat:36.5,duration:1,type:5,inversion:2},
        {root:5,beat:37.5,duration:3.5,type:5,inversion:0},{root:1,beat:41,duration:3.5,type:5,inversion:1},
        {root:5,beat:44.5,duration:1,type:7,inversion:3},{root:4,beat:45.5,duration:1,type:5,inversion:2},
        {root:4,beat:46.5,duration:2.5,type:5,inversion:0},{root:2,beat:49,duration:1.5,type:7,inversion:0},
        {root:1,beat:50.5,duration:1,type:5,inversion:1},{root:6,beat:51.5,duration:5.5,type:11,inversion:0},
        {root:4,beat:57,duration:0.5,type:5,inversion:0},{root:1,beat:57.5,duration:0.5,type:5,inversion:1},
        {root:4,beat:58,duration:0.5,type:5,inversion:0},{root:5,beat:58.5,duration:0.5,type:5,inversion:0},
      ],
    },
    // Cover 2 — F# major
    {
      label: 'Cover 2',
      tonic: 'F#', scale: 'major',
      notes: [
        {sd:'3',octave:0,beat:2,duration:1.5},{sd:'3',octave:0,beat:3.5,duration:0.5},{sd:'3',octave:0,beat:4,duration:0.25},
        {sd:'3',octave:0,beat:4.25,duration:0.25},{sd:'3',octave:0,beat:4.5,duration:1},{sd:'1',octave:0,beat:5.5,duration:0.5},
        {sd:'1',octave:0,beat:6,duration:0.5},{sd:'1',octave:0,beat:6.5,duration:1},{sd:'2',octave:0,beat:7.5,duration:0.5},
        {sd:'3',octave:0,beat:10.5,duration:0.5},{sd:'3',octave:0,beat:11,duration:0.25},{sd:'3',octave:0,beat:11.25,duration:0.25},
        {sd:'3',octave:0,beat:11.5,duration:0.5},{sd:'3',octave:0,beat:12,duration:0.5},{sd:'5',octave:0,beat:12.5,duration:0.5},
        {sd:'1',octave:0,beat:13.5,duration:0.5},{sd:'1',octave:0,beat:14,duration:0.5},{sd:'1',octave:0,beat:14.5,duration:1},
        {sd:'2',octave:0,beat:15.5,duration:0.5},{sd:'3',octave:0,beat:18,duration:1.5},{sd:'3',octave:0,beat:19.5,duration:0.5},
        {sd:'3',octave:0,beat:20,duration:0.25},{sd:'3',octave:0,beat:20.25,duration:0.25},{sd:'3',octave:0,beat:20.5,duration:1},
        {sd:'1',octave:0,beat:21.5,duration:0.5},{sd:'1',octave:0,beat:22,duration:0.5},{sd:'1',octave:0,beat:22.5,duration:1},
        {sd:'2',octave:0,beat:23.5,duration:0.5},{sd:'1',octave:0,beat:27,duration:1},{sd:'1',octave:0,beat:28,duration:1},
        {sd:'1',octave:0,beat:29,duration:0.5},{sd:'2',octave:0,beat:29.5,duration:0.5},{sd:'3',octave:0,beat:30,duration:0.5},
        {sd:'2',octave:0,beat:30.5,duration:1},{sd:'1',octave:0,beat:31.5,duration:0.5},{sd:'1',octave:0,beat:32,duration:1},
        {sd:'3',octave:0,beat:34,duration:1.5},{sd:'3',octave:0,beat:35.5,duration:0.5},{sd:'3',octave:0,beat:36,duration:0.25},
        {sd:'3',octave:0,beat:36.25,duration:0.25},{sd:'3',octave:0,beat:36.5,duration:1},{sd:'1',octave:0,beat:37.5,duration:0.5},
        {sd:'1',octave:0,beat:38,duration:0.5},{sd:'1',octave:0,beat:38.5,duration:1},{sd:'2',octave:0,beat:39.5,duration:0.5},
        {sd:'3',octave:0,beat:42.5,duration:0.5},{sd:'3',octave:0,beat:43,duration:0.25},{sd:'3',octave:0,beat:43.25,duration:0.25},
        {sd:'3',octave:0,beat:43.5,duration:0.5},{sd:'3',octave:0,beat:44,duration:0.5},{sd:'5',octave:0,beat:44.5,duration:0.5},
        {sd:'1',octave:0,beat:45.5,duration:0.5},{sd:'1',octave:0,beat:46,duration:0.5},{sd:'1',octave:0,beat:46.5,duration:1},
        {sd:'2',octave:0,beat:47.5,duration:0.5},{sd:'4',octave:0,beat:50,duration:0.5},{sd:'3',octave:0,beat:50.5,duration:1},
        {sd:'3',octave:0,beat:51.5,duration:0.5},{sd:'3',octave:0,beat:52,duration:0.25},{sd:'3',octave:0,beat:52.25,duration:0.25},
        {sd:'3',octave:0,beat:52.5,duration:0.5},{sd:'2',octave:0,beat:53,duration:0.5},{sd:'1',octave:0,beat:53.5,duration:0.5},
        {sd:'1',octave:0,beat:54,duration:0.5},{sd:'1',octave:0,beat:54.5,duration:1},{sd:'2',octave:0,beat:55.5,duration:0.5},
        {sd:'1',octave:0,beat:59,duration:1},{sd:'1',octave:0,beat:60,duration:1},{sd:'1',octave:0,beat:61,duration:0.5},
        {sd:'2',octave:0,beat:61.5,duration:0.5},{sd:'3',octave:0,beat:62,duration:0.5},{sd:'2',octave:0,beat:62.5,duration:1},
        {sd:'1',octave:0,beat:63.5,duration:0.5},{sd:'1',octave:0,beat:64,duration:3.5},{sd:'3',octave:0,beat:67.5,duration:0.5},
        {sd:'3',octave:0,beat:68,duration:0.25},{sd:'5',octave:0,beat:68.25,duration:0.25},{sd:'5',octave:-1,beat:68.75,duration:0.25},
        {sd:'3',octave:0,beat:69,duration:0.5},{sd:'2',octave:0,beat:69.5,duration:0.5},{sd:'1',octave:0,beat:70,duration:0.5},
        {sd:'1',octave:0,beat:70.5,duration:0.5},{sd:'3',octave:0,beat:72,duration:0.5},{sd:'2',octave:0,beat:72.5,duration:0.5},
      ],
      chords: [
        {root:1,beat:1,duration:15,type:5,inversion:0},{root:1,beat:16,duration:1,type:7,inversion:3},
        {root:6,beat:17,duration:7,type:5,inversion:0},{root:1,beat:24,duration:1,type:5,inversion:1},
        {root:4,beat:25,duration:7,type:5,inversion:0},{root:5,beat:32,duration:1,type:5,inversion:0},
        {root:1,beat:33,duration:15,type:5,inversion:0},{root:1,beat:48,duration:1,type:7,inversion:3},
        {root:6,beat:49,duration:7,type:5,inversion:0},{root:1,beat:56,duration:1,type:5,inversion:1},
        {root:4,beat:57,duration:4,type:5,inversion:0},{root:2,beat:61,duration:1,type:7,inversion:0},
        {root:3,beat:62,duration:1,type:7,inversion:0},{root:4,beat:63,duration:2,type:5,inversion:0},
        {root:1,beat:65,duration:4,type:5,inversion:0},{root:1,beat:69,duration:2,type:5,inversion:0},
        {root:1,beat:71,duration:1,type:5,inversion:0},{root:1,beat:72,duration:0.5,type:5,inversion:2},
        {root:5,beat:72.5,duration:0.5,type:5,inversion:0},
      ],
    },
    // Cover 3 — F# major
    {
      label: 'Cover 3',
      tonic: 'F#', scale: 'major',
      notes: [
        {sd:'3',octave:0,beat:4.5,duration:1},{sd:'3',octave:0,beat:5.5,duration:0.25},{sd:'3',octave:0,beat:5.75,duration:0.25},
        {sd:'6',octave:0,beat:6.5,duration:1},{sd:'3',octave:0,beat:8.5,duration:1},{sd:'3',octave:0,beat:9.5,duration:0.25},
        {sd:'3',octave:0,beat:9.75,duration:0.25},{sd:'6',octave:0,beat:10.5,duration:1},{sd:'3',octave:0,beat:14,duration:0.5},
        {sd:'5',octave:0,beat:14.5,duration:1},{sd:'3',octave:0,beat:15.5,duration:0.5},{sd:'3',octave:0,beat:16,duration:0.5},
        {sd:'5',octave:0,beat:16.5,duration:1.5},{sd:'3',octave:0,beat:18,duration:0.5},{sd:'3',octave:0,beat:18.5,duration:0.5},
        {sd:'2',octave:0,beat:19,duration:1},{sd:'2',octave:0,beat:20,duration:0.25},{sd:'1',octave:0,beat:20.25,duration:0.25},
        {sd:'3',octave:0,beat:20.5,duration:1},{sd:'3',octave:0,beat:21.5,duration:0.25},{sd:'3',octave:0,beat:21.75,duration:0.25},
        {sd:'6',octave:0,beat:22.5,duration:1},{sd:'3',octave:0,beat:24.5,duration:1},{sd:'3',octave:0,beat:25.5,duration:0.25},
        {sd:'3',octave:0,beat:25.75,duration:0.25},{sd:'6',octave:0,beat:26.5,duration:1},{sd:'3',octave:0,beat:30,duration:0.5},
        {sd:'5',octave:0,beat:30.5,duration:1.5},{sd:'3',octave:0,beat:32,duration:0.5},{sd:'6',octave:0,beat:32.5,duration:1},
        {sd:'3',octave:0,beat:34,duration:0.5},{sd:'5',octave:0,beat:34.5,duration:1.5},{sd:'3',octave:0,beat:36,duration:1},
      ],
      chords: [
        {root:6,beat:5,duration:8,type:7,inversion:0},{root:5,beat:13,duration:6,type:5,inversion:0},
        {root:2,beat:19,duration:1,type:5,inversion:0},{root:3,beat:20,duration:1,type:5,inversion:0},
        {root:6,beat:21,duration:8,type:7,inversion:0},{root:5,beat:29,duration:6.75,type:5,inversion:0},
        {root:4,beat:35.75,duration:0.75,type:5,inversion:0},{root:3,beat:36.5,duration:0.5,type:7,inversion:0},
      ],
    },
    // Cover 4 — Ab major
    {
      label: 'Cover 4',
      tonic: 'Ab', scale: 'major',
      notes: [
        {sd:'3',octave:0,beat:2,duration:1.5},{sd:'3',octave:0,beat:3.5,duration:0.5},{sd:'3',octave:0,beat:4,duration:0.25},
        {sd:'3',octave:0,beat:4.25,duration:0.25},{sd:'3',octave:0,beat:4.5,duration:1},{sd:'1',octave:0,beat:5.5,duration:0.5},
        {sd:'1',octave:0,beat:6,duration:0.5},{sd:'1',octave:0,beat:6.5,duration:1},{sd:'2',octave:0,beat:7.5,duration:0.5},
        {sd:'3',octave:0,beat:10.5,duration:0.5},{sd:'3',octave:0,beat:11,duration:0.25},{sd:'3',octave:0,beat:11.25,duration:0.25},
        {sd:'3',octave:0,beat:11.5,duration:0.5},{sd:'3',octave:0,beat:12,duration:0.5},{sd:'5',octave:0,beat:12.5,duration:0.5},
        {sd:'1',octave:0,beat:13.5,duration:0.5},{sd:'1',octave:0,beat:14,duration:0.5},{sd:'1',octave:0,beat:14.5,duration:1},
        {sd:'2',octave:0,beat:15.5,duration:0.5},{sd:'4',octave:0,beat:18,duration:0.5},{sd:'3',octave:0,beat:18.5,duration:1},
        {sd:'3',octave:0,beat:19.5,duration:0.5},{sd:'3',octave:0,beat:20,duration:0.25},{sd:'3',octave:0,beat:20.25,duration:0.25},
        {sd:'3',octave:0,beat:20.5,duration:1},{sd:'1',octave:0,beat:21.5,duration:0.5},{sd:'1',octave:0,beat:22,duration:0.5},
        {sd:'1',octave:0,beat:22.5,duration:1},{sd:'2',octave:0,beat:23.5,duration:0.5},{sd:'1',octave:0,beat:27,duration:1},
        {sd:'1',octave:0,beat:28,duration:1},{sd:'1',octave:0,beat:29,duration:0.5},{sd:'2',octave:0,beat:29.5,duration:0.5},
        {sd:'3',octave:0,beat:30,duration:0.5},{sd:'2',octave:0,beat:30.5,duration:1},{sd:'1',octave:0,beat:31.5,duration:0.5},
        {sd:'1',octave:0,beat:32,duration:0.5},{sd:'4',octave:0,beat:34,duration:0.5},{sd:'3',octave:0,beat:34.5,duration:1},
        {sd:'3',octave:0,beat:35.5,duration:0.5},{sd:'3',octave:0,beat:36,duration:0.25},{sd:'3',octave:0,beat:36.25,duration:0.25},
        {sd:'3',octave:0,beat:36.5,duration:1},{sd:'1',octave:0,beat:37.5,duration:0.5},{sd:'1',octave:0,beat:38,duration:0.5},
        {sd:'1',octave:0,beat:38.5,duration:1},{sd:'2',octave:0,beat:39.5,duration:0.25},{sd:'1',octave:0,beat:39.75,duration:0.25},
        {sd:'6',octave:-1,beat:40,duration:0.5},{sd:'3',octave:0,beat:42.5,duration:0.5},{sd:'3',octave:0,beat:43,duration:0.25},
        {sd:'3',octave:0,beat:43.25,duration:0.25},{sd:'3',octave:0,beat:43.5,duration:0.5},{sd:'3',octave:0,beat:44,duration:0.5},
        {sd:'5',octave:0,beat:44.5,duration:0.5},{sd:'1',octave:0,beat:45.5,duration:0.5},{sd:'1',octave:0,beat:46,duration:0.5},
        {sd:'1',octave:0,beat:46.5,duration:1},{sd:'4',octave:0,beat:47.5,duration:0.5},{sd:'3',octave:0,beat:48,duration:1},
        {sd:'4',octave:0,beat:50,duration:0.5},{sd:'3',octave:0,beat:50.5,duration:1},{sd:'3',octave:0,beat:51.5,duration:0.5},
        {sd:'3',octave:0,beat:52,duration:0.25},{sd:'3',octave:0,beat:52.25,duration:0.25},{sd:'3',octave:0,beat:52.5,duration:1},
        {sd:'1',octave:0,beat:53.5,duration:0.5},{sd:'1',octave:0,beat:54,duration:0.5},{sd:'1',octave:0,beat:54.5,duration:1},
        {sd:'2',octave:0,beat:55.5,duration:0.5},{sd:'1',octave:0,beat:59,duration:1},{sd:'1',octave:0,beat:60,duration:1},
        {sd:'1',octave:0,beat:61,duration:0.5},{sd:'2',octave:0,beat:61.5,duration:0.5},{sd:'3',octave:0,beat:62,duration:0.5},
        {sd:'5',octave:0,beat:62.5,duration:1.5},{sd:'3',octave:0,beat:64,duration:0.5},
      ],
      chords: [
        {root:1,beat:1,duration:15,type:5,inversion:0},{root:5,beat:16,duration:1,type:5,inversion:1},
        {root:6,beat:17,duration:7,type:5,inversion:0},{root:6,beat:24,duration:1,type:5,inversion:2},
        {root:4,beat:25,duration:7,type:5,inversion:0},{root:5,beat:32,duration:1,type:5,inversion:0},
        {root:1,beat:33,duration:15,type:5,inversion:0},{root:5,beat:48,duration:1,type:5,inversion:1},
        {root:6,beat:49,duration:7,type:5,inversion:0},{root:6,beat:56,duration:1,type:5,inversion:2},
        {root:4,beat:57,duration:4,type:5,inversion:0},{root:2,beat:61,duration:1,type:7,inversion:0},
        {root:3,beat:62,duration:1,type:7,inversion:0},{root:4,beat:63,duration:2,type:5,inversion:0},
      ],
    },
    // Cover 5 — G major (intro chords)
    {
      label: 'Cover 5',
      tonic: 'G', scale: 'major',
      notes: [],
      chords: [
        {root:1,beat:1,duration:20,type:5,inversion:0},
        {root:2,beat:21,duration:4,type:5,inversion:0},
        {root:6,beat:25,duration:8,type:5,inversion:0},
      ],
    },
    // Cover 6 — G major (verse)
    {
      label: 'Cover 6',
      tonic: 'G', scale: 'major',
      notes: [
        {sd:'5',octave:-1,beat:3,duration:0.5},{sd:'3',octave:-1,beat:3.5,duration:0.5},
        {sd:'5',octave:-1,beat:4,duration:0.5},{sd:'6',octave:-1,beat:4.5,duration:1.5},
        {sd:'5',octave:-1,beat:7,duration:1},{sd:'5',octave:-1,beat:8,duration:0.5},
        {sd:'3',octave:-1,beat:8.5,duration:1.5},{sd:'5',octave:-1,beat:11,duration:0.5},
        {sd:'3',octave:-1,beat:11.5,duration:1.5},{sd:'5',octave:-1,beat:13,duration:0.5},
        {sd:'6',octave:-1,beat:13.5,duration:1.5},{sd:'3',octave:-1,beat:15,duration:0.5},
        {sd:'2',octave:-1,beat:15.5,duration:1.5},{sd:'3',octave:-1,beat:17,duration:4},
        {sd:'4',octave:-1,beat:21,duration:4},{sd:'5',octave:-1,beat:25,duration:2},
        {sd:'5',octave:-1,beat:35,duration:0.5},{sd:'5',octave:-1,beat:35.5,duration:1},
        {sd:'3',octave:-1,beat:36.5,duration:0.5},{sd:'5',octave:-1,beat:37,duration:1},
        {sd:'5',octave:-1,beat:38,duration:0.5},{sd:'6',octave:-1,beat:38.5,duration:1.5},
        {sd:'5',octave:-1,beat:44,duration:1.5},{sd:'5',octave:-1,beat:45.5,duration:1.5},
        {sd:'6',octave:-1,beat:47,duration:1},{sd:'3',octave:-1,beat:48,duration:1},
        {sd:'2',octave:-1,beat:49,duration:1},{sd:'3',octave:-1,beat:50,duration:3},
        {sd:'4',octave:-1,beat:53,duration:4},{sd:'5',octave:-1,beat:57,duration:2},
      ],
      chords: [
        {root:1,beat:1,duration:4,type:5,inversion:0},{root:1,beat:5,duration:4,type:5,inversion:0},
        {root:1,beat:9,duration:4,type:5,inversion:0},{root:1,beat:13,duration:4,type:5,inversion:0},
        {root:1,beat:17,duration:4,type:5,inversion:0},{root:2,beat:21,duration:4,type:5,inversion:0},
        {root:6,beat:25,duration:4,type:5,inversion:0},{root:6,beat:29,duration:4,type:5,inversion:0},
        {root:1,beat:33,duration:4,type:5,inversion:0},{root:1,beat:37,duration:4,type:5,inversion:0},
        {root:1,beat:41,duration:4,type:5,inversion:0},{root:1,beat:45,duration:4,type:5,inversion:0},
        {root:1,beat:49,duration:4,type:5,inversion:0},{root:2,beat:53,duration:4,type:5,inversion:0},
        {root:6,beat:57,duration:4,type:5,inversion:0},{root:6,beat:61,duration:4,type:5,inversion:0},
      ],
    },
    // Cover 7 — G major (climax)
    {
      label: 'Cover 7',
      tonic: 'G', scale: 'major',
      notes: [
        {sd:'1',octave:0,beat:1,duration:0.5},{sd:'7',octave:-1,beat:1.5,duration:0.5},
        {sd:'6',octave:-1,beat:2,duration:0.5},{sd:'5',octave:-1,beat:2.5,duration:1.5},
        {sd:'5',octave:-1,beat:4,duration:0.5},{sd:'5',octave:-1,beat:4.5,duration:1},
        {sd:'6',octave:-1,beat:5.5,duration:1},{sd:'5',octave:-1,beat:6.5,duration:2},
        {sd:'5',octave:-1,beat:8.5,duration:0.5},{sd:'1',octave:0,beat:9,duration:0.5},
        {sd:'2',octave:0,beat:9.5,duration:0.5},{sd:'1',octave:0,beat:10,duration:0.5},
        {sd:'1',octave:0,beat:10.5,duration:1.5},{sd:'3',octave:0,beat:12,duration:1},
        {sd:'2',octave:0,beat:13,duration:0.5},{sd:'1',octave:0,beat:13.5,duration:1},
        {sd:'6',octave:-1,beat:14.5,duration:1},{sd:'5',octave:-1,beat:16.5,duration:0.5},
        {sd:'1',octave:0,beat:17,duration:1.5},{sd:'3',octave:-1,beat:18.5,duration:1.5},
        {sd:'3',octave:-1,beat:20,duration:0.5},{sd:'5',octave:-1,beat:20.5,duration:1},
        {sd:'6',octave:-1,beat:21.5,duration:0.5},{sd:'5',octave:-1,beat:22,duration:1.5},
        {sd:'5',octave:-1,beat:23.5,duration:1.5},{sd:'1',octave:0,beat:25,duration:1.5},
        {sd:'1',octave:0,beat:26.5,duration:1},{sd:'6',octave:-1,beat:27.5,duration:0.5},
        {sd:'1',octave:0,beat:28,duration:0.5},{sd:'6',octave:-1,beat:28.5,duration:0.5},
        {sd:'1',octave:0,beat:29,duration:0.5},{sd:'2',octave:0,beat:29.5,duration:0.5},
        {sd:'1',octave:0,beat:30,duration:1},{sd:'1',octave:0,beat:32,duration:1},
        {sd:'1',octave:0,beat:33,duration:1},{sd:'1',octave:0,beat:34,duration:0.5},
        {sd:'6',octave:-1,beat:34.5,duration:0.5},{sd:'1',octave:0,beat:35,duration:0.5},
        {sd:'6',octave:-1,beat:35.5,duration:0.5},{sd:'6',octave:-1,beat:36,duration:0.5},
        {sd:'1',octave:0,beat:36.5,duration:1},{sd:'1',octave:0,beat:37.5,duration:1},
        {sd:'6',octave:-1,beat:38.5,duration:0.5},{sd:'1',octave:0,beat:39,duration:0.5},
        {sd:'2',octave:0,beat:39.5,duration:0.5},{sd:'1',octave:0,beat:40,duration:0.25},
        {sd:'1',octave:0,beat:41,duration:0.5},{sd:'1',octave:0,beat:41.5,duration:0.5},
        {sd:'6',octave:-1,beat:42,duration:0.5},{sd:'1',octave:0,beat:42.5,duration:0.5},
        {sd:'6',octave:-1,beat:43,duration:0.5},{sd:'6',octave:-1,beat:43.5,duration:0.5},
        {sd:'1',octave:0,beat:44,duration:0.5},{sd:'6',octave:-1,beat:44.5,duration:0.5},
        {sd:'1',octave:0,beat:45,duration:0.5},{sd:'6',octave:-1,beat:45.5,duration:0.5},
        {sd:'1',octave:0,beat:46,duration:0.5},{sd:'6',octave:-1,beat:46.5,duration:0.5},
        {sd:'1',octave:0,beat:47,duration:0.5},{sd:'2',octave:0,beat:47.5,duration:0.5},
        {sd:'1',octave:0,beat:49,duration:0.5},{sd:'1',octave:0,beat:49.5,duration:0.5},
        {sd:'1',octave:0,beat:50,duration:0.5},{sd:'3',octave:0,beat:50.5,duration:0.5},
        {sd:'2',octave:0,beat:51,duration:0.5},{sd:'2',octave:0,beat:51.5,duration:0.5},
        {sd:'1',octave:0,beat:52,duration:0.5},{sd:'3',octave:0,beat:52.5,duration:0.5},
        {sd:'2',octave:0,beat:53,duration:0.5},{sd:'2',octave:0,beat:53.5,duration:0.5},
        {sd:'1',octave:0,beat:54,duration:0.5},{sd:'1',octave:0,beat:54.5,duration:1},
        {sd:'6',octave:-1,beat:55.5,duration:0.5},{sd:'1',octave:0,beat:56,duration:0.5},
        {sd:'6',octave:-1,beat:56.5,duration:0.5},{sd:'1',octave:0,beat:57,duration:0.5},
        {sd:'6',octave:-1,beat:57.5,duration:0.5},{sd:'6',octave:-1,beat:58,duration:0.5},
        {sd:'1',octave:0,beat:58.5,duration:1},{sd:'6',octave:-1,beat:59.5,duration:0.5},
        {sd:'1',octave:0,beat:60,duration:0.5},{sd:'6',octave:-1,beat:60.5,duration:0.5},
        {sd:'1',octave:0,beat:61,duration:0.5},{sd:'1',octave:0,beat:61.5,duration:0.5},
        {sd:'6',octave:-1,beat:62,duration:0.5},{sd:'1',octave:0,beat:62.5,duration:0.5},
        {sd:'6',octave:-1,beat:63,duration:0.5},{sd:'1',octave:0,beat:64.5,duration:0.5},
      ],
      chords: [
        {root:1,beat:1,duration:8,type:5,inversion:0},{root:1,beat:9,duration:8,type:5,inversion:0},
        {root:1,beat:17,duration:4,type:5,inversion:0},{root:2,beat:21,duration:4,type:5,inversion:0},
        {root:6,beat:25,duration:8,type:5,inversion:0},{root:1,beat:33,duration:8,type:5,inversion:0},
        {root:1,beat:41,duration:8,type:5,inversion:0},{root:1,beat:49,duration:4,type:5,inversion:0},
        {root:2,beat:53,duration:4,type:5,inversion:0},{root:6,beat:57,duration:8,type:5,inversion:0},
      ],
    },
  ];

  const BALLAD_SECTIONS = [
    // Ballad 1 — G major (chord-only intro: I dur 20 / ii dur 4 / vi dur 8)
    {
      label: 'Ballad 1',
      tonic: 'G', scale: 'major',
      notes: [],
      chords: [
        {root:1,beat:1,duration:20,type:5,inversion:0},{root:2,beat:21,duration:4,type:5,inversion:0},
        {root:6,beat:25,duration:8,type:5,inversion:0},
      ],
    },
    // Ballad 2 — G major (verse: I/I/I/I/I/ii/vi/vi × 2)
    {
      label: 'Ballad 2',
      tonic: 'G', scale: 'major',
      notes: [
        {sd:'1',octave:0,beat:1,duration:2,isRest:true},{sd:'5',octave:-1,beat:3,duration:0.5},{sd:'3',octave:-1,beat:3.5,duration:0.5},
        {sd:'5',octave:-1,beat:4,duration:0.5},{sd:'6',octave:-1,beat:4.5,duration:1.5},{sd:'1',octave:0,beat:6,duration:1,isRest:true},
        {sd:'5',octave:-1,beat:7,duration:1},{sd:'5',octave:-1,beat:8,duration:0.5},{sd:'3',octave:-1,beat:8.5,duration:1.5},
        {sd:'1',octave:0,beat:10,duration:1,isRest:true},{sd:'5',octave:-1,beat:11,duration:0.5},{sd:'3',octave:-1,beat:11.5,duration:1.5},
        {sd:'5',octave:-1,beat:13,duration:0.5},{sd:'6',octave:-1,beat:13.5,duration:1.5},{sd:'3',octave:-1,beat:15,duration:0.5},
        {sd:'2',octave:-1,beat:15.5,duration:1.5},{sd:'3',octave:-1,beat:17,duration:4},{sd:'4',octave:-1,beat:21,duration:4},
        {sd:'5',octave:-1,beat:25,duration:2},{sd:'1',octave:0,beat:27,duration:6,isRest:true},{sd:'1',octave:0,beat:33,duration:2,isRest:true},
        {sd:'5',octave:-1,beat:35,duration:0.5},{sd:'5',octave:-1,beat:35.5,duration:1},{sd:'3',octave:-1,beat:36.5,duration:0.5},
        {sd:'5',octave:-1,beat:37,duration:1},{sd:'5',octave:-1,beat:38,duration:0.5},{sd:'6',octave:-1,beat:38.5,duration:1.5},
        {sd:'1',octave:-1,beat:40,duration:1,isRest:true},{sd:'1',octave:-1,beat:41,duration:1,isRest:true},{sd:'1',octave:0,beat:42,duration:1,isRest:true},
        {sd:'1',octave:-1,beat:43,duration:1,isRest:true},{sd:'5',octave:-1,beat:44,duration:1.5},{sd:'5',octave:-1,beat:45.5,duration:1.5},
        {sd:'6',octave:-1,beat:47,duration:1},{sd:'3',octave:-1,beat:48,duration:1},{sd:'2',octave:-1,beat:49,duration:1},
        {sd:'3',octave:-1,beat:50,duration:3},{sd:'4',octave:-1,beat:53,duration:4},{sd:'5',octave:-1,beat:57,duration:2},
        {sd:'1',octave:0,beat:59,duration:6,isRest:true},
      ],
      chords: [
        {root:1,beat:1,duration:4,type:5,inversion:0},{root:1,beat:5,duration:4,type:5,inversion:0},
        {root:1,beat:9,duration:4,type:5,inversion:0},{root:1,beat:13,duration:4,type:5,inversion:0},
        {root:1,beat:17,duration:4,type:5,inversion:0},{root:2,beat:21,duration:4,type:5,inversion:0},
        {root:6,beat:25,duration:4,type:5,inversion:0},{root:6,beat:29,duration:4,type:5,inversion:0},
        {root:1,beat:33,duration:4,type:5,inversion:0},{root:1,beat:37,duration:4,type:5,inversion:0},
        {root:1,beat:41,duration:4,type:5,inversion:0},{root:1,beat:45,duration:4,type:5,inversion:0},
        {root:1,beat:49,duration:4,type:5,inversion:0},{root:2,beat:53,duration:4,type:5,inversion:0},
        {root:6,beat:57,duration:4,type:5,inversion:0},{root:6,beat:61,duration:4,type:5,inversion:0},
      ],
    },
    // Ballad 3 — G major (climax: I/I/I/ii/vi × 2, dense eighth-note melody)
    {
      label: 'Ballad 3',
      tonic: 'G', scale: 'major',
      notes: [
        {sd:'1',octave:0,beat:1,duration:0.5},{sd:'7',octave:-1,beat:1.5,duration:0.5},{sd:'6',octave:-1,beat:2,duration:0.5},
        {sd:'5',octave:-1,beat:2.5,duration:1.5},{sd:'5',octave:-1,beat:4,duration:0.5},{sd:'5',octave:-1,beat:4.5,duration:1},
        {sd:'6',octave:-1,beat:5.5,duration:1},{sd:'5',octave:-1,beat:6.5,duration:2},{sd:'5',octave:-1,beat:8.5,duration:0.5},
        {sd:'1',octave:0,beat:9,duration:0.5},{sd:'2',octave:0,beat:9.5,duration:0.5},{sd:'1',octave:0,beat:10,duration:0.5},
        {sd:'1',octave:0,beat:10.5,duration:1.5},{sd:'3',octave:0,beat:12,duration:1},{sd:'2',octave:0,beat:13,duration:0.5},
        {sd:'1',octave:0,beat:13.5,duration:1},{sd:'6',octave:-1,beat:14.5,duration:1},{sd:'5',octave:-1,beat:16.5,duration:0.5},
        {sd:'1',octave:0,beat:17,duration:1.5},{sd:'3',octave:-1,beat:18.5,duration:1.5},{sd:'3',octave:-1,beat:20,duration:0.5},
        {sd:'5',octave:-1,beat:20.5,duration:1},{sd:'6',octave:-1,beat:21.5,duration:0.5},{sd:'5',octave:-1,beat:22,duration:1.5},
        {sd:'5',octave:-1,beat:23.5,duration:1.5},{sd:'1',octave:0,beat:25,duration:1.5},{sd:'1',octave:0,beat:26.5,duration:1},
        {sd:'6',octave:-1,beat:27.5,duration:0.5},{sd:'1',octave:0,beat:28,duration:0.5},{sd:'6',octave:-1,beat:28.5,duration:0.5},
        {sd:'1',octave:0,beat:29,duration:0.5},{sd:'2',octave:0,beat:29.5,duration:0.5},{sd:'1',octave:0,beat:30,duration:1},
        {sd:'1',octave:0,beat:32,duration:1},{sd:'1',octave:0,beat:33,duration:1},{sd:'1',octave:0,beat:34,duration:0.5},
        {sd:'6',octave:-1,beat:34.5,duration:0.5},{sd:'1',octave:0,beat:35,duration:0.5},{sd:'6',octave:-1,beat:35.5,duration:0.5},
        {sd:'6',octave:-1,beat:36,duration:0.5},{sd:'1',octave:0,beat:36.5,duration:1},{sd:'1',octave:0,beat:37.5,duration:1},
        {sd:'6',octave:-1,beat:38.5,duration:0.5},{sd:'1',octave:0,beat:39,duration:0.5},{sd:'2',octave:0,beat:39.5,duration:0.5},
        {sd:'1',octave:0,beat:40,duration:0.25},{sd:'1',octave:0,beat:41,duration:0.5},{sd:'1',octave:0,beat:41.5,duration:0.5},
        {sd:'6',octave:-1,beat:42,duration:0.5},{sd:'1',octave:0,beat:42.5,duration:0.5},{sd:'6',octave:-1,beat:43,duration:0.5},
        {sd:'6',octave:-1,beat:43.5,duration:0.5},{sd:'1',octave:0,beat:44,duration:0.5},{sd:'6',octave:-1,beat:44.5,duration:0.5},
        {sd:'1',octave:0,beat:45,duration:0.5},{sd:'6',octave:-1,beat:45.5,duration:0.5},{sd:'1',octave:0,beat:46,duration:0.5},
        {sd:'6',octave:-1,beat:46.5,duration:0.5},{sd:'1',octave:0,beat:47,duration:0.5},{sd:'2',octave:0,beat:47.5,duration:0.5},
        {sd:'1',octave:0,beat:49,duration:0.5},{sd:'1',octave:0,beat:49.5,duration:0.5},{sd:'1',octave:0,beat:50,duration:0.5},
        {sd:'3',octave:0,beat:50.5,duration:0.5},{sd:'2',octave:0,beat:51,duration:0.5},{sd:'2',octave:0,beat:51.5,duration:0.5},
        {sd:'1',octave:0,beat:52,duration:0.5},{sd:'3',octave:0,beat:52.5,duration:0.5},{sd:'2',octave:0,beat:53,duration:0.5},
        {sd:'2',octave:0,beat:53.5,duration:0.5},{sd:'1',octave:0,beat:54,duration:0.5},{sd:'1',octave:0,beat:54.5,duration:1},
        {sd:'6',octave:-1,beat:55.5,duration:0.5},{sd:'1',octave:0,beat:56,duration:0.5},{sd:'6',octave:-1,beat:56.5,duration:0.5},
        {sd:'1',octave:0,beat:57,duration:0.5},{sd:'6',octave:-1,beat:57.5,duration:0.5},{sd:'6',octave:-1,beat:58,duration:0.5},
        {sd:'1',octave:0,beat:58.5,duration:1},{sd:'6',octave:-1,beat:59.5,duration:0.5},{sd:'1',octave:0,beat:60,duration:0.5},
        {sd:'6',octave:-1,beat:60.5,duration:0.5},{sd:'1',octave:0,beat:61,duration:0.5},{sd:'1',octave:0,beat:61.5,duration:0.5},
        {sd:'6',octave:-1,beat:62,duration:0.5},{sd:'1',octave:0,beat:62.5,duration:0.5},{sd:'6',octave:-1,beat:63,duration:0.5},
        {sd:'1',octave:0,beat:64.5,duration:0.5},
      ],
      chords: [
        {root:1,beat:1,duration:8,type:5,inversion:0},{root:1,beat:9,duration:8,type:5,inversion:0},
        {root:1,beat:17,duration:4,type:5,inversion:0},{root:2,beat:21,duration:4,type:5,inversion:0},
        {root:6,beat:25,duration:8,type:5,inversion:0},{root:1,beat:33,duration:8,type:5,inversion:0},
        {root:1,beat:41,duration:8,type:5,inversion:0},{root:1,beat:49,duration:4,type:5,inversion:0},
        {root:2,beat:53,duration:4,type:5,inversion:0},{root:6,beat:57,duration:8,type:5,inversion:0},
      ],
    },
  ];

  // Song catalog. Add more songs by appending entries here.
  const SONGS = [
    { name: 'Hero',   sections: HERO_SECTIONS   },
    { name: 'Cover',  sections: COVER_SECTIONS  },
    { name: 'Ballad', sections: BALLAD_SECTIONS },
  ];
  let currentSongIdx = 0;

  // Flatten one song's sections into one timeline. "Seamless" = strip each
  // section's lead-in (first note/chord beat) so sections butt up against
  // each other. Sections can carry { repeat: N } to play N times back-to-back.
  let EVENTS = []; // {type:'note'|'chord', startMs, durMs, midi|midis}
  let SONG_END_MS = 0;
  function buildEvents(songIdx) {
    const sections = SONGS[songIdx].sections;
    EVENTS = [];
    let cursorMs = 0;
    for (const sec of sections) {
      const allItems = [...sec.notes, ...(sec.chords || [])];
      if (!allItems.length) continue;
      const firstBeat = Math.min(...allItems.map(x => x.beat));
      const lastEnd  = Math.max(...allItems.map(x => x.beat + x.duration));
      const secLenMs = (lastEnd - firstBeat) * BEAT_MS;
      const reps = Math.max(1, sec.repeat || 1);
      for (let r = 0; r < reps; r++) {
        const repStart = cursorMs + r * secLenMs;
        for (const n of sec.notes) {
          if (n.isRest) continue;
          EVENTS.push({
            type: 'note',
            startMs: repStart + (n.beat - firstBeat) * BEAT_MS,
            durMs: n.duration * BEAT_MS,
            midi: sdToMidi(n.sd, n.octave, sec.tonic, sec.scale),
          });
        }
        for (const ch of (sec.chords || [])) {
          if (ch.isRest) continue;
          EVENTS.push({
            type: 'chord',
            startMs: repStart + (ch.beat - firstBeat) * BEAT_MS,
            durMs: ch.duration * BEAT_MS,
            midis: chordToMidis(ch, sec.tonic, sec.scale),
          });
        }
      }
      cursorMs += secLenMs * reps;
    }
    EVENTS.sort((a, b) => a.startMs - b.startMs);
    SONG_END_MS = cursorMs;
  }
  buildEvents(currentSongIdx);

  const reducedMotion = window.matchMedia &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  let demoActive = !reducedMotion;
  let demoTimer = null;
  let resolveSleep = null;

  function sleep(ms) {
    return new Promise(resolve => {
      resolveSleep = resolve;
      demoTimer = setTimeout(() => { resolveSleep = null; resolve(); }, ms);
    });
  }
  function stopDemo() {
    if (!demoActive) return;
    demoActive = false;
    document.body.classList.remove('song-playing');
    if (demoTimer) clearTimeout(demoTimer);
    if (resolveSleep) { const r = resolveSleep; resolveSleep = null; r(); }
  }
  // Visual-only flash for the intro flourish (no audio — audio context
  // isn't unlocked yet on page load anyway).
  function flashKey(el) {
    if (!el) return;
    el.classList.add('pressed');
    pulseFloor(getComputedStyle(el).getPropertyValue('--key-color').trim());
    setTimeout(() => el.classList.remove('pressed'), 220);
  }

  // Center → out → back to center. About 1.4 seconds total.
  async function introFlourish() {
    const whites = piano.querySelectorAll('.key.white');
    if (!whites.length) return;
    const N = whites.length;
    const mid = Math.floor(N / 2);
    const STEP_MS = 45;
    // Expand outward
    for (let r = 0; r <= mid && demoActive; r++) {
      if (r === 0) flashKey(whites[mid]);
      else {
        if (mid - r >= 0) flashKey(whites[mid - r]);
        if (mid + r < N) flashKey(whites[mid + r]);
      }
      await sleep(STEP_MS);
    }
    if (!demoActive) return;
    await sleep(160);
    // Collapse back to center
    for (let r = mid - 1; r >= 0 && demoActive; r--) {
      if (r === 0) flashKey(whites[mid]);
      else {
        if (mid - r >= 0) flashKey(whites[mid - r]);
        if (mid + r < N) flashKey(whites[mid + r]);
      }
      await sleep(STEP_MS);
    }
    if (!demoActive) return;
    await sleep(280);
  }

  function syncPickerUI() {
    const picker = document.getElementById('songPicker');
    if (picker && picker.selectedIndex !== currentSongIdx) {
      picker.selectedIndex = currentSongIdx;
    }
  }

  async function melodyLoop() {
    while (demoActive) {
      const t0 = performance.now();
      for (const ev of EVENTS) {
        if (!demoActive) return;
        const wait = ev.startMs - (performance.now() - t0);
        if (wait > 4) await sleep(wait);
        if (!demoActive) return;
        if (ev.type === 'note') {
          const el = piano.querySelector(`.key[data-midi="${ev.midi}"]`);
          if (el) {
            el.classList.add('pressed');
            pulseFloor(getComputedStyle(el).getPropertyValue('--key-color').trim());
            const flashMs = Math.max(140, Math.min(320, ev.durMs));
            setTimeout(() => el.classList.remove('pressed'), flashMs);
          }
          play(ev.midi, Math.max(0.22, ev.durMs / 1000));
        } else if (ev.type === 'chord') {
          // Soft pad under the melody. Each chord tone at ~0.22 gain so the
          // 3-note triad totals ~0.66, sitting below the 1.0 melody peak.
          const release = Math.max(0.6, ev.durMs / 1000);
          for (const m of ev.midis) play(m, release, 0.22);
        }
      }
      if (!demoActive) return;
      await sleep(TAIL_BEATS * BEAT_MS);
      // Advance to next song on loop end. Auto-cycle through SONGS.
      if (!demoActive) return;
      currentSongIdx = (currentSongIdx + 1) % SONGS.length;
      buildEvents(currentSongIdx);
      syncPickerUI();
    }
  }

  async function startSong() {
    if (!demoActive) demoActive = true;
    document.body.classList.add('song-playing');
    await introFlourish();
    if (demoActive) await melodyLoop();
    // Loop exited (either naturally or via stopDemo); remove the class.
    document.body.classList.remove('song-playing');
  }
  async function restartSong() {
    // Stop in-flight loop (if any) and give it a moment to unwind.
    stopDemo();
    await new Promise(r => setTimeout(r, 80));
    demoActive = true;
    startSong();
  }
  // Page-load start
  if (demoActive) setTimeout(startSong, 300);

  // ─── Replay button: restart the current song any time (incl. mid-playback). ───
  const replayBtn = document.getElementById('replayBtn');
  if (replayBtn) {
    replayBtn.addEventListener('click', () => {
      unlockAudio();
      restartSong();
    });
  }

  // ─── Song picker: switch songs manually (also auto-cycles on loop end). ───
  const songPicker = document.getElementById('songPicker');
  if (songPicker) {
    // Populate options from SONGS catalog (in case markup is stale).
    if (songPicker.options.length !== SONGS.length) {
      songPicker.innerHTML = '';
      SONGS.forEach((s, i) => {
        const opt = document.createElement('option');
        opt.value = String(i);
        opt.textContent = s.name;
        songPicker.appendChild(opt);
      });
    }
    songPicker.selectedIndex = currentSongIdx;
    songPicker.addEventListener('change', () => {
      unlockAudio();
      const idx = Number(songPicker.value);
      if (Number.isNaN(idx) || idx < 0 || idx >= SONGS.length) return;
      currentSongIdx = idx;
      buildEvents(currentSongIdx);
      restartSong();
    });
  }

  piano.querySelectorAll('.key').forEach(k => {
    k.addEventListener('pointerdown', e => { e.preventDefault(); pressKey(k); });
    k.addEventListener('keydown', e => {
      if (e.key === ' ' || e.key === 'Enter') { e.preventDefault(); pressKey(k); }
    });
  });

  // ─── Computer keyboard ───
  const KEY_TO_NOTE = {
    'a': 'C4', 's': 'D4', 'd': 'E4', 'f': 'F4', 'g': 'G4', 'h': 'A4', 'j': 'B4',
    'k': 'C5', 'l': 'D5', ';': 'E5',
    'w': 'C#4', 'e': 'D#4', 't': 'F#4', 'y': 'G#4', 'u': 'A#4',
    'o': 'C#5', 'p': 'D#5',
  };
  const held = new Set();
  window.addEventListener('keydown', e => {
    if (e.repeat) return;
    const t = e.target;
    if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable)) return;
    const n = KEY_TO_NOTE[e.key.toLowerCase()];
    if (!n) return;
    if (held.has(e.key)) return;
    held.add(e.key);
    const el = piano.querySelector(`.key[data-note="${n}"]`);
    if (el) pressKey(el);
  });
  window.addEventListener('keyup', e => held.delete(e.key));

  // ─── Mute toggle ───
  const muteBtn = document.getElementById('muteBtn');
  if (muteBtn) {
    // First click on the button is *always* the start trigger, never a mute
    // toggle. This is independent of audioReady because microtask timing
    // (the document-capture unlock + resume().then) can flip audioReady
    // between pointerdown and click, fooling a state-based check.
    let mutePristine = true;
    muteBtn.addEventListener('click', () => {
      unlockAudio();
      if (mutePristine) {
        mutePristine = false;
        // Reflect current mute state in the label without toggling
        muteBtn.textContent = muted ? 'sound off' : 'sound on';
        muteBtn.classList.toggle('muted', muted);
        return;
      }
      muted = !muted;
      muteBtn.classList.toggle('muted', muted);
      muteBtn.textContent = muted ? 'sound off' : 'sound on';
      muteBtn.setAttribute('aria-pressed', String(muted));
    });
  }

  // Preload Salamander immediately so the loop has samples ready before
  // the first user gesture unlocks audio. Other voices load on-demand
  // when their button is clicked.
  loadVoice('salamander');

  // ─── Voice switcher ───
  document.querySelectorAll('[data-voice]').forEach(btn => {
    btn.addEventListener('click', async () => {
      const v = btn.dataset.voice;
      document.querySelectorAll('[data-voice]').forEach(b =>
        b.classList.toggle('active', b === btn));
      unlockAudio();
      currentVoice = v;
      if (v !== 'synth') await loadVoice(v);
    });
  });
})();
