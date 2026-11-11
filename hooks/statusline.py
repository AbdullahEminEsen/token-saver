#!/usr/bin/env python3
"""
Optional status line (terminal Claude Code only; plugins can't set it, so add it by hand):

  "statusLine": {"type": "command", "command": "python3 /path/to/statusline.py"}

Shows:  Opus 5.5 | ctx ████░░░░░░ 41% (82k/200k) | 5h 23%
Turns yellow at your first threshold and red at your last (with a single threshold: yellow at
80% of it, red at it). Stays green until you have chosen one.
"""
import json, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import data_dir, thresholds  # noqa: E402


def k(n):
    return f"{n/1000:.0f}k" if n < 1_000_000 else f"{n/1_000_000:.1f}M"


def main():
    try:  # the bar characters aren't in legacy Windows code pages
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    try:
        d = json.load(sys.stdin)
    except Exception:
        print("ctx ?")
        return
    if not isinstance(d, dict):
        print("ctx ?")
        return
    cw = d.get("context_window") or {}
    pct, size, sid = cw.get("used_percentage"), cw.get("context_window_size") or 200000, d.get("session_id")
    if pct is not None and sid:
        try:
            st = data_dir() / "state"
            st.mkdir(exist_ok=True)
            (st / f"{sid}.json").write_text(json.dumps(
                {"used_percentage": pct, "context_window_size": size, "ts": time.time()}))
        except Exception:
            pass
    parts = [(d.get("model") or {}).get("display_name", "")]
    if pct is not None:
        p = float(pct)
        used = p * size / 100
        bar = "█" * int(round(p / 10)) + "░" * (10 - int(round(p / 10)))
        levels, _ = thresholds()
        red = levels[-1] if levels else float("inf")
        yellow = levels[0] if len(levels) > 1 else red * 0.8
        color = "\033[31m" if used >= red else "\033[33m" if used >= yellow else "\033[32m"
        parts.append(f"{color}ctx {bar} {p:.0f}% ({k(used)}/{k(size)})\033[0m")
    rl = ((d.get("rate_limits") or {}).get("five_hour") or {}).get("used_percentage")
    if rl is not None:
        parts.append(f"5h {float(rl):.0f}%")
    print(" | ".join(x for x in parts if x))


if __name__ == "__main__":
    main()
