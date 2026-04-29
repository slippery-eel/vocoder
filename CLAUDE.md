# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

A self-contained browser vocoder — one file, zero dependencies, zero build step. Open `index.html` directly.

## Running the app

```bash
start index.html   # Windows
open index.html    # macOS
```

## Architecture

### `index.html` (the entire app)

All logic is inline. Structure:

1. **DSP pipeline** (pure JS, typed arrays):
   - `fft` / `ifft` — radix-2 Cooley-Tukey, in-place, on `Float64Array`
   - `hilbertEnvelope(signal)` — FFT-based analytic signal magnitude; used per modulator band instead of a rectifier
   - `bandpassBiquad(fLow, fHigh, sr)` — computes 2nd-order IIR coefficients
   - `lowpassBiquad(fCutoff, sr)` — Butterworth lowpass for low-band preservation; requires `b1` support in `applyBiquad`
   - `apply4thOrder(signal, coeffs)` — cascades two biquad passes for 24 dB/oct rolloff
   - `extractEnvelope(signal, alphaA, alphaR)` — Hilbert magnitude + asymmetric AR smoother
   - `applyContrast(env, contrast)` — `env[i] = pow(env[i], contrast)`; shapes dynamics before carrier multiplication
   - `buildFilterBank(nBands, fLow, fHigh, sr)` — log-spaced bandpass bank (80–8000 Hz)
   - `runVocoder(mod, car, filterBank, sr, attackMs, releaseMs, blur, contrast)` — per-band filter → envelope → contrast → multiply → sum; `blur > 0` averages each band's envelope with its N nearest neighbors
   - `generateCarrier(n, sr, opts)` — sawtooth/square/triangle/sine oscillator with chord voicing (major/minor/power/single/octaves), optional detune unison, and per-sample vibrato LFO via `vibRate` / `vibDepthCents`
   - `oscillator(waveform, freq, n, sr, vibRate, vibDepthCents)` — phase-accumulator oscillator; vibrato modulates the instantaneous phase increment each sample via `Math.pow(2, cents * sin(lfo) / 1200)`
   - `schroederReverb(signal, sr, roomSize, decay)` — 4 parallel comb filters + 2 series allpass (Freeverb formulation)
   - `normalize(signal)` — peak-normalize to −3 dBFS; called after each post-vocoder effect stage
   - `encodeWAV(samples, sr)` — manual PCM16 WAV writer → `Blob` → download

2. **Audio I/O** (Web Audio API):
   - `decodeAndResample(arrayBuffer)` — `decodeAudioData` + `OfflineAudioContext` resampling to 44100 Hz
   - Microphone recording via `MediaRecorder` / `getUserMedia`
   - Spectrum analyser via `createMediaElementSource` + `AnalyserNode` — created **once** on first run (browser enforces one `MediaElementSource` per element)

3. **Visualization**:
   - `buildWaveformCache(samples, W, H)` — renders waveform to an offscreen `<canvas>` once
   - `renderWaveform(canvas, cache, audioEl)` — stamps cache + draws playback cursor via RAF
   - `drawSpectrum()` — real-time log-scale frequency bars via RAF, active only during playback

## Key design constraints

- **`MediaElementSource` is created once** — `setupSpectrumAnalyser()` guards with `if (outputAudioCtx) return`. Never call `outputAudioCtx.close()` or recreate it; the browser permanently marks the `<audio>` element as connected.
- **4th-order filtering** — `apply4thOrder` runs `applyBiquad` twice. This is intentional for band separation; do not collapse to a single pass.
- **`applyBiquad` supports `b1`** — the bandpass path uses `b1 = 0` (default); the lowpass path sets `b1 ≠ 0`. Do not remove the `b1` parameter.
- **Hilbert via FFT** — zero-pads to next power of 2, doubles positive frequencies, zeros negative frequencies, IFFTs. Gives smoother envelopes than rectification.
- **Unvoiced mix** — white noise blended into the carrier before vocoding to preserve unvoiced consonants (s, f, t).
- **Post-vocoder effects chain** (applied in order, each re-normalizing if it changes the peak):
  1. **Wet/dry** — linear blend of normalized vocoded output and normalized dry modulator
  2. **Ring modulation** — multiply output by `sin(2π × f × t)`; skipped when freq = 0
  3. **Tremolo** — amplitude LFO; skipped when depth = 0
  4. **Low-band preservation** — lowpassed modulator added directly to output; skipped when blend = 0
  5. **Reverb** — Schroeder wet/dry blend; skipped when mix = 0
- **Vibrato vs tremolo**: vibrato is baked into carrier generation (pitch LFO, synth only); tremolo is applied to the final mix (amplitude LFO, works on all carrier types).
- **Spectral blur memory**: when `blur > 0`, `runVocoder` allocates all band envelopes and carrier bands at once (`nb × n` floats each). At 64 bands and long audio this can reach ~200 MB — acceptable but worth knowing.
