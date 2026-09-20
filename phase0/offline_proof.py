"""Run the whole local stack with the network off — the D1 claim, rehearsed.

    1. Turn Wi-Fi OFF.
    2. /Users/evancanty/vn-shared/.venv/bin/python phase0/offline_proof.py <clip.wav>

This is 4b in miniature. It is the one check that cannot be faked from inside
the process: HF_HUB_OFFLINE makes a fetch *fail* rather than succeed silently,
so if anything still wants the network, this run breaks instead of lying.
"""

import sys, pathlib, time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import env_guard  # noqa: F401

import socket

# Fail loudly on any outbound connection, rather than waiting on a timeout.
_real = socket.socket.connect


def _blocked(self, addr):
    host = addr[0] if isinstance(addr, tuple) else addr
    if isinstance(host, str) and not host.startswith(("127.", "::1", "/")):
        raise AssertionError(f"OUTBOUND CONNECTION ATTEMPTED: {addr} — D1 violated")
    return _real(self, addr)


socket.socket.connect = _blocked

clip = sys.argv[1]

import torch, mlx_whisper
from pyannote.audio import Pipeline
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from gate_0g_0h import load_wav, MODEL  # noqa: E402

print("transcribing...")
t0 = time.perf_counter()
r = mlx_whisper.transcribe(clip, path_or_hf_repo="mlx-community/whisper-large-v3-mlx",
                           word_timestamps=True)
words = [w for s in r["segments"] for w in s["words"]]
print(f"  {len(words)} words in {time.perf_counter() - t0:.1f}s")

print("diarizing...")
waveform, sr = load_wav(clip)
pipe = Pipeline.from_pretrained(MODEL).to(torch.device("mps"))
out = pipe({"waveform": waveform, "sample_rate": sr})
ann = out.speaker_diarization
turns = list(ann.itertracks(yield_label=True))
print(f"  {len(turns)} turns")
for seg, _, lbl in turns:
    print(f"  {seg.start:7.2f} -> {seg.end:7.2f}  {lbl}")

print("\ntranscript:", r["text"].strip()[:300])
print("\nNO OUTBOUND CONNECTIONS. D1 holds.")
