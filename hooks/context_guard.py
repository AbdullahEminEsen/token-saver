#!/usr/bin/env python3
"""
UserPromptSubmit hook — context guard.

When the conversation context crosses a token threshold, tells Claude to ask the user
(before doing anything) whether to continue the request in a fresh session.

Thresholds are ABSOLUTE TOKENS, not percentages: every message re-processes the whole
context, so 300k tokens costs the same whether the window is 200k or 1M. This also means
we never need to know the window size (the Desktop app doesn't run status lines).

Options (plugin /config, or TS_* env vars for a manual install):
  warn_tokens        "150000,300000"  thresholds; each fires once per session
  idle_minutes       "60"             after a break this long the prompt cache is cold...
  idle_min_tokens    "60000"          ...so suggest a fresh session if context is at least this big
"""
import json, sys, time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import data_dir, log, opt  # noqa: E402


def num(name, default):
    try:
        return int(float(opt(name, default)))
    except ValueError:
        return int(default)


def read_transcript(path):
    """Return (tokens in context after the last main-agent reply, last activity ISO timestamp)."""
    used, last_ts = None, None
    try:
        with open(path, "rb") as fh:
            fh.seek(0, 2)
            fh.seek(max(0, fh.tell() - 2_000_000))
            lines = fh.read().decode("utf-8", "ignore").splitlines()
    except Exception:
        return None, None
    for line in reversed(lines):
        try:
            e = json.loads(line)
        except Exception:
            continue
        if last_ts is None and e.get("timestamp"):
            last_ts = e["timestamp"]
        if e.get("isSidechain") or e.get("type") != "assistant":
            continue
        u = (e.get("message") or {}).get("usage")
        if u:
            used = sum(u.get(k, 0) or 0 for k in (
                "input_tokens", "cache_read_input_tokens",
                "cache_creation_input_tokens", "output_tokens"))
            break
    return used, last_ts


def from_statusline(sid):
    """Fallback: value written by statusline.py (terminal only)."""
    try:
        d = json.loads((data_dir() / "state" / f"{sid}.json").read_text())
        if time.time() - d.get("ts", 0) > 600:
            return None
        return float(d["used_percentage"]) * float(d.get("context_window_size") or 200000) / 100
    except Exception:
        return None


def idle_minutes(iso):
    try:
        return (time.time() - datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()) / 60
    except Exception:
        return 0


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return
    sid = data.get("session_id", "unknown")
    prompt = (data.get("prompt") or "").strip()
    if prompt.startswith("/") or "handoff" in prompt.lower():
        return

    used, last_ts = read_transcript(data.get("transcript_path", ""))
    if used is None:
        used = from_statusline(sid)
    if used is None:
        log("guard: context size unknown")
        return
    kt = f"~{used/1000:.0f}k tokens"
    log(f"guard: context {kt}")

    levels = sorted(int(float(x)) for x in opt("warn_tokens", "150000,300000").split(",") if x.strip())
    state = data_dir() / "state"
    state.mkdir(exist_ok=True)
    warned_f = state / f"{sid}.warned"
    warned = {int(x) for x in warned_f.read_text().split()} if warned_f.exists() else set()

    reason = None
    hit = [lv for lv in levels if used >= lv and lv not in warned]
    if hit:
        reason = f"the conversation context is {kt}; every message re-processes all of it"
        warned.update(hit)
    elif (idle_minutes(last_ts) >= num("idle_minutes", 60)
          and used >= num("idle_min_tokens", 60000) and 0 not in warned):
        reason = (f"the user is back after a long break and the context is {kt}; the prompt cache "
                  "has most likely expired, so this message re-processes the full context at full price")
        warned.add(0)
    if not reason:
        return
    warned_f.write_text(" ".join(map(str, sorted(warned))))
    log(f"guard: WARNING shown ({kt})")

    ctx = f"""[token-saver] {reason}.
BEFORE starting on the user's request in this message, ask exactly one short question in the
user's own language, equivalent to:
"Context is at {kt}. To save tokens, shall I continue this request in a fresh session? (yes/no)"
Call no tools; ask the question and stop.
- If the user says yes: use the token-saver handoff skill (or follow the same template yourself)
  to write .claude/handoff.md in the project root. Put the user's still-unfinished request,
  VERBATIM, under "## Pending request". Then tell the user only, in their language:
  "Done. Type /clear, then say 'continue'."
- If the user says no: carry out the request normally and don't ask again.
"""
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit",
                                             "additionalContext": ctx}}))


if __name__ == "__main__":
    main()
