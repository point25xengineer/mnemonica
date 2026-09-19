"""Environment guard — import this FIRST, above every other import (D4, 0e).

pyannote 4.0.7 ships ``metrics_enabled: true`` and exports OpenTelemetry spans
— audio duration, speaker counts — to ``otel.pyannote.ai``. The setting is read
at **import time**, so an ``os.environ[...]`` line below ``import
pyannote.audio`` does nothing at all, and you will believe telemetry is off
when it is not.

Every entry point starts with::

    import env_guard  # noqa: F401  — must precede pyannote/transformers

``HF_HUB_OFFLINE``/``TRANSFORMERS_OFFLINE`` pin the stack to the local cache so
4b's Wi-Fi-off run does not discover a lazy metadata fetch on stage. Weights
are already cached (0f). To deliberately fetch a new model, run with
``VN_ALLOW_HF_NETWORK=1``.
"""

import os

os.environ["PYANNOTE_METRICS_ENABLED"] = "false"

if os.environ.get("VN_ALLOW_HF_NETWORK") != "1":
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"

# Do not set HF_HOME — the HuggingFace cache is shared across worktrees on
# purpose, so models download once (BRIEFING §7).

for _name in ("pyannote.audio", "transformers", "torch"):
    if _name in __import__("sys").modules:
        raise RuntimeError(
            f"env_guard imported after {_name}; telemetry settings are read at "
            f"import time, so they had no effect. Move 'import env_guard' to "
            f"the top of the entry point."
        )
