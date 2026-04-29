"""
Vocoder: apply a voice modulator's spectral envelope to a carrier signal.

Usage examples:
    python vocoder.py --modulator voice.wav
    python vocoder.py --modulator voice.wav --carrier synth.wav --output result.wav
    python vocoder.py --modulator voice.wav --carrier-mode chord --bands 32
    python vocoder.py --modulator voice.wav --carrier-mode noise --attack 5 --release 80
"""

import argparse
import os
from math import ceil, gcd, log10

import numpy as np
from scipy.signal import butter, hilbert, sawtooth as scipy_sawtooth, sosfilt
import soundfile as sf

try:
    import librosa
    HAS_LIBROSA = True
except ImportError:
    HAS_LIBROSA = False

DEFAULT_SR = 44100
DEFAULT_BANDS = 16
DEFAULT_F_LOW = 80.0
DEFAULT_F_HIGH = 8000.0
DEFAULT_ATTACK = 10.0     # ms
DEFAULT_RELEASE = 100.0   # ms
DEFAULT_TARGET_DB = -3.0


def load_audio(path, target_sr=None):
    """Load audio file; return (float32 ndarray, sample_rate)."""
    try:
        data, sr = sf.read(path, always_2d=False)
        data = data.astype(np.float32)
    except Exception:
        if not HAS_LIBROSA:
            raise
        # librosa handles MP3 and other formats soundfile cannot
        data, sr = librosa.load(path, sr=None, mono=False)
        data = data.astype(np.float32)
        if data.ndim == 2:
            # librosa returns (channels, samples); transpose to (samples, channels)
            data = data.T

    if len(data) == 0:
        raise ValueError(f"Audio file is empty: {path}")

    if target_sr is not None and target_sr != sr:
        data = to_mono(data)
        data = resample_audio(data, sr, target_sr)
        sr = target_sr

    return data, sr


def to_mono(signal):
    """Collapse multichannel audio to a mono float32 array."""
    if signal.ndim == 1:
        return signal
    return np.mean(signal, axis=-1).squeeze().astype(np.float32)


def resample_audio(signal, orig_sr, target_sr):
    """Resample a 1-D signal from orig_sr to target_sr."""
    if orig_sr == target_sr:
        return signal
    if HAS_LIBROSA:
        return librosa.resample(signal, orig_sr=orig_sr, target_sr=target_sr).astype(np.float32)
    # scipy fallback: resample_poly with gcd-reduced up/down ratio
    from scipy.signal import resample_poly
    common = gcd(int(orig_sr), int(target_sr))
    up = int(target_sr) // common
    down = int(orig_sr) // common
    return resample_poly(signal, up, down).astype(np.float32)


def prepare_signals(modulator, carrier, sample_rate):
    """Match carrier length to modulator by trimming or tiling."""
    mod_len = len(modulator)
    car_len = len(carrier)

    if car_len == mod_len:
        return modulator, carrier
    if car_len > mod_len:
        return modulator, carrier[:mod_len]

    repeats = ceil(mod_len / car_len)
    carrier = np.tile(carrier, repeats)[:mod_len]
    return modulator, carrier


def create_filter_bank(n_bands, f_low, f_high, sample_rate):
    """Build a bank of 4th-order Butterworth bandpass SOS filters, log-spaced."""
    nyquist = sample_rate / 2.0
    edges = np.logspace(log10(f_low), log10(f_high), n_bands + 1)

    filter_bank = []
    for i in range(n_bands):
        low = edges[i] / nyquist
        high = edges[i + 1] / nyquist

        low = max(low, 1e-6)
        high = min(high, 0.9999)

        if high <= low:
            print(f"Warning: skipping band {i} ({edges[i]:.1f}–{edges[i+1]:.1f} Hz) — too narrow")
            continue

        sos = butter(4, [low, high], btype='bandpass', output='sos')
        filter_bank.append(sos)

    return filter_bank


def extract_envelope(signal, sample_rate, attack_ms, release_ms):
    """
    Extract amplitude envelope via Hilbert transform + asymmetric AR smoothing.

    The sample-by-sample loop is intentional: vectorised approximations of
    asymmetric AR smoothing introduce phase errors audible in voice material.
    """
    envelope_raw = np.abs(hilbert(signal)).astype(np.float64)

    attack_samples = (attack_ms / 1000.0) * sample_rate
    release_samples = (release_ms / 1000.0) * sample_rate

    alpha_attack = np.exp(-1.0 / max(attack_samples, 1.0))
    alpha_release = np.exp(-1.0 / max(release_samples, 1.0))

    envelope = np.empty_like(envelope_raw)
    prev = 0.0
    for i, x in enumerate(envelope_raw):
        alpha = alpha_attack if x > prev else alpha_release
        prev = alpha * prev + (1.0 - alpha) * x
        envelope[i] = prev

    return envelope.astype(np.float32)


def apply_vocoder(modulator, carrier, filter_bank, sample_rate, attack_ms, release_ms):
    """
    Core vocoder: for each band, multiply the carrier band by the modulator's
    amplitude envelope, then sum all bands into the output.
    """
    output = np.zeros(len(modulator), dtype=np.float32)
    n_bands = len(filter_bank)

    for i, sos in enumerate(filter_bank):
        print(f"  Band {i + 1}/{n_bands}...", end="\r", flush=True)
        mod_band = sosfilt(sos, modulator).astype(np.float32)
        car_band = sosfilt(sos, carrier).astype(np.float32)
        envelope = extract_envelope(mod_band, sample_rate, attack_ms, release_ms)
        output += car_band * envelope

    print()
    return output.astype(np.float32)


def normalize_audio(signal, target_db=DEFAULT_TARGET_DB):
    """Peak-normalize signal to target_db, preventing clipping."""
    if target_db > 0:
        print(f"Warning: target_db={target_db} is positive; output may clip.")
    peak = np.max(np.abs(signal))
    if peak < 1e-9:
        print("Warning: output signal is silent.")
        return signal
    target_linear = 10.0 ** (target_db / 20.0)
    return (signal * (target_linear / peak)).astype(np.float32)


def generate_carrier(duration, sample_rate, mode):
    """Generate a synthetic carrier: 'sawtooth', 'chord', or 'noise'."""
    n_samples = int(duration * sample_rate)
    t = np.linspace(0.0, duration, n_samples, endpoint=False)

    if mode == 'noise':
        return np.random.randn(n_samples).astype(np.float32)

    if mode == 'sawtooth':
        return scipy_sawtooth(2.0 * np.pi * 261.63 * t).astype(np.float32)

    if mode == 'chord':
        freqs = [261.63, 329.63, 392.0]  # C4, E4, G4
        carrier = np.zeros(n_samples, dtype=np.float32)
        for f in freqs:
            carrier += scipy_sawtooth(2.0 * np.pi * f * t).astype(np.float32)
        return carrier / len(freqs)

    raise ValueError(f"Unknown carrier mode: {mode!r}. Choose 'sawtooth', 'noise', or 'chord'.")


def export_audio(signal, sample_rate, output_path):
    """Write a float32 signal to a 16-bit PCM WAV file."""
    if d := os.path.dirname(output_path):
        os.makedirs(d, exist_ok=True)
    sf.write(output_path, signal, sample_rate, subtype='PCM_16')


def main():
    parser = argparse.ArgumentParser(
        prog='vocoder',
        description='Vocoder: apply a voice modulator\'s spectral envelope to a carrier signal.',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument('--modulator', required=True, metavar='PATH',
                        help='Modulator (voice) audio file.')
    parser.add_argument('--carrier', default=None, metavar='PATH',
                        help='Carrier audio file. Omit to auto-generate via --carrier-mode.')
    parser.add_argument('--output', default='output.wav', metavar='PATH',
                        help='Output WAV path.')
    parser.add_argument('--bands', type=int, default=DEFAULT_BANDS, metavar='N',
                        help='Number of filter bands.')
    parser.add_argument('--attack', type=float, default=DEFAULT_ATTACK, metavar='MS',
                        help='Envelope attack time (ms).')
    parser.add_argument('--release', type=float, default=DEFAULT_RELEASE, metavar='MS',
                        help='Envelope release time (ms).')
    parser.add_argument('--carrier-mode', default='sawtooth',
                        choices=['sawtooth', 'noise', 'chord'],
                        help='Carrier type when --carrier is omitted.')
    parser.add_argument('--sample-rate', type=int, default=DEFAULT_SR, metavar='HZ',
                        help='Target sample rate (Hz).')
    args = parser.parse_args()

    sr = args.sample_rate

    print(f"Loading modulator: {args.modulator}")
    modulator, _ = load_audio(args.modulator, target_sr=sr)
    modulator = to_mono(modulator)
    duration = len(modulator) / sr
    print(f"  {len(modulator)} samples at {sr} Hz ({duration:.2f}s)")

    if args.carrier is not None:
        print(f"Loading carrier: {args.carrier}")
        carrier, _ = load_audio(args.carrier, target_sr=sr)
        carrier = to_mono(carrier)
        modulator, carrier = prepare_signals(modulator, carrier, sr)
    else:
        print(f"Generating {args.carrier_mode} carrier ({duration:.2f}s)...")
        carrier = generate_carrier(duration, sr, args.carrier_mode)

    print(f"Building filter bank: {args.bands} bands, {DEFAULT_F_LOW:.0f}–{DEFAULT_F_HIGH:.0f} Hz")
    filter_bank = create_filter_bank(args.bands, DEFAULT_F_LOW, DEFAULT_F_HIGH, sr)
    print(f"  {len(filter_bank)} bands created")

    print(f"Running vocoder (attack={args.attack}ms, release={args.release}ms)...")
    output = apply_vocoder(modulator, carrier, filter_bank, sr, args.attack, args.release)

    output = normalize_audio(output)
    export_audio(output, sr, args.output)
    print(f"Done. Written to: {args.output}")


if __name__ == '__main__':
    main()
