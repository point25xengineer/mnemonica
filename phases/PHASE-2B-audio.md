# Phase 2 · Track B — Audio pipeline

**Goal:** audio in, `Session` out — words with timestamps and confidence,
grouped into turns with roles assigned.

**Blocked by:** gates 0g and 0h, plus recording 1e. **Blocks:** Phase 3 only —
Tracks C and D build on the fixture, not on you.

---

## Phase 0 results — read before B1 *(recorded by Phase 0; see PLAN.md Log)*

**0g PASS.** pyannote 4.0.7 diarizes end to end on Python 3.14.7. Single-speaker
fallback is **not** in play — build the full diarization path. Confirmed API
shape: `pipeline(...)` returns a `DiarizeOutput`, so reach through
`out.speaker_diarization` before `.itertracks(yield_label=True)`, or pass
`legacy=True`. The kwarg is `token=`.

**0h PASS — use MPS.** Same clip on `cpu` and `mps` gave a worst boundary delta
of **0.0 ms** with identical labels. Throughput was 4.9× real-time on MPS and
3.5× on CPU — both far above the ~0.55× the plan budgeted, so CPU is a usable
fallback and the long demo file is affordable either way. The gate ran on a
28 s synthetic clip; re-run `phase0/gate_0g_0h.py` against 1e's real recording
before trusting MPS at 15-minute length.

**Do not call `pipeline(path)`.** torchcodec cannot decode on this machine —
its `libtorchcodec_core*.dylib` needs FFmpeg *shared* libraries and
`imageio-ffmpeg` ships only a static CLI. Every file-path decode raises
`OSError`. Load the audio yourself and pass
`{"waveform": (channel, time) float32 tensor, "sample_rate": int}` — pyannote's
own documented workaround, and it keeps D1 intact. There is a stdlib-only
`load_wav` in [`phase0/gate_0g_0h.py`](../phase0/gate_0g_0h.py); lift it.
Whisper is unaffected — it shells out to the ffmpeg CLI, which resolves.

**Environment.** One shared venv:
`/Users/evancanty/vn-shared/.venv/bin/python`. Run
`python phase0/check_env.py` first. Start every entry point with
`import env_guard` **above** the pyannote import — it raises if you don't.
`whisper-large-v3-mlx` is pre-cached, so `HF_HUB_OFFLINE=1` will not bite you.

---

## B1 — Whisper → `Word[]`

```python
import mlx_whisper
r = mlx_whisper.transcribe(
    path,
    path_or_hf_repo="mlx-community/whisper-large-v3-mlx",
    word_timestamps=True,
)
```

**Use `whisper-large-v3-mlx` (3.08 GB), not turbo** — D21. Neither ships
`alignment_heads`, so mlx-whisper falls back to "last half of decoder layers"
for the DTW alignment that produces word timestamps. On large-v3 that's 16
layers; **on turbo it's 2**, because turbo has only 4 decoder layers total.
Your entire provenance chain is word offsets. The 1.5 GB saving is not worth
it.

Pass the model ID explicitly — the in-code default differs from the README.

You get `WordTiming(word, tokens, start, end, probability)` per word, plus
`avg_logprob`, `compression_ratio`, `no_speech_prob` per segment. The per-word
`probability` is what feeds D16 category 2.

**Optional upstream win:** seed `initial_prompt` with the ~50 most commonly
prescribed drug names. Whisper produces correct spellings more often, so Track
A's fuzzy stage fires less. Prompt context is ~224 tokens, so this is a
targeted bias, not the whole vocabulary.

**Use the generic top-50 — never the demo script's own drugs.** Two reasons,
and the second is the one that bites: priming on the script overfits the demo
so measured accuracy means nothing, *and* it suppresses the `metropolol` →
*metoprolol* mistranscription that is demo beat #2. You would be priming away
the error you are about to show off catching.

**Keep the segment-level fields.** `no_speech_prob` and `compression_ratio`
are not decoration — D16 category 2 now reads them, because Whisper large-v3
invents text over silence and an exam room has plenty of it. Those inventions
land in `transcript_text`, which makes them **verifiable spans**: `str.find`
will confirm them and span verification cannot help. The standard heuristic is
`compression_ratio` > ~2.4 or a high `no_speech_prob`; B4's drop rule catches
most of the rest.

**Done when:** `Word` records populate with sane timestamps and varied
probabilities, and segment-level fields are carried through rather than
discarded.

## B2 — Diarization

```python
pipeline = Pipeline.from_pretrained("pyannote-community/speaker-diarization-community-1")
out = pipeline(path, num_speakers=2)
turns = out.exclusive_speaker_diarization
```

Use **`exclusive_speaker_diarization`** — new in 4.0, built for downstream
transcription. It strips overlapping speech, so assigning each word to a
speaker is an unambiguous interval lookup rather than a tie-break.

`num_speakers=2` per D19/Q22c. Accepted limitation: a third voice is merged
into an existing cluster rather than detected. B6 mitigates.

Remember the 4.x breaks: `DiarizeOutput` not `Annotation`; `token=` not
`use_auth_token=`; `legacy=True` if you want the old shape.

**Done when:** two clusters with sensible boundaries on the recorded clip.

## B3 — Enrollment match → `role`

pyannote emits anonymous `SPEAKER_00` / `SPEAKER_01` with **no role
identification** — named-speaker voiceprinting is a paid cloud feature. But
4.x exposes `out.speaker_embeddings`, an array aligned to
`speaker_diarization.labels()`. That's the intended hook.

Embed the 10-second enrollment sample from 1e, compare against each cluster
embedding, assign `role="clinician"` to the nearest and `role="other"` to the
rest.

Keep a manual "that's me" override (D20, Q15c) — embeddings fail on colds,
masks and speakerphone.

**Done when:** the clinician's cluster is identified correctly, and the
override flips it.

## B4 — Word → turn assignment

Interval lookup from `exclusive_speaker_diarization`. Build
`Session.transcript_text` by concatenation, and set each word's `char_offset`
as its index into that exact string.

**A word with no overlapping diarization interval is DROPPED, not snapped to
the nearest speaker.** It never enters `transcript_text` and never gets an
offset. This is three lines and it is the cheapest anti-hallucination measure
in the build: Whisper's silence inventions occur exactly where pyannote found
no speech, so exclusive diarization removes most of them for free — before
they can become quotable spans. Compute `char_offset` *after* dropping.

**This is the bridge to D14.** If `char_offset` doesn't index into the same
string that span verification searches, every citation silently breaks.

**Done when:** `transcript_text[w.char_offset:w.char_offset+len(w.text)] ==
w.text` holds for every word. Assert it. And a clip with 20 seconds of silence
produces no words over that stretch.

## B5 — Emit `Session` · GATE

Persist `visit_date` from the audio file's mtime **once, at ingest** (D18).
Never read mtime again — `cp` without `-p` resets it, and so does any
re-encode.

**GATE:** run B1–B5 on the recorded clip and diff against fixture 1c. Then
listen to five random citations and decide whether the word offsets are
accurate enough for click-to-play.

This is a judgment call, not a metric. If offsets are sloppy, the first thing
to check is that you are on `large-v3-mlx` and not turbo.

**Free the models between stages.** Whisper is 3.08 GB and the MoE is
20.43 GB against a ~36 GB practical working set. Stages run sequentially
(SPEC §2), so drop references and clear the MLX cache before loading the next
model rather than trusting it to happen in time.

**Done when:** the fixture and the real output agree on structure, and
playback lands on the right words.

## B6 — Unexpected-speaker check

After B3, check each cluster's distance from its assigned identity. If a
cluster's internal variance or distance is implausible, flag the session
`"unexpected speaker — review manually"`.

This converts the D19 silent-misattribution risk into a D16 blocking item.
~10 lines, and it's the difference between "we don't handle 3 speakers" and
"we detect when we might not be able to" — which is what
PRESENTATION-NOTES item 6 commits you to saying.

**Done when:** a deliberately 3-speaker test file raises the flag.

---

## If gate 0g failed

Single-speaker mode:

- skip B2, B3, B6 entirely
- all turns get `role="unknown"`
- **every dose becomes a D16 category 3 blocking item** — the clinician
  confirms each one
- say so on stage; the review flow already absorbs it

You lose the "companion asks four, doctor says two" beat. You do not lose
correctness, because nothing unattributed is ever printed as fact.

## Track B is done when

- [ ] `Session` validates against `contracts.py`
- [ ] the char_offset assertion passes for every word
- [ ] words outside every diarization interval are dropped, not reassigned
- [ ] clinician role assigned correctly, override works
- [ ] playback lands on the right words for five random citations
- [ ] `visit_date` persisted, not recomputed
