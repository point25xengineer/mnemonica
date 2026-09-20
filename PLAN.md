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
| Track A — knowledge base | | 0 / 13 | **can start now** |
| Track B — audio | | 0 / 6 | **can start now** — clip ingested; B3 needs the enrollment sample |
| Track C — extraction | | 0 / 6 | **can start now** |
| Track D — interface | | 0 / 10 | **can start now** |
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
| **B5** | word offsets good enough for click-to-play? | — | | fail → check you're on large-v3, not turbo |
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

- [ ] **A1** RXNCONSO → SQLite (watch the trailing pipe)
- [ ] **A2** RXNSAT `SPL_SET_ID` slice
- [ ] **A3** normalization + salt-stripped key
- [ ] **A3.5** filter `SY`/`TMSY` by dose pattern, add `PIN` → **18,094-string** name index *(do this BEFORE A4 — see SPEC §7)*
- [ ] **A4** indexes: exact, salt-stripped, Double Metaphone
- [ ] **A5** frequency prior from product counts
- [ ] **A5.5** salt table — the **32** `IN` concepts with 2+ `PIN` children
- [ ] **A6** `resolve_medication` + margin test + `salt_unspecified`
- [ ] **A7** brand → ingredient via SBD brackets
- [ ] **A8** openFDA → SQLite FTS5 *(needs 0d)*
- [ ] **A9** `parse_sig` — `not_specified` ≠ `unparseable`
- [ ] **A10** `resolve_date` — anchor injected, past direction works
- [ ] **A11** cross-validation vs available strengths

## Track B — Audio · [phases/PHASE-2B-audio.md](phases/PHASE-2B-audio.md)

*Owner:* ____  ·  *Needs 0g, 0h, 1e.*

- [ ] **B1** Whisper large-v3-mlx → `Word[]` (**not turbo**)
- [ ] **B2** pyannote, `exclusive_speaker_diarization`
- [ ] **B3** enrollment match → `role`, manual override
- [ ] **B4** word → turn assignment, `char_offset` assertion passes
- [ ] **B5** GATE — emit `Session`, diff against fixture
- [ ] **B6** unexpected-speaker cluster-distance check

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

- [ ] **U1** localhost app shell
- [ ] **U2** consent capture at session start (**D27**) — required before recording
- [ ] **U3** review list — only blocking items demand attention; header shows the **discarded count** (D16 cat 1)
- [ ] **U4** click-a-line → audio playback (clinician only)
- [ ] **U5** blocking-item resolution, keyboard-only
- [ ] **U6** action card templates — `change_kind` never printed as fact unless derived
- [ ] **U7** extractive summary — no generated prose
- [ ] **U8** print stylesheet, 18px+, clinician footer **+ consent line**
- [ ] **U9** approve → shred audio **and logs**, write FHIR, print
- [ ] **U10** 24 h expiry sweep — **exempt pre-computed demo sessions (4a)**

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
