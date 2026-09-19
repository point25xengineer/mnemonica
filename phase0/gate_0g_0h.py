"""Gates 0g (pyannote on Python 3.14) and 0h (MPS vs CPU turn boundaries).

Run:  python phase0/gate_0g_0h.py <clip.wav>

Audio is loaded into memory with the stdlib ``wave`` module and handed to the
pipeline as a ``{"waveform", "sample_rate"}`` dict rather than a path.
torchcodec's ``libtorchcodec_core*.dylib`` needs FFmpeg *shared* libraries
(libavutil.56-.61) and the imageio-ffmpeg static binary supplies only a CLI,
so every file-path decode raises OSError. The waveform dict is pyannote's own
documented workaround (core/io.py:49) and needs no new dependency.
"""

import sys, os, pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import env_guard  # noqa: F401  — must precede pyannote; telemetry is read at import time

import wave
import numpy as np
import torch
from pyannote.audio import Pipeline

MODEL = "pyannote-community/speaker-diarization-community-1"


def load_wav(path):
    """(channel, time) float32 tensor + sample rate, via the stdlib only."""
    with wave.open(str(path), "rb") as w:
        assert w.getsampwidth() == 2, "expected 16-bit PCM"
        frames = w.readframes(w.getnframes())
        data = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
        data = data.reshape(-1, w.getnchannels()).T
        return torch.from_numpy(data.copy()), w.getframerate()


def turns(pipeline, waveform, sr):
    out = pipeline({"waveform": waveform, "sample_rate": sr})
    ann = out.speaker_diarization if hasattr(out, "speaker_diarization") else out
    return [(round(s.start, 3), round(s.end, 3), lbl)
            for s, _, lbl in ann.itertracks(yield_label=True)]


def main(path):
    waveform, sr = load_wav(path)
    print(f"audio: {waveform.shape[1] / sr:.2f}s @ {sr} Hz")

    results = {}
    for device in ("cpu", "mps"):
        pipeline = Pipeline.from_pretrained(MODEL).to(torch.device(device))
        import time
        t0 = time.perf_counter()
        results[device] = turns(pipeline, waveform, sr)
        elapsed = time.perf_counter() - t0
        rtf = (waveform.shape[1] / sr) / elapsed
        print(f"\n--- {device} --- {elapsed:.1f}s ({rtf:.2f}x real-time)")
        for s, e, lbl in results[device]:
            print(f"  {s:7.3f} -> {e:7.3f}  {lbl}")

    print("\n--- 0h: CPU vs MPS ---")
    cpu, mps = results["cpu"], results["mps"]
    if len(cpu) != len(mps):
        print(f"FAIL: different turn counts, cpu={len(cpu)} mps={len(mps)}")
        return
    worst = max(max(abs(c[0] - m[0]), abs(c[1] - m[1])) for c, m in zip(cpu, mps))
    labels_match = all(c[2] == m[2] for c, m in zip(cpu, mps))
    print(f"turns: {len(cpu)}  worst boundary delta: {worst * 1000:.1f} ms  "
          f"labels match: {labels_match}")
    print("PASS — use MPS" if worst < 0.05 and labels_match else "FAIL — CPU only")


if __name__ == "__main__":
    main(sys.argv[1])
