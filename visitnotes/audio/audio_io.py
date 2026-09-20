"""Loading audio for Track B — one decoder, used by both models.

torchcodec cannot decode on this machine (see PLAN.md Deviations): its
``libtorchcodec_core*.dylib`` wants FFmpeg *shared* libraries and
``imageio-ffmpeg`` ships only a static CLI, so every ``pipeline(path)`` call
raises ``OSError``. pyannote is therefore fed a ``{"waveform", "sample_rate"}``
dict, which is pyannote's own documented workaround.

So the decode happens here, once, with the stdlib ``wave`` module. Anything
that is not already 16-bit PCM WAV is converted by shelling out to the ffmpeg
CLI, which resolves fine — that is the same path Whisper takes internally.

The converted copy is written **inside the session directory**, never to
``/tmp``: D2/D3 make ``session_dir`` the unit of retention and U9 shreds it.
A decoded WAV in the system temp dir is PHI that survives approval.
"""

from __future__ import annotations

import subprocess
import wave
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import torch

__all__ = ["Audio", "load_audio", "load_wav", "resample"]

#: What both models want. Whisper resamples internally either way; pyannote's
#: embedding model states its own rate, which `resample` matches on demand.
TARGET_SAMPLE_RATE = 16_000


@dataclass(frozen=True)
class Audio:
    """Decoded audio, in the shape pyannote's waveform-dict API expects."""

    waveform: torch.Tensor
    """``(channel, time)`` float32 in [-1, 1]."""
    sample_rate: int
    path: Path
    """The file that was decoded — the *converted* one if conversion happened.
    Whisper is given this path, so both models see identical samples."""

    @property
    def duration(self) -> float:
        return self.waveform.shape[1] / self.sample_rate

    def as_pyannote_input(self) -> dict:
        return {"waveform": self.waveform, "sample_rate": self.sample_rate}

    def mono(self) -> np.ndarray:
        """``(time,)`` float32, channels averaged."""
        return self.waveform.mean(dim=0).numpy()


def load_wav(path: Path | str) -> tuple[torch.Tensor, int]:
    """``(channel, time)`` float32 tensor + sample rate, via the stdlib only.

    Lifted from ``phase0/gate_0g_0h.py``, which is what gates 0g and 0h ran on.
    """
    with wave.open(str(path), "rb") as w:
        if w.getsampwidth() != 2:
            raise ValueError(
                f"{path}: expected 16-bit PCM, got {w.getsampwidth() * 8}-bit — "
                f"call load_audio(), which converts first"
            )
        frames = w.readframes(w.getnframes())
        data = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
        data = data.reshape(-1, w.getnchannels()).T
        return torch.from_numpy(data.copy()), w.getframerate()


def load_audio(
    path: Path | str,
    *,
    work_dir: Path | None = None,
    sample_rate: int = TARGET_SAMPLE_RATE,
) -> Audio:
    """Decode `path`, converting through ffmpeg when the stdlib cannot read it.

    `work_dir` is where a converted copy lands — pass the session directory so
    U9's shred catches it. Defaults to the source file's own directory.
    """
    path = Path(path)
    try:
        waveform, sr = load_wav(path)
        if sr == sample_rate:
            return Audio(waveform=waveform, sample_rate=sr, path=path)
    except (wave.Error, ValueError, EOFError):
        pass  # not a WAV we can read, or the wrong rate — convert below

    work_dir = Path(work_dir) if work_dir is not None else path.parent
    work_dir.mkdir(parents=True, exist_ok=True)
    converted = work_dir / f"{path.stem}.{sample_rate}.wav"
    if converted.resolve() == path.resolve():
        raise ValueError(f"{path}: would convert onto itself")

    subprocess.run(
        [
            "ffmpeg", "-nostdin", "-loglevel", "error", "-y",
            "-i", str(path),
            "-ac", "1", "-ar", str(sample_rate), "-acodec", "pcm_s16le",
            str(converted),
        ],
        check=True,
    )
    waveform, sr = load_wav(converted)
    return Audio(waveform=waveform, sample_rate=sr, path=converted)


def resample(samples: np.ndarray, source_rate: int, target_rate: int) -> np.ndarray:
    """Rate-convert a mono signal. Used to feed the enrollment clip to
    pyannote's embedding model, which names its own sample rate (B3)."""
    if source_rate == target_rate:
        return samples.astype(np.float32)
    from math import gcd

    from scipy.signal import resample_poly

    g = gcd(source_rate, target_rate)
    return resample_poly(samples, target_rate // g, source_rate // g).astype(np.float32)
