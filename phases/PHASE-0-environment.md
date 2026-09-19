# Phase 0 — Environment

**Goal:** every dependency present and both risk gates answered, so no track
discovers a blocker at hour six.

**Blocked by:** nothing. **Blocks:** Track B only.

---

## 0a — Repo

Done. `main` branch, specs committed, `.gitignore` excludes the data.

**Done when:** `git log` shows the spec commit and `git status` is clean.

## 0b — Python stack · CLOCK

```bash
python3 -m pip install mlx==0.32.2 mlx-lm==0.31.3 xgrammar==0.2.7 \
  mlx-whisper==0.4.3 "pyannote.audio==4.0.7" transformers
```

torch arrives as a pyannote dependency and is 1–2 GB — this is the long pole.
Start it before anything else.

**Done when:** every package imports without error.

**Failure mode:** a package resolves but its transitive deps don't have cp314
wheels. Everything listed above was verified to have them; anything *else* you
add mid-build may not. Check before adding a dependency.

## 0c — ffmpeg

```bash
python3 -m pip install imageio-ffmpeg
```

Hard dependency for both Whisper and pyannote 4.x — the latter dropped sox and
soundfile for torchcodec, which is ffmpeg-only. No Homebrew here, so either
`imageio-ffmpeg` or a static build from evermeet.cx.

**Done when:** `ffmpeg -version` resolves, or the bundled binary path is
exported.

## 0d — openFDA bulk · CLOCK

**Do not construct the URLs by hand.** The part count and the zero-padding
both change between releases, and `seq -w 1 14` yields `01` where openFDA uses
four digits. Take the manifest:

```bash
mkdir -p openfda
curl -s https://api.fda.gov/download.json \
  | python3 -c "import json,sys;[print(p['file']) for p in json.load(sys.stdin)['results']['drug']['label']['partitions']]" \
  | while read -r url; do
      curl -fL --retry 3 -C - -o "openfda/$(basename "$url")" "$url" &
    done; wait
```

`-f` is the flag that matters: the original `-s` writes an error page silently
on a 404, and `du -sh` still looks about right. You find out at A8, hours
later. `--retry 3 -C -` survives hackathon Wi-Fi.

1.77 GB, CC0, no API key. Only step A8 needs it, so it can finish whenever.

**Done when:** `du -sh openfda` shows ~1.8 GB, **and every part passes
`unzip -t`.** Size alone does not prove a zip is intact.

## 0e — Kill telemetry · D4

```bash
export PYANNOTE_METRICS_ENABLED=false
```

pyannote 4.0.7 ships `metrics_enabled: true` and exports spans — including
audio duration and speaker counts — to `otel.pyannote.ai`. A dependency
phoning home destroys the D1 claim.

Put it in the shell profile **and** set it in code, so it survives someone
running a script in a fresh shell.

**Order matters, and this is the part that silently fails.** pyannote reads
the setting at **import time**. An `os.environ[...]` line *below*
`import pyannote.audio` does nothing at all — and you will believe telemetry
is off when it is not. In code it goes at the very top of the entry point,
above every pyannote import.

**Also pin the stack offline once weights are cached**, so 4b's Wi-Fi-off run
does not discover a lazy metadata fetch on stage:

```bash
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
```

**Done when:** it's in the profile, at the top of the entry point, the offline
vars are set, and item 4 of PRESENTATION-NOTES still reads true.

## 0f — Diarization model access

Use the **ungated mirror** and skip the HuggingFace account entirely:

```
pyannote-community/speaker-diarization-community-1
```

Same CC-BY-4.0 weights, no token, no gate form. The official repo
`pyannote/speaker-diarization-community-1` also works and its gate is
auto-approval (instant), but it needs an account.

**Done when:** the pipeline loads without a token.

---

## 0g — GATE · pyannote on Python 3.14

```bash
python3 -c "from pyannote.audio import Pipeline; print('import ok')"
```

Then diarize a 30-second clip end to end and print the turns.

Nobody has publicly reported this combination. Wheels and metadata say it
works. **Confirm before a line of Track B is written.**

Things that will trip you here, all from the 3.x → 4.x break:

- Model ID is `speaker-diarization-community-1`, not `speaker-diarization-3.1`
- The kwarg is `token=`; `use_auth_token=` was removed and raises `TypeError`
- `pipeline(...)` returns a **`DiarizeOutput` dataclass**, not an `Annotation`.
  Every 3.x tutorial calling `.itertracks(yield_label=True)` on the result
  breaks. `legacy=True` restores the old shape

**Pass:** turns print with sensible boundaries.
**Fail:** single-speaker mode — skip diarization, treat the transcript as one
stream, make *every* dose a D16 blocking item. Degraded but honest, no new
dependencies, and the clinician review already absorbs it.
**Do not** install Python 3.13 mid-event; it reshuffles the whole stack
including MLX.

## 0h — GATE · MPS correctness

Diarize the same file twice, `device="cpu"` and `device="mps"`, and diff the
turn boundaries.

CPU runs ~0.55× real-time on M5 Pro — 15 minutes of audio takes about 8. So
MPS matters. But pyannote's MPS issues are closed *wontfix*, including one
titled "wrong timestamps when using MPS on a Mac M1", and wrong timestamps
silently corrupt the provenance chain — the one thing the product rests on.

The old `aten::_fft_r2c` crash is already patched internally, so you should
not need `PYTORCH_ENABLE_MPS_FALLBACK`.

**Pass:** boundaries match within a few milliseconds. Use MPS.
**Fail:** CPU only. Budget ~8 min per 15 min of audio, and let it push you
toward the shorter demo clip.

---

## Phase 0 is done when

- [ ] every package imports
- [ ] ffmpeg resolves
- [ ] openFDA downloaded
- [ ] telemetry disabled in profile and code, **set above the pyannote import**
- [ ] `HF_HUB_OFFLINE=1` / `TRANSFORMERS_OFFLINE=1` set, weights pre-cached
- [ ] every openFDA part passes `unzip -t`
- [ ] 0g answered, and if it failed, single-speaker mode is written into
      PHASE-2B as the plan rather than a surprise
- [ ] 0h answered, and the device choice is recorded somewhere Track B reads
