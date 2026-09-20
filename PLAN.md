# Build Hub

**This file is the single source of truth for build state.** Everyone syncs
here. If it isn't ticked here, it isn't done.

Architecture decisions live in [SPEC.md](SPEC.md) (**D1**–**D27**). Tool
contracts live in [TOOLS.md](TOOLS.md). Step-by-step detail lives in
[phases/](phases/). This file tracks *progress*, not design.

---

## Protocol — read this before editing

1. **Check your blockers before you start, and re-check before each step.**
   This file is the source of truth for *whether you can begin*, not just for
   recording that you did. Your phase file's header names what blocks you;
   confirm every one of those boxes is `[x]` and every gate you depend on
   reads `pass` or `fail` — not `—`. Starting behind an unanswered gate is how
   a track builds an afternoon of work on an assumption that was never true.
2. **Only edit your own track's section.** Four people editing one file
   conflicts constantly. Your section is yours; everything else is read-only
   to you.
3. **Tick the box the moment a step's acceptance criteria pass** — not when
   you think it'll pass, not at the end of a batch. Someone downstream is
   reading this to decide whether they can start.
4. **Append to the Log, never edit it.** Append-only merges cleanly; edits in
   place do not.
5. **Record gate results immediately.** Gate outcomes change *other people's*
   plans. A failed 0g rewrites Track B's whole approach.
6. **Pull before you read, not just before you push.** `git pull --rebase
   origin main` at the start of every step. Pulling only when you are ready to
   write means working an hour against stale state — including a gate that
   failed while you were building on it passing.
7. **If a gate you depend on comes back `fail`, stop and re-read your phase
   file.** Every gate has a documented degraded mode; it is the plan, not a
   surprise. Do not keep going on the assumption it will be fixed.
8. **If you are blocked, park properly.** Mark the step `[!]`, add a Blockers
   row saying what you need and who can clear it, and then do the next step in
   your track that is *not* blocked. Do not idle, and do not work around a
   blocker by guessing at what the upstream step will produce.
9. **If you deviate from SPEC.md, log it and say why.** Then update SPEC.md.
   Silent drift across eight files is how the architecture dies.

Status markers: `[ ]` not started · `[~]` in progress · `[x]` done ·
`[!]` blocked (add a line to Blockers)

---

## Status at a glance

| Track | Owner | Progress | State |
|---|---|---|---|
| Phase 0 — environment | agent-phase-0 | 9 / 9 | **done** |
| Phase 1 — foundations | Evan + agent | 5.5 / 6 | 1e — clip in; enrollment + long visit left |
| Track A — knowledge base | Evan + agent | 13 / 13 | **done** |
| Track B — audio | agent-track-b | 4 / 6 | **B1-B2-B4-B6 done**; B3 + B5 wait on 1e's enrollment and a listen |
| Track C — extraction | | 0 / 6 | **can start now** |
| Track D — interface | | 10 / 10 | **done** |
| Phase 3 — integration | | 0 / 5 | waits on all tracks |
| Phase 4 — demo | | 0 / 4 | waits on Phase 3 |

## Gate results — record immediately, others depend on these

**`—` means not answered, and not answered means do not proceed.** If your
track waits on a gate, its row must say `pass` or `fail` before you start the
steps behind it. A blank is not "probably fine"; it is "nobody has checked."

| Gate | Question | Result | Decided by | Consequence |
|---|---|---|---|---|
| **0g** | pyannote imports + runs on Python 3.14? | **pass** | agent-phase-0 | fail → Track B goes single-speaker, every dose blocking |
| **0h** | MPS turn boundaries match CPU? | **pass** — 0.0 ms delta, use MPS | agent-phase-0 | fail → CPU only, ~8 min per 15 min audio |
| **B5** | word offsets good enough for click-to-play? | **structural pass** — real `Session` reproduces fixture 1c exactly; 28/28 quotes resolve at the fixture's own offsets. The listening half is unanswered. | agent-track-b | fail → check you're on large-v3, not turbo |
| **C2** | does `compile_json_schema(VisitExtraction)` compile at all? | — | | fail → post-hoc parse + retry; span verification still holds |
| **C3** | verbatim quote fidelity holding? | — | | fail → 8-bit 9B, then 35B MoE |
| **3c** | thresholds calibrated? | — | | no labeled data — bias toward flagging |

---

## Phase 0 — Environment · [phases/PHASE-0-environment.md](phases/PHASE-0-environment.md)

- [x] **0a** repo init, specs committed
- [x] **0b** pip install the stack · CLOCK
- [x] **0c** ffmpeg resolves
- [x] **0d** openFDA downloaded, 14 parts / 1.77 GB · CLOCK
- [x] **0e** `PYANNOTE_METRICS_ENABLED=false` in profile **and** in code *(set it above the pyannote import — it is read at import time)*, plus `HF_HUB_OFFLINE=1` / `TRANSFORMERS_OFFLINE=1` once weights are cached *(**0i** is what caches them — the flag alone turns a lazy fetch into a hard failure, it does not prevent one)*
- [x] **0f** diarization model loads (ungated mirror, no token)
- [x] **0i** all **four** model weights pre-cached, each verified to **load** offline · CLOCK
- [x] **0g** GATE — pyannote on Python 3.14
- [x] **0h** GATE — MPS output matches CPU

## Phase 1 — Foundations · [phases/PHASE-1-foundations.md](phases/PHASE-1-foundations.md)

- [x] **1a** HUMAN — data contract agreed, `contracts.py` committed
- [x] **1b** repo skeleton committed
- [x] **1c-i** HUMAN — `fixtures/golden_visit.json` (`Session`), all **8** D16 cases planted
- [x] **1c-ii** HUMAN — `fixtures/golden_extraction.json` (dispositioned items) — **Track D is blocked without this**; a `Session` has no items to render
- [x] **1d** HUMAN — role-play script, drugs verified, 2 speakers
- [~] **1e** HUMAN — clip **recorded and ingested**; long visit + 10 s enrollment still needed

---

## Track A — Knowledge base + tools · [phases/PHASE-2A-knowledge-base.md](phases/PHASE-2A-knowledge-base.md)

*Owner:* ____  ·  *No ML dependencies. Nothing blocks this.*

- [x] **A1** RXNCONSO → SQLite (watch the trailing pipe)
- [x] **A2** RXNSAT `SPL_SET_ID` slice
- [x] **A3** normalization + salt-stripped key
- [x] **A3.5** filter `SY`/`TMSY` by dose pattern, add `PIN` → **18,094-string** name index *(do this BEFORE A4 — see SPEC §7)*
- [x] **A4** indexes: exact, salt-stripped, Double Metaphone
- [x] **A5** frequency prior from product counts
- [x] **A5.5** salt table — the **32** `IN` concepts with 2+ `PIN` children *(lands at **20** under a marketed-salt filter — see Deviations)*
- [x] **A6** `resolve_medication` + margin test + `salt_unspecified`
- [x] **A7** brand → ingredient via SBD brackets
- [x] **A8** openFDA → SQLite FTS5 *(needs 0d)*
- [x] **A9** `parse_sig` — `not_specified` ≠ `unparseable`
- [x] **A10** `resolve_date` — anchor injected, past direction works
- [x] **A11** cross-validation vs available strengths

**Build the two databases before running anything** (both gitignored — 233 MB
and 1.8 GB, rebuildable in 7 s and 37 s):

    /Users/evancanty/vn-shared/.venv/bin/python -m visitnotes.kb.build
    /Users/evancanty/vn-shared/.venv/bin/python -m visitnotes.kb.openfda

## Track B — Audio · [phases/PHASE-2B-audio.md](phases/PHASE-2B-audio.md)

*Owner:* ____  ·  *Needs 0g, 0h, 1e.*

- [x] **B1** Whisper large-v3-mlx → `Word[]` (**not turbo**)
- [x] **B2** pyannote, `exclusive_speaker_diarization`
- [~] **B3** enrollment match → `role`, manual override — *works, but rehearsed
  against a proxy sample cut from the take itself. Needs 1e's real 10 s
  enrollment before anyone calls it validated.*
- [x] **B4** word → turn assignment, `char_offset` assertion passes
- [~] **B5** GATE — structural half **pass**; the ear test needs a human
- [x] **B6** unexpected-speaker cluster-distance check

## Track C — Extraction + verification · [phases/PHASE-2C-extraction.md](phases/PHASE-2C-extraction.md)

*Owner:* ____  ·  *Needs 1a, 1c. Builds on the fixture, not on Track B.*

- [ ] **C1** schemas — no free-text field anywhere
- [ ] **C2** GATE — xgrammar compiles the real `VisitExtraction`, + logits processor
- [ ] **C3** GATE — turn-chunked prompt, verbatim fidelity on 9B
- [ ] **C4** span verification, offsets by `str.find`
- [ ] **C4.5** association check — mention turn vs sig/date turn (**D16 cat 8**)
- [ ] **C5** all **8** D16 dispositions fire on the fixture

## Track D — Review UI + output · [phases/PHASE-2D-interface.md](phases/PHASE-2D-interface.md)

*Owner:* ____  ·  *Needs 1a, 1c. Builds on the fixture, not on Track B.*

Steps are **U**1–U10. `D1`–`D27` are SPEC decision IDs; this track used to
number its steps D1–D9 too, which made *"D8 — approve: shred the audio (D2)"*
mean two different documents in one sentence.

- [x] **U1** localhost app shell
- [x] **U2** consent capture at session start (**D27**) — required before recording
- [x] **U3** review list — only blocking items demand attention; header shows the **discarded count** (D16 cat 1)
- [x] **U4** click-a-line → audio playback (clinician only)
- [x] **U5** blocking-item resolution, keyboard-only
- [x] **U6** action card templates — `change_kind` never printed as fact unless derived
- [x] **U7** extractive summary — no generated prose
- [x] **U8** print stylesheet, 18px+, clinician footer **+ consent line**
- [x] **U9** approve → shred audio **and logs**, write FHIR, print
- [x] **U10** 24 h expiry sweep — **exempt pre-computed demo sessions (4a)**

---

## Phase 3 — Integration · [phases/PHASE-3-integration.md](phases/PHASE-3-integration.md)

- [ ] **3a** swap fixture for real Track B output
- [ ] **3b** first end-to-end run — **stopwatch the whole pipeline**, not just the review → ____ s
- [ ] **3c** HUMAN GATE — tune thresholds
- [ ] **3d** D16 sweep, all **8** categories on real audio
- [ ] **3e** time the review against the 60 s target → ____ s

## Phase 4 — Demo · [phases/PHASE-4-demo.md](phases/PHASE-4-demo.md)

- [ ] **4a** pre-compute the long file — **and exempt it from U10's sweep**, or it deletes itself before the demo
- [ ] **4b** Wi-Fi off, full run, no outbound attempts
- [ ] **4c** HUMAN — rehearse the five judge questions
- [ ] **4d** re-verify every script drug against the final build

---

## Blockers — live

*Anything marked `[!]` goes here with what you need to get unstuck. Delete the
line when it clears.*

| Step | Blocked on | Who can clear it | Raised |
|---|---|---|---|
| — | — | — | — |

## Deviations from SPEC.md

*Log any departure from a D-number decision, with the reason. Then update
SPEC.md — this table is the record, not the decision.*

| Decision | What we did instead | Why | Who |
|---|---|---|---|
| 0c / D1 | pyannote is fed `{"waveform", "sample_rate"}` dicts, not file paths | torchcodec's `libtorchcodec_core*.dylib` needs FFmpeg **shared** libs (`libavutil.56`–`.61`); `imageio-ffmpeg` ships only a static CLI, and there is no Homebrew on this machine. Every file-path decode raises `OSError`. The waveform dict is pyannote's own documented workaround (`core/io.py:49`) and adds no dependency — which also keeps D1 intact. Whisper is unaffected: it shells out to the ffmpeg CLI, which resolves. | agent-phase-0 |
| D16 / TOOLS §4 | `golden_extraction.json` defines a post-C5 disposition envelope (`disposition`, `d16_categories`, `flags[].render`, `header` counts) and a concrete `SummarySelection` shape | TOOLS §4 specifies what the *model* emits and §5 the verification steps, but never the shape Track D consumes. Track D is blocked without one, so 1c-ii pins it. Not a departure from a decision — a gap being filled. Update TOOLS §4 when C1 lands. | Phase 1 |
| A5.5 / TOOLS §1 | the salt table has **20** ingredients, not ~32 | The spec's 32 was measured but the method was not written down, and it does not reproduce. A bare 2+-`PIN`-children join gives **151**, most of them hydration states (*X anhydrous* vs *X monohydrate*) and formulations (*amphotericin B liposomal*) — not two dosing schedules wearing one name. Restricting the suffix to a real counter-ion vocabulary gives 50; additionally requiring **both salts to be marketed** (each heads ≥1 `SCD`/`SBD`) gives 20. A salt nobody sells cannot be what the clinician meant. Metoprolol, hydroxyzine, bupropion, paroxetine and diclofenac are all on it; the flag stays rare enough to mean something. | Track A |
| A3 / TOOLS §1 | `SALT_WORDS` is 46 counter-ions, not the 6 A3 names | With the 6 named words the A5.5 join found **2** ingredients: `paroxetine mesylate`, `hydroxyzine pamoate` and `diclofenac potassium` never salt-stripped to their `IN`. The list is now the counter-ion vocabulary measured off this release's `PIN` suffixes, deliberately excluding hydration states, formulation words and source qualifiers. The salt key is only ever a fallback lookup, which is what makes a broader list survivable. | Track A |
| A6 / TOOLS §1 stage 3 | Double Metaphone is a **scoring term**, not the blocking step | The spec blocks on the phonetic code — "retrieve everything sharing the query's code". Measured, that fails A6's own acceptance case: `doublemetaphone("metropolol")` is `MTRPLL` and `doublemetaphone("metoprolol")` is `MTPRLL`. The error is a metathesis, and a phonetic code is a positional encoding — robust to substitution, brittle to transposition. It dropped the one example the stage exists to recover, silently, as an `unresolved` with an empty candidate list. A3.5 cut the index to 18,094 strings and a Jaro-Winkler pass over all of them takes **14 ms**, so blocking buys speed we do not need at the cost of recall we cannot audit. | Track A |
| A6 / TOOLS §1 | added `MAX_FUZZY_EDIT_DISTANCE = 3` | *Coumadin* is not in the Current Prescribable release (discontinued brand) and scored **0.81 against *Comtan*** — above threshold, clear of #2, `resolved`. Jaro-Winkler weights the prefix and `co` is a prefix many drugs share. Truncating converts it to `unresolved`, i.e. D16 category 4: raw heard text, flagged, near-matches offered. | Track A |
| A6 / TOOLS §1 | added head-of-phrase backoff | TOOLS §1 tells the model to pass the drug name alone; `golden_extraction.json` passes `"the metoprolol up to 50 milligrams"` and `"the lisonopril at 10"` and expects both `resolved`. Both documents are right in their own terms. A phrase that fails whole is retried on the tokens before the first preposition or numeral. Deliberately not a general prefix sweep — that version "resolved" the fixture's category-4 plant `"the other blood pressure pill"`. | Track A |
| TOOLS §1 | `source_release` is **09082026**, not the "09012026" TOOLS.md names | 09012026 is the mtime of the files inside the zip. The release readme says September 08, 2026. It is read from `Readme_Full_Prescribe_*.txt` at build time and the builder refuses to guess if the readme is missing. | Track A |
| PHASE-1 1a sketch | `Turn` gained `char_start`/`char_end`; `Session` gained `session_dir`; `Word.text` whitespace rule made explicit | C4.5 needs turn bounds to answer D16 cat 8 cheaply; D2/D3 retention covers logs and scratch files, not just the `.wav`; the leading-space ambiguity in mlx-whisper's `WordTiming.word` would break every citation silently. | Phase 1 |

---

## Log — append only, newest at the bottom

Format: `HH:MM · <step> · <what happened>`

```
21:55 · 0a · repo pushed to github.com/point25xengineer/visit-notes (private)
18:25 · spec · review pass landed. SPEC/TOOLS/phases corrected against the
        actual RxNorm release. Headlines: name index was 67% dose-bearing
        product strings (A3.5); PIN was unindexed so metoprolol succinate vs
        tartrate resolved silently to the bare ingredient (A5.5); D16 gained
        category 8 (cross-turn association); D27 added (patient consent);
        Track D steps renamed U1-U10. Nothing was deleted — see git diff.
18:52 · 0b · stack installed into ONE shared venv at ../vn-shared/.venv (not
        four). All of mlx 0.32.2 / mlx-lm 0.31.3 / xgrammar 0.2.7 /
        mlx-whisper 0.4.3 / pyannote.audio 4.0.7 / transformers 5.17.0 /
        torch 2.14.0 import clean on Python 3.14.7. cp314 wheels all present.
18:52 · 0c · ffmpeg 7.1 via imageio-ffmpeg, symlinked to ~/.local/bin/ffmpeg
        (already on PATH). BUT torchcodec cannot decode: it wants FFmpeg
        SHARED libs and the static CLI is not one. See Deviations — pyannote
        gets waveform dicts. Track B: do not call pipeline(path).
18:53 · 0d · openFDA 1.8 GB, 14/14 parts, every one passes `unzip -t`, all
        real zips not HTML error pages. In ../vn-shared/openfda, symlinked in.
18:53 · 0e · PYANNOTE_METRICS_ENABLED=false + HF_HUB_OFFLINE/TRANSFORMERS_
        OFFLINE in ~/.zshrc, and in code as env_guard.py, which also RAISES if
        imported after pyannote/torch — the setting is read at import time, so
        a late import silently does nothing. Verified both ways: guarded
        is_metrics_enabled() is False, unguarded it is True. PRESENTATION-NOTES
        item 4 reads true.
18:53 · 0f · speaker-diarization-community-1 loads from the ungated mirror,
        no token, no gate form. Weights cached, and it loads again with
        HF_HUB_OFFLINE=1 — 4b's Wi-Fi-off risk is retired for diarization.
18:54 · 0g · GATE PASS. Diarized a 28 s two-speaker clip end to end on 3.14.
        3 turns, boundaries clean, speakers A/B/A as spoken. API notes for
        Track B: result is DiarizeOutput, use `.speaker_diarization` before
        .itertracks(); kwarg is token=. Caveat: clip is macOS `say` TTS, not
        real speech — 1e's recording should re-confirm. Single-speaker
        fallback NOT needed.
18:54 · 0h · GATE PASS. Same clip, cpu vs mps: worst boundary delta 0.0 ms,
        labels identical. USE MPS. 4.9x real-time on MPS vs 3.5x on CPU —
        both far better than the ~0.55x the plan budgeted, so the long demo
        file is affordable. Re-run on 1e's 15-min recording before trusting
        it at length.
18:55 · 0x · Track A unblock: the briefing says RxNorm is unzipped on disk;
        it was still a .zip. Unzipped to ../vn-shared/rrf (RXNCONSO.RRF etc.
        at the top level, nesting flattened) and symlinked as ./rrf, with
        ./openfda alongside. `phase0/check_env.py` runs every Phase 0 check
        in one command — run it before starting a track.
18:55 · 1b · skeleton committed: visitnotes/{audio,tools,kb,extract,verify,
        render,ui}, fixtures/, tests/, all with __init__.py.
18:55 · 1a · contracts.py committed and merged to main — rebase before your
        next commit. Three additions beyond the PHASE-1 sketch, all agreed:
        (1) Turn.char_start/char_end + Session.turn_at_offset(), so C4.5 can
        ask "which turn did this quote come from" without scanning words —
        D16 cat 8 is the residual risk and should not rest on a hand-rolled
        loop. (2) Word.text excludes whitespace and the offset contract is
        exact: transcript_text[off:off+len(text)] == text, validated for
        every word on construction. mlx-whisper emits " metoprolol" with a
        leading space; unspecified, B strips it and C does not and every
        citation is off by one silently. This validator IS B4's assertion,
        and it runs when golden_visit.json loads. (3) Consent rejects
        obtained=False (D27).
18:55 · 1a · Session gained session_dir, and audio_path is validated to live
        inside it. D2/D3 retention covers logs, ffmpeg scratch and tracebacks
        — all PHI. audio_path alone invites unlink(audio_path) at U9, which
        shreds the .wav and leaves the log beside it. U9's owner: shred the
        directory. 13 tests in tests/test_contracts.py cover all of it.
19:07 · 0e · whisper-large-v3-mlx (2.9 GB) pre-cached and verified with
        HF_HUB_OFFLINE=1: transcribes at 4.9x real-time with word timestamps.
        Both models now load with the network off, so 4b cannot be ambushed
        by a lazy fetch on stage. Track B: use path_or_hf_repo=
        'mlx-community/whisper-large-v3-mlx' — NOT turbo.
19:35 · 0i · NEW STEP, and it closes a real hole: 0e's HF_HUB_OFFLINE=1 does
        not prevent a runtime download, it converts one into a hard failure.
        It was written assuming a caching step that did not exist. 0i is that
        step. All three models now cached AND verified to load offline, 8.4 GB
        of blobs: pyannote 31 MB, whisper-large-v3-mlx 3.08 GB (already done
        at 19:07), Qwen3.5-9B-4bit 5.98 GB (new — was absent entirely). B1 and
        C3 will no longer discover a 6 GB download mid-build on venue Wi-Fi.
        check_env.py now asserts all three, so this cannot silently regress.
19:35 · 0i · Two traps, both recorded in PHASE-0 §0i. (1) `du -sh` on
        ~/.cache/huggingface/hub/models--* reports ~20 KB for a fully cached
        3 GB model — HF puts content in blobs/ and fills the snapshot dir with
        symlinks. It is indistinguishable from a metadata-only stub. Use
        `du -shL`, or just run check_env.py. (2) 0e put HF_HUB_OFFLINE=1 in
        ~/.zshrc, so any shell opened after it inherits the flag and
        snapshot_download FAILS instead of downloading — pull with
        `env -u HF_HUB_OFFLINE -u TRANSFORMERS_OFFLINE`.
19:35 · 0i · NOT pulled, deliberately: D24's demo candidate
        Qwen3.6-35B-A3B-4bit (20.43 GB) and the 8-bit 9B fallback (~10 GB).
        Both are contingent on C3's outcome and 30 GB of speculative download
        is worse than the risk it hedges. Track C: if C3 picks either, pull it
        THAT MOMENT, not on demo day.
19:36 · 0i · Track C, worth knowing before C2: Qwen3.5-9B-4bit is a THINKING
        model. Straight out of the box it answered a one-word prompt with
        'Thinking Process:\n1. **Analyze the Request:**...'. Thinking tokens
        and an xgrammar logits processor are a bad combination — the grammar
        constrains the JSON, and the model wants to emit prose first.
        tok.apply_chat_template(..., enable_thinking=False) is supported and
        prefills an empty <think></think> block. Load+generate is 1.1s + 1.8s,
        so C2 is cheap to iterate on.
20:25 · 0i · MoE pulled after all, on request, while the Wi-Fi was good:
        Qwen3.6-35B-A3B-4bit, 20.43 GB, 42 minutes. Verified offline —
        loads in 4.6 s, generates. Cache is now 27 GB across four models and
        4a can no longer be ambushed by a 20 GB download. check_env.py
        asserts all four.
20:26 · 0i · Track C, a number worth having before C3: the MoE measured
        **41 tok/s** here (300-token generation, enable_thinking=False),
        against SPEC D24's ~65-85 tok/s estimate. Time the real extraction
        prompt before choosing on speed — the 9B-vs-MoE gap is narrower than
        the spec table implies. The 8-bit 9B fallback is still NOT cached;
        pull it the moment C3 wants it, not on demo day.
20:35 · 0i · Track C — I ran the thinking-vs-xgrammar experiment rather than
        leave it as a warning, because the predicted symptom was wrong and it
        would have cost C2 an hour. CORRECTION to my own 19:36 line: thinking
        tokens under a logits processor do NOT look like a schema failure.
        The grammar masks <think> away, so the output stays schema-valid
        either way — both enable_thinking=True and False returned parseable
        JSON with quotes that passed a verbatim `in transcript` check. The
        real symptom is subtler and worse: quote SELECTION drifts. Thinking-on
        returned sig_quote='increase the metaprolol succinate from 25 mg to
        50 mg. Once daily in the morning.' where thinking-off returned the
        tight 'Once daily in the morning.' A sig quote that swallows the dose
        sentence is precisely the cross-turn association smear C4.5 hunts
        (D16 cat 8). So: still pass enable_thinking=False — but debug it at
        C4/C4.5 by looking at quote BOUNDARIES, not at JSON validity.
20:36 · 0i · Track C — three concrete C2 landmines, hit in 20 minutes. This
        is a PRIOR, not the gate; C2 is still yours to record. (1) GOOD NEWS:
        compile_json_schema(..., strict_mode=True) COMPILES on xgrammar
        0.2.7 / cp314, and constrained generation works end to end on the 9B.
        (2) xgr.apply_token_bitmask_inplace is TORCH-ONLY — it reads
        logits.device and dies with AttributeError on an mlx array. Unpack
        the packed int32 bitmask yourself: np.unpackbits(np.asarray(bm).
        view(np.uint8), bitorder='little') then mx.where(bits, logits, -inf).
        (3) Two shape/state traps in that unpack: the bitmask unpacks to the
        tokenizer vocab (248096) but mlx logits are padded wider (248320), so
        pad the mask with zeros to logits.shape[-1]; and GrammarMatcher
        RAISES once it accepts the stop token if you keep filling masks, so
        guard with `if m.is_terminated(): return logits` or generation dies
        after the JSON closes.
19:07 · 0e · Track B, empirical confirmation of 1a's offset contract: whisper
        emits words WITH a leading space (' Good', ' morning.'). 1a specified
        Word.text excludes whitespace, so B4 must strip and shift char_offset
        by the same amount. The contract validator catches it if you don't.
19:05 · 1d · script committed: fixtures/roleplay_script.md, 39 turns, ~3:30,
        hypertension follow-up, 2 speakers. Drugs verified against this
        RxNorm release before writing, not after: metoprolol IN 6918,
        succinate PIN 221124, tartrate PIN 203191, lisinopril IN 29046, all
        SAB=RXNORM and unsuppressed. Nobody says a salt anywhere in the
        script — that is the A5.5 plant. Follow-up is TEN days, not two
        weeks: every multiple of seven from the hackathon weekend lands on a
        weekend, and ten days is a weekday from Fri/Sat/Sun alike, so the
        printed page is safe whichever anchor D18's mtime actually reads.
        Stays [~] until 1c mirrors it turn for turn.
19:40 · 1c · BOTH fixtures committed and merged to main. Tracks C and D are
        unblocked — neither waits on audio or on each other now.
        golden_visit.json: 35 turns, 461 words, 2449 chars, validates as a
        Session. golden_extraction.json: 3 medications, 1 appointment, 2 red
        flags, 1 loose thread, 1 discarded. 37 tests green.
19:40 · 1c · Three things worth knowing before you build on them.
        (a) The fixtures are GENERATED by fixtures/build_golden.py, and so is
        the script's dialogue block. Content is hand-authored in the TURNS
        list; offsets are computed with str.find over the same transcript
        Track C searches, because hand-typing 461 char_offsets produces a
        fixture that is subtly wrong in a way nobody finds until citations
        point at the wrong characters. Edit TURNS, re-run, never hand-edit
        the JSON or the generated markdown — a test fails if you do.
        (b) 1d's turn count changed from 39 to 35. Consecutive same-speaker
        lines were merged, because exclusive_speaker_diarization emits one
        turn per contiguous stretch of one voice; the old numbering
        predicted turns pyannote cannot produce and would have made B5's
        diff noise. Category 8 got STRONGER: the sig at turn 20 is now 8
        turns from the mention at turn 12, with lisinopril the nearest drug
        named in between and nothing re-anchoring metoprolol after it.
        (c) golden_extraction.json pins a post-C5 shape that TOOLS.md never
        defined — §4 gives the model's output and §5 the verification steps,
        but the envelope Track D consumes (disposition, d16_categories,
        flags[].render, header counts) was not written down anywhere, and
        SummarySelection is referenced without a definition. Track D will
        build against this file. C5: if you emit something different, change
        the fixture and TELL Track D. Logged under Deviations.
20:55 · 1e · Short clip recorded and ingested: 2:48, mono 48 kHz AAC, one
        mixed room mic (not per-speaker tracks — diarization has real work to
        do). whisper-large-v3-mlx: 11.9 s for 165.7 s of audio, 13.9x
        real-time, 480 words. Still needed: the 10 s clinician enrollment
        sample (D20 does not work without it) and the long visit for 4a.
20:55 · 1c · FIXTURES REBUILT FROM THE REAL TAKE. golden_visit.json is no
        longer a prediction — it carries actual mlx-whisper words, timings
        and per-word probabilities, read from the newly committed
        fixtures/asr_words.json so it rebuilds without the audio. What stays
        hand-authored is the turn segmentation and speaker roles, which is
        deliberate: a fixture built from pyannote's own output cannot test
        pyannote. B5 still has an independent target to diff against.
20:55 · 1c · Three things every track needs to know about the real
        transcript. (1) WHISPER WRITES DIGITS: "25 milligrams", "150 over
        90", "the 50s" — not "twenty-five". Every quote matched against a
        transcript must expect digits. All fixture quotes were rewired.
        (2) The fuzzy-match plant landed on LISINOPRIL, not metoprolol.
        Metoprolol was correct all three times; lisinopril came back as
        lisonopril (p=0.90) and lysinopril (p=1.00, 1.00, 0.78) — all edit
        distance 1. Two at p=1.00, so no confidence signal flags them and
        resolve_medication's fuzzy path is the only thing that catches it.
        Track A: A6's margin test now has a real case, not a synthetic one.
        (3) The scripted cat 2 plant did NOT land — the actor read
        "sixty-two" and Whisper heard it right at p=1.00. A better one
        landed free at T23: "will the 50 make me more tired" with 50 at
        p=0.14, a dose numeral in a patient turn.
20:55 · 1c · Track B and C, a correction to D16 category 2 as specified.
        SEGMENT-LEVEL SIGNALS DO NOT DISCRIMINATE in mlx-whisper output:
        no_speech_prob=0.101, compression_ratio=1.64, avg_logprob=-0.098 are
        IDENTICAL across nine consecutive segments, because the 30 s decode
        window's stats are stamped onto every segment inside it. D16 cat 2
        says to read them per segment; at sentence granularity they carry no
        information. Per-word probability is the signal that works. Do not
        build a threshold on the segment fields without checking this first.
20:55 · A1-A5.5 · knowledge base built, `data/rxnorm.db` (233 MB, 7 s from
        RRF). Every count in SPEC §7 reproduced exactly off this release:
        name index **18,094** (IN 5,844 / BN 4,134 / PIN 1,943 / SY 2,902 /
        TMSY 3,271), concept table 246,241, SPL_SET_ID over 21,594 rxcuis,
        and the dose-bearing rows left in the index are exactly the 42 IN /
        27 BN / 43 PIN A3.5 says are real names with numerals. The A3.5
        filter is worth the trouble it was given.
20:55 · A5.5 · the salt table does NOT reproduce at 32, and the gap is
        methodological rather than a data change. A bare "IN with 2+ PIN
        children" join gives **151** — hydration states and liposomal
        formulations, not dosing schedules. Counter-ion vocabulary only: 50.
        Also requiring both salts to be MARKETED: **20**, metoprolol among
        them. Logged under Deviations with the full chain. If anyone re-runs
        the original measurement and finds the 32, say so — the list is one
        `GROUP BY` and I would rather match the spec than argue with it.
20:55 · A7 · two bugs that a count alone would never have shown, both found
        by asserting on metoprolol specifically. (1) RxNorm writes the
        release rate FIRST — `24 HR metoprolol succinate 25 MG Extended
        Release Oral Tablet` — so the ingredient head of every ER product was
        `24 hr metoprolol succinate`, a key nothing looks up. It cost A5.5
        the hero drug and undercounted A5's frequency prior on exactly the
        drugs most likely to be discussed. (2) The bracketed brand in this
        release is `[Toprol]`, not `[Toprol-XL]` as TOOLS §1 spells it —
        A7 is a string parse over a format that varies, and it varies.
20:56 · A6 · `resolve_medication` lands. Four things worth knowing before
        you build on it, all in Deviations with reasoning:
        (a) Double Metaphone is a SCORING term, not the blocking step.
        `metropolol` -> MTRPLL, `metoprolol` -> MTPRLL: the spec's bucket
        drops A6's own acceptance case, because the error is a metathesis and
        a phonetic code is positional. Recall is exhaustive instead — 14 ms
        over all 18,094 keys, which is nothing against one constrained
        generation per turn.
        (b) thresholds are SET, not tuned: SCORE_THRESHOLD 0.72,
        AMBIGUITY_MARGIN 0.06, RECALL_FLOOR 0.80, MAX_FUZZY_EDIT_DISTANCE 3.
        No labeled data exists, so they are biased toward flagging and
        Phase 3c owns them. Gate 3c stays `—`.
        (c) the margin does real work: `predisone` comes back **ambiguous**
        between predniSONE (0.721) and predniSOLONE (0.709). Two different
        drugs at different potencies, and a 0.012 gap is a coin toss the
        patient cannot see.
        (d) the edit-distance cap exists because *Coumadin* is not in the
        Current Prescribable release and scored 0.81 against **Comtan** —
        resolved, confident, wrong.
20:56 · A6 · all three medications in `golden_extraction.json` now resolve to
        the status and RxCUI the hand-authored fixture recorded, including
        `salt_unspecified` on bare metoprolol and `unresolved` on "the other
        blood pressure pill". Track C/D: two fields of the fixture's
        hand-written resolution differ from the real tool and yours should
        follow the tool — `source_release` is **09082026** (the fixture says
        09012026, which is a file mtime), and `available_strengths` are
        RxNorm's `RXN_AVAILABLE_STRENGTH` values like `25 MG (expressed as
        metoprolol succinate)`, not the fixture's `25 MG Oral Tablet`.
20:57 · A9 · `parse_sig`. Two bugs found by running it rather than reading
        it: `\bdaily\b` matched inside "twice daily" and returned
        frequency_per_day=1.0 — a silent halving from a regex that looked
        right, so the frequency alternatives are now ordered most-specific
        first; and the route cue "puff" matched inside "puffy", classifying
        *"when your ankles look puffy"* as inhaled. Note `partial` has TWO
        causes and only one leaves a remainder: leftover text, or complete
        coverage with a missing component ("10 mg for ten days" has no
        frequency). Both are prefilled+flagged; inventing a remainder to
        satisfy the field would be the tool lying about its own coverage.
20:57 · A10 · `resolve_date`. The bug here was the worst of the lot and it is
        worth stating plainly: a bare `\bback in\b` past cue matched
        **"come back in three weeks"** — the most common follow-up phrasing
        there is, and TOOLS §3's own worked example — and resolved it three
        weeks BEFORE the visit. A past cue inverts the arithmetic, it does
        not degrade it. All past cues are now narrowed to specific forms.
        D18's display string is computed end to end: "come back in three
        weeks, which is Friday, October 9" from a Friday 2026-09-18 visit.
20:58 · A8 · openFDA into FTS5, `data/openfda_labels.db` (1.8 GB, 37 s over
        the 14 zips). 262,883 records, 253,906 with indexed text. **64,660
        carry an openfda.rxcui — 25%**, exactly as SPEC warns, which is why
        the join is on SPL_SET_ID. The full chain runs: spoken "metoprolol
        succinate" -> RxNorm 221124 -> 50 SPL set ids -> the FDA's own
        geriatric_use paragraph. That paragraph is public-domain,
        FDA-authoritative, quotable, and no model wrote it.
20:58 · A11 · cross-validation fires on all four: unmarketed strength
        (250 mg metoprolol succinate), two sigs for one drug -> **blocking,
        D16 cat 7**, schedule over a stated maximum -> blocking, and the
        salt-unspecified flag restated where the dose lives. Multiples of a
        marketed strength are NOT flagged — "two 25 mg tablets" is 50 mg and
        is not an error.
20:54 · A · two packages added to the shared venv, both pure-offline and
        both tiny: `jellyfish` 1.2.1 (Jaro-Winkler, Levenshtein) and
        `metaphone` 0.6 (Double Metaphone). Nothing in Track A calls a
        network. If you rebuild the venv, reinstall them or `test_tools.py`
        fails at import.
20:59 · A · Track A done. 128 new tests in tests/test_kb.py and
        tests/test_tools.py, 176 green overall. Both databases are gitignored
        and rebuild in 7 s and 37 s from data already on disk; the tests skip
        rather than fail when they are absent, so a fresh clone is not stuck.
        Gate 3c is still `—` and is still Phase 3's to answer.

20:58 · B1/B2/B4 · Pipeline runs end to end on 1e's take, and the result
        is the fixture. 2:48 of audio in 21.7 s wall clock (7.7x real-time,
        both models, MPS): 35 turns, 480 words, 2463 chars — every one of
        those identical to golden_visit.json. transcript_text matches
        character for character; all 35 turn boundaries match turn for turn;
        all 35 cluster labels match, SPEAKER_00 for SPEAKER_00. That last one
        is luck, not contract — do not depend on pyannote's numbering.
        Entry point: `python -m visitnotes.audio.pipeline <audio>
        --session-dir <dir>`. Diff: `python -m visitnotes.audio.b5_gate
        <session.json>`.
20:58 · B5 · GATE, structural half: PASS. The strong result is not the turn
        counts, it is that all 28 quotes in golden_extraction.json resolve in
        the REAL transcript **at the fixture's own char_offsets**, and
        turn_at_offset() returns the fixture's turn id for every one. That is
        the D14 bridge proven on real audio rather than asserted: Track C can
        search Track B's output and Track D can cite it. Track C — you can
        swap the fixture for sessions/b5/session.json today; 3a is already
        half done.
20:58 · B5 · GATE, listening half: UNANSWERED, and it needs a human with
        headphones. What I could check objectively is all clean — word starts
        strictly monotonic, no zero-length words, longest word 1.32 s (no DTW
        blowouts), every word inside its own turn's time span, per-word
        probability median 1.00 and only 8 of 480 under p=0.50. Five random
        citations to play: 0:05.84 'leaves', 1:40.22 'the', 2:05.34 'for',
        2:20.76 'So', 2:39.72 'bring'. If they land late or early, the first
        thing to check is that you are on large-v3-mlx and not turbo.
20:58 · B4 · Zero words dropped on the real take — no silence inventions to
        catch, because the clip is 2:48 of continuous conversation. The drop
        rule is therefore UNEXERCISED by real audio and is covered only by
        unit tests (tests/test_audio_assemble.py, 10 of them). It earns its
        keep on 4a's long file, which has real pauses. Do not read "0
        dropped" as "the rule works".
20:58 · B3 · Enrollment matching works, but read the caveat. Against a proxy
        sample cut from the take's own turn 18, the clinician's cluster came
        back at cosine distance 0.095 and the patient's at 0.937 — a margin
        of 0.84 against a 0.10 floor. The 0.095 is circular and means little;
        the 0.937 does not — that is a real measurement of how far apart
        these two voices sit, and it says the decision has enormous headroom.
        1e still owes a genuine 10 s sample. Thresholds
        (MAX_CLINICIAN_DISTANCE 0.65, MIN_MARGIN 0.10) are uncalibrated
        guesses for 3c to tune. With no enrollment at all every role is
        `unknown` and every dose goes blocking — that path is tested.
20:58 · B6 · Fires correctly, and the first two ways I built it did not.
        Spliced an 11 s third voice into the take at 1:29, ran the pinned
        num_speakers=2. (1) Centroid separation alone: MISSES — the two
        centroids stayed 0.948 apart, because folding a third person in
        barely moves a centroid. (2) Mean within-cluster spread at
        min_duration=1.0: MISSES, and worse, it is not separable at all — a
        1-second "Mm-hm" embeds 0.71 from its own speaker's centroid, FURTHER
        than the genuine intruder at 0.65. Any threshold between those would
        have flagged every real session. What works is (3) embed only
        intervals >= 2.0 s and take the WORST interval, not the mean: the two
        real speakers' worst intervals drop to 0.20 and 0.32 while the
        intruder stays at 0.65. One outlier is exactly what one intruder
        looks like, and averaging it across ten honest intervals erases the
        only evidence you have. The flag names the timestamp so the clinician
        can go listen: "a segment at 1:29 sounds unlike the rest of
        SPEAKER_00". Silent on the genuine take. Threshold 0.45 on n=1 file
        each — 3c should tune it.
20:58 · B1 · Priming prompt is the generic top-50 with metoprolol and
        lisinopril REMOVED, and the removal is in the code as a named
        constant with the reason attached. Priming on the demo's own drugs
        would suppress the mistranscription the demo exists to catch. Note
        the take's real ASR errors landed on lisinopril, not metoprolol (1c,
        20:55) — so the exclusion is load-bearing for beat #2, not
        hypothetical.
20:58 · B4/D18 · visit_date on the real run is 2026-09-19, the audio mtime.
        The fixture pins 2026-09-18. Both are correct, and 1d chose a ten-day
        follow-up precisely so the printed date lands on a weekday from any
        of Fri/Sat/Sun. Do not "fix" the fixture to match — mtime wins at
        runtime, by D18.
20:58 · B · Two things Track D should know. (1) `Session` stayed clean:
        dropped words, B6 flags and per-cluster distances ride in an
        `IngestResult` beside it, not bolted onto the contract. U3's
        discarded count reads `IngestResult.dropped`; U5's blocking items
        read `.flags`. (2) `RoleAssignment.override(cluster)` is D20's
        "that's me" button, and it clears the identity flags it was raised to
        answer.
20:58 · U1-U10 · Track D done. `python -m visitnotes.ui.app` serves the
        review screen on 127.0.0.1:8765; `--sweep` runs U10 and exits;
        `--audio PATH` attaches a recording, since golden_visit.json names
        fixtures/sessions/golden/visit.m4a and that file is not in git. 48
        tests in tests/test_track_d.py, one per done-when row. Stdlib
        http.server + Jinja2 and NO web framework: 4b turns the Wi-Fi off,
        and a pip install on venue Wi-Fi is a demo-day risk taken for a
        router we do not need.
20:58 · U4 · A landmine worth knowing about if anyone else serves media from
        BaseHTTPRequestHandler: it answers every GET with the whole file and
        no Accept-Ranges, so the browser reports seekable=[0,0] and SILENTLY
        IGNORES currentTime=64.35. Clicking a line played the visit from the
        top — no error, no console warning, just the wrong two seconds.
        Caught it by reading p.seekable in the live page, not from a test.
        app.py now serves 206 Partial Content and answers HEAD. Verified in
        the browser: click "the metoprolol up to 50 milligrams" → starts
        64.49s, stops 65.35s, pauses. Cues are computed from Word.start, so
        this is contract 1a paying for itself a second time.
20:58 · U3/U6 · Two calls Track C should know about, because they read the
        same fixture. (a) A flagged line cues to the LEAST CONFIDENT WORD in
        the span, not the start of the turn — with a dose numeral at p=0.14
        inside a confident sentence, cueing to the sentence makes the doctor
        listen and guess which part we doubted. (b) Sigs are never merged
        across turns in the action card, even when one turn has the dose and
        another the frequency. That merge is exactly the D16 cat 8 smear, and
        a template doing it silently would launder the thing the flag warns
        about. `actioncard._select_sig` picks ONE sig and prints only what it
        carries.
20:58 · U3 · The rebuilt fixture (11b32a4) carries D16 cat 2 as well, which
        1c's first cut did not. Nothing needed changing — the review screen
        reads `flags[].render` rather than switching on category — but it is
        a good sign for 3d: the categories are data, not code paths.
20:58 · U9 · Verified end to end in the browser, not just in tests: consent
        → review → two keystrokes to settle both blocking flags → A →
        signed. Shred took visit.wav AND review.log; the FHIR
        DocumentReference landed in data/records/<id>/ (outside session_dir,
        so the shred cannot reach it) and its base64 attachment decodes
        byte-for-byte equal to the printed HTML. One render, two
        destinations — D26 holds.
20:58 · U10 · Sweep runs on server startup and as `--sweep` for cron. 4a:
        call `retention.mark_demo_fixture(session_dir)` WHEN YOU CREATE the
        pre-computed session, not later — verified a 40-hour-old marked
        session survives a sweep that takes its unmarked neighbours.
20:58 · 3a · The seam is `ReviewSession.load_fixture()` in visitnotes/ui/
        state.py — one method, and it is the only place Track D touches JSON.
        It re-homes the session into data/sessions/<id>/ before validating,
        because the fixture's own session_dir points inside fixtures/, which
        is checked-in test data U9 must never shred. Track B: hand it a
        Session and delete the json.loads. Nothing else in Track D reads a
        file path.
```

---

## Cut list — agreed in advance, cut from the bottom

| | |
|---|---|
| 1 | Clip → transcript → `parse_sig` → action card with click-to-play |
| 2 | `resolve_medication` fuzzy match |
| 3 | D16 disposition table |
| 4 | `resolve_date` |
| 5 | Diarization + enrollment |
| 6 | Extractive summary (keep the card) |
| 7 | openFDA grounding + `geriatric_use` |
| 8 | Cross-validation vs available strengths |
| 9 | FHIR `DocumentReference` |
| 10 | Pre-computed long file |

**Cutting 5 removes a safety property, not a feature.** Without diarization
there is no clinician attribution, so D19's rule — a dose may only be extracted
from a clinician turn — has nothing to stand on, and the companion's *"should I
take four?"* can print as fact. If you cut it, adopt gate 0g's degraded mode in
the same breath: **every dose becomes a D16 category 3 blocking item**, and say
so on stage.

Never in scope: live recording, interaction checking, mobile delivery,
3+ speakers.
