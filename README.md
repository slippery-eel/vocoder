# Vocoder

A browser-based vocoder — open `index.html` directly, no server required.

Apply any sound's spectral shape to a synthesized carrier. Works great with voice, but especially interesting with ambient nature sounds: rain, thunder, birds, wind, and water.

## Quick start

```
# Browser UI
open index.html   # or just double-click it

# Python CLI
pip install -r requirements.txt
python vocoder.py --modulator voice.wav
python vocoder.py --modulator rain.wav --carrier-mode noise --bands 32
python vocoder.py --modulator voice.wav --carrier synth.wav --output result.wav
```

## How it works

The modulator (your voice or any audio) is split into frequency bands via a log-spaced bandpass filter bank. The amplitude envelope of each band is extracted using a Hilbert transform and smoothed with an asymmetric attack/release filter. That envelope then scales the corresponding band of the carrier signal. The bands are summed and normalized to produce the output.

**Carrier options:** synthesized oscillator (saw, square, triangle, sine) with chord voicing, pitch, and unison detune — or upload any audio file as the carrier.

## Controls

### Signals
| Control | Description |
|---------|-------------|
| Modulator | Upload a file or record from microphone. Any audio works — voice, rain, birds, thunder. |
| Carrier | Upload a file, or use the synth/noise generator below. |
| Waveform | Oscillator shape: Saw (bright), Square (hollow), Triangle (soft), Sine (pure). |
| Chord | Interval stack: Major, Minor, Power, Single, or Octaves. |
| Pitch | Root frequency of the carrier oscillator (50–500 Hz). |
| Detune | Cents offset on a doubled voice — adds chorus/unison thickness. |

### Processing
| Control | Description |
|---------|-------------|
| Bands | Number of filter bands (4–64). More bands = finer spectral detail. |
| Attack | Envelope rise time. Fast = transients preserved. Slow = blurry onset. |
| Release | Envelope fall time. 500 ms+ creates a spectral freeze/smear effect. |
| Unvoiced | Noise blended into the carrier before vocoding. Restores energy for s/f/t consonants and rain texture. |

### Effects
| Control | Description |
|---------|-------------|
| Env Contrast | Shapes envelope dynamics. Below 1 = smooth pad. Above 1 = punchier, more textured. |
| Wet / Dry | Blends vocoded output with the original unprocessed modulator. |
| Spectral Blur | Averages each band's envelope with its neighbors. Creates dreamy, diffuse textures. |
| Ring Mod | Multiplies output by a sine wave — metallic sidebands. 0 = off. |
| Tremolo Rate/Depth | Amplitude LFO — rhythmic pulsing. |
| Vibrato Rate/Depth | Pitch LFO on the synthesized carrier. |

### Reverb & Low-End
| Control | Description |
|---------|-------------|
| Reverb Mix | Schroeder algorithmic reverb blend. Transforms nature sounds into spaces. |
| Room Size | Scales reverb delay line lengths (small room → large cave). |
| Reverb Decay | Reverb tail length (short bright room → cathedral). |
| Low Blend | Adds the modulator's sub-bass content directly to the output, bypassing the vocoder. Critical for preserving thunder and kick drum impact. |
| Low Crossover | Frequency below which content bypasses the vocoder (when Low Blend > 0). |

## Tips for nature sounds

- **Rain**: Bands 32+, Attack 5 ms, Env Contrast 2.0, Noise carrier, light Reverb
- **Thunder**: Low Blend 60–80%, Low Crossover 100–160 Hz, long Release, large Reverb
- **Birds**: Bands 24–32, fast Attack/Release, Spectral Blur 2–4 for ambient pad effect
- **Wind**: Noise carrier, high Wet/Dry, Spectral Blur 3–6, Reverb Mix 30–50%

## Files

| File | Description |
|------|-------------|
| `index.html` | Self-contained browser app — all DSP in vanilla JavaScript |
| `vocoder.py` | Python CLI with the same pipeline using NumPy/SciPy |
| `requirements.txt` | Python dependencies |

## Python CLI options

```
python vocoder.py --modulator PATH    # required: source audio
                  --carrier PATH      # optional: carrier audio file
                  --output PATH       # default: output.wav
                  --bands N           # default: 16
                  --attack MS         # default: 10
                  --release MS        # default: 100
                  --carrier-mode      # sawtooth | noise | chord
                  --sample-rate HZ    # default: 44100
```
