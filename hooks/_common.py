"""Shared helpers: works both as a Claude Code plugin and as a manual install."""
import datetime, os
from pathlib import Path


def data_dir() -> Path:
    d = os.environ.get("CLAUDE_PLUGIN_DATA")
    p = Path(d) if d else Path.home() / ".claude" / "token-saver"
    p.mkdir(parents=True, exist_ok=True)
    return p


def opt(name: str, default: str) -> str:
    """Plugin option (set in /config) > TS_* env var > default."""
    for key in (f"CLAUDE_PLUGIN_OPTION_{name.upper()}", f"TS_{name.upper()}"):
        v = os.environ.get(key)
        if v not in (None, ""):
            return v
    return default


def log(msg: str) -> None:
    try:
        with open(data_dir() / "hook.log", "a", encoding="utf-8") as fh:
            fh.write(f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S} {msg}\n")
    except Exception:
        pass
