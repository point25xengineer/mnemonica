"""Shared fixtures.

The important one is `full_scope`. D29 narrows what a human sees to
medications, but appointments, red flags and loose threads still extract, still
verify and still render correctly — the tests for them are capability tests,
not statements about the current product scope. They widen `SCOPE` for their
duration rather than being deleted or weakened, so that flipping D29 back does
not require rewriting a suite to prove something that was working all along.
"""

from __future__ import annotations

import pytest

from mnemonica.render import model

ALL_KINDS = ("medications", "appointments", "red_flags", "loose_threads", "summary")


@pytest.fixture
def full_scope(monkeypatch):
    """Render every extracted kind, as D29 would if it were reversed."""
    monkeypatch.setattr(model, "SCOPE", ALL_KINDS)
    return ALL_KINDS
