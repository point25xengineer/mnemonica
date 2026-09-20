/* U4 + U5 — playback and the keyboard layer.
 *
 * D9's sixty seconds is not reachable with a mouse. Everything here is doable
 * from the home row: move, hear, answer, approve. The forms all work without
 * JavaScript too — this file drives the same <button>s a click would, so the
 * keyboard path and the mouse path cannot diverge.
 *
 * Space CYCLES the focused row's audio rather than playing one fixed clip.
 * With a contradiction the doctor has to hear both doses before choosing one,
 * and the alternative was a second key nobody would remember.
 *
 * Playback stops at the cue's end. An <audio> element left running plays the
 * rest of the visit into a quiet exam room, which is both alarming and, with
 * a patient still in the chair, a small privacy incident. */

(function () {
  const player = document.getElementById('player');
  const rows = Array.from(document.querySelectorAll('.row'));
  let focused = 0;
  let cueIndex = 0;
  let stopAt = null;

  function cuesIn(row) {
    const found = row.dataset.cueStart !== undefined ? [row] : [];
    return found.concat(Array.from(row.querySelectorAll('[data-cue-start]')));
  }

  function focus(index) {
    if (!rows.length) return;
    focused = Math.max(0, Math.min(index, rows.length - 1));
    cueIndex = 0;
    rows.forEach((r, i) => r.classList.toggle('focused', i === focused));
    const row = rows[focused];
    const details = row.querySelector('details');
    if (details) details.open = true;
    row.focus({ preventScroll: true });
    row.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  }

  function play(start, end) {
    if (!player || !player.getAttribute('src')) {
      // No audio on disk. Say so rather than failing silently — a dead Space
      // bar reads as a broken app, not as a missing recording.
      announce(`would play ${start.toFixed(1)}s–${end.toFixed(1)}s`);
      return;
    }
    stopAt = end;
    player.currentTime = start;
    player.play().catch(() => announce('playback blocked by the browser'));
  }

  function playElement(el) {
    if (!el) return;
    play(parseFloat(el.dataset.cueStart || '0'), parseFloat(el.dataset.cueEnd || '0'));
  }

  function announce(text) {
    let el = document.getElementById('announce');
    if (!el) {
      el = document.createElement('div');
      el.id = 'announce';
      el.setAttribute('role', 'status');
      el.style.cssText =
        'position:fixed;bottom:1rem;left:1.5rem;background:#16191d;color:#fff;' +
        'padding:.35rem .6rem;border-radius:6px;font-size:12px;z-index:9';
      document.body.appendChild(el);
    }
    el.textContent = text;
    clearTimeout(announce.timer);
    announce.timer = setTimeout(() => el.remove(), 2000);
  }

  if (player) {
    player.addEventListener('timeupdate', () => {
      if (stopAt !== null && player.currentTime >= stopAt) {
        player.pause();
        stopAt = null;
      }
    });
  }

  document.addEventListener('click', (event) => {
    // The little play glyph inside an answer button hears that option
    // WITHOUT choosing it — otherwise the only way to compare two doses is
    // to commit to one of them first.
    const hear = event.target.closest('.hear');
    if (hear) {
      event.preventDefault();
      event.stopPropagation();
      playElement(hear.closest('[data-cue-start]'));
      return;
    }
    const button = event.target.closest('button.play');
    if (!button) return;
    event.preventDefault();
    playElement(button);
  });

  document.addEventListener('keydown', (event) => {
    if (event.metaKey || event.ctrlKey || event.altKey) return;
    const tag = (event.target.tagName || '').toLowerCase();
    if (tag === 'input' || tag === 'textarea') return;

    const row = rows[focused];
    const key = event.key.toLowerCase();

    if (key === 'j' || key === 'arrowdown') { event.preventDefault(); focus(focused + 1); return; }
    if (key === 'k' || key === 'arrowup') { event.preventDefault(); focus(focused - 1); return; }

    if (event.key === ' ') {
      event.preventDefault();
      if (!row) return;
      const cues = cuesIn(row);
      if (!cues.length) return;
      playElement(cues[cueIndex % cues.length]);
      cueIndex += 1;
      return;
    }

    if (key >= '1' && key <= '9') {
      if (!row) return;
      // The first *unanswered* question on this row, so repeated digits walk
      // through a multi-question item instead of re-answering the first.
      const forms = Array.from(row.querySelectorAll('form.answers'));
      const form = forms.find((f) => !f.querySelector('.option.chosen')) || forms[0];
      if (!form) return;
      const choice = form.querySelectorAll('button.option')[parseInt(key, 10) - 1];
      if (choice) { event.preventDefault(); choice.click(); }
      return;
    }

    if (key === 'c') {
      if (!row) return;
      const confirm = row.querySelector('form[action="/promote"] button');
      if (confirm) { event.preventDefault(); confirm.click(); }
      return;
    }

    if (key === 'x') {
      if (!row) return;
      const drop = row.querySelector('.dropline button');
      if (drop) { event.preventDefault(); drop.click(); }
      return;
    }

    if (key === 'a') {
      const approve = document.getElementById('approve-button');
      if (approve) { event.preventDefault(); approve.click(); }
      else announce('still items to settle');
    }
  });

  focus(0);
})();
