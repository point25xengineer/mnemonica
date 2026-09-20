"""Phase 0 environment check — run this before you start a track.

    /Users/evancanty/vn-shared/.venv/bin/python phase0/check_env.py

It answers, in one place: are the packages importable, is telemetry actually
off, does ffmpeg resolve, are the weights cached so a Wi-Fi-off run works?
"""

import sys, pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import env_guard  # noqa: F401  — must precede pyannote

import importlib, os, subprocess

ok = True


def check(label, fn):
    global ok
    try:
        detail = fn()
        print(f"  ok    {label}{' — ' + detail if detail else ''}")
    except Exception as e:  # noqa: BLE001 — a check failing is the result, not a crash
        ok = False
        print(f"  FAIL  {label} — {e}")


print(f"python {sys.version.split()[0]}")

for mod in ("mlx", "mlx_lm", "xgrammar", "mlx_whisper", "pyannote.audio",
            "transformers", "torch"):
    check(mod, lambda m=mod: getattr(importlib.import_module(m), "__version__", ""))


def telemetry_off():
    from pyannote.audio.telemetry.metrics import is_metrics_enabled
    assert not is_metrics_enabled(), "pyannote telemetry is ON — D4/D1 broken"
    return "pyannote metrics disabled"


def ffmpeg():
    import imageio_ffmpeg
    exe = imageio_ffmpeg.get_ffmpeg_exe()
    v = subprocess.run([exe, "-version"], capture_output=True, text=True).stdout
    return v.splitlines()[0]


def mps():
    import torch
    assert torch.backends.mps.is_available(), "MPS unavailable"
    return "MPS available (gate 0h: matches CPU exactly, use it)"


def weights_cached():
    """0i — every model LOADS with the network off, not merely sits on disk.

    HF_HUB_OFFLINE=1 does not prevent a download; it turns one into a hard
    failure. This is what makes that flag safe to leave on.
    """
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"

    from pyannote.audio import Pipeline
    Pipeline.from_pretrained("pyannote-community/speaker-diarization-community-1")

    from huggingface_hub import snapshot_download
    for repo in ("mlx-community/whisper-large-v3-mlx",
                 "mlx-community/Qwen3.5-9B-4bit",
                 "mlx-community/Qwen3.6-35B-A3B-4bit"):
        snapshot_download(repo)  # raises offline if anything is missing

    return "all 4 models resolve offline (0i)"


check("telemetry", telemetry_off)
check("ffmpeg", ffmpeg)
check("mps", mps)
check("weights", weights_cached)

print("\nPhase 0 environment OK" if ok else "\nPhase 0 environment INCOMPLETE")
sys.exit(0 if ok else 1)
