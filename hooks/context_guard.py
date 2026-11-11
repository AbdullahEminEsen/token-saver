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
import json, re, sys, time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import data_dir, log, opt  # noqa: E402


DEFAULT_LEVELS = "150000,300000"


def num(name, default):
    try:
        return int(float(opt(name, default)))
    except (ValueError, OverflowError):
        return int(default)


def parse_levels(raw):
    """"150000, junk,," -> [150000]. Bad or non-positive entries are skipped; if nothing
    usable is left, the defaults apply (a typo must never disable the guard)."""
    levels = set()
    for part in str(raw).replace(";", ",").split(","):
        try:
            v = int(float(part.strip()))
        except (ValueError, OverflowError):
            continue
        if v > 0:
            levels.add(v)
    return sorted(levels) or parse_levels(DEFAULT_LEVELS)


def read_warned(path):
    """Thresholds already shown this session. A corrupt state file counts as empty."""
    try:
        return {int(x) for x in path.read_text().split()}
    except Exception:
        return set()


def usage_total(usage):
    """Sum the token fields of a usage block; tolerates nulls, strings and missing keys."""
    if not isinstance(usage, dict):
        return 0
    total = 0
    for k in ("input_tokens", "cache_read_input_tokens",
              "cache_creation_input_tokens", "output_tokens"):
        v = usage.get(k)
        if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0:
            total += int(v)
    return total


def read_transcript(path):
    """Return (tokens in context after the last main-agent reply, last activity ISO timestamp)."""
    used, last_ts = None, None
    if not path:
        return None, None
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
        if not isinstance(e, dict):
            continue
        if last_ts is None and isinstance(e.get("timestamp"), str):
            last_ts = e["timestamp"]
        if e.get("isSidechain") or e.get("type") != "assistant":
            continue
        msg = e.get("message")
        total = usage_total(msg.get("usage") if isinstance(msg, dict) else None)
        if total:  # synthetic/error replies carry an all-zero usage block; keep looking
            used = total
            break
    return used, last_ts


def from_statusline(sid):
    """Fallback: value written by statusline.py (terminal only)."""
    try:
        d = json.loads((data_dir() / "state" / f"{sid}.json").read_text())
        if time.time() - d.get("ts", 0) > 600:
            return None
        used = float(d["used_percentage"]) * float(d.get("context_window_size") or 200000) / 100
        return used if used > 0 else None
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
    if not isinstance(data, dict):
        return
    sid = re.sub(r"[^A-Za-z0-9_.-]", "_", str(data.get("session_id") or "unknown"))
    prompt = str(data.get("prompt") or "").strip()
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

    levels = parse_levels(opt("warn_tokens", DEFAULT_LEVELS))
    state = data_dir() / "state"
    state.mkdir(exist_ok=True)
    warned_f = state / f"{sid}.warned"
    seen = read_warned(warned_f)
    # Re-arm thresholds the context has dropped back under (after /compact), so growing
    # past them again warns again. 0 is the idle-break marker and stays.
    warned = {lv for lv in seen if lv == 0 or used >= lv}

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
        if warned != seen:
            warned_f.write_text(" ".join(map(str, sorted(warned))))
        return
    warned_f.write_text(" ".join(map(str, sorted(warned))))
    log(f"guard: WARNING shown ({kt})")

    ctx = f"""[token-saver] {reason}.
BEFORE starting on the user's request in this message, ask exactly one short question in the
user's own language, equivalent to:
"Context is at {kt}. To save tokens, shall I continue this request in a fresh session? (yes/no)"
Call no tools; ask the question and stop.
- If the user says yes: use the token-saver handoff skill (or follow the same template yourself)
  to write .token-saver/handoff.md in the project root. Put the user's still-unfinished request,
  VERBATIM, under "## Pending request". Once the file is written, tell the user only, in their
  language: "Done. Type /clear, then say 'continue'." If the file could not be written, say so
  instead; never say "Done" without it.
- If the user says no: carry out the request normally and don't ask again.
"""
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit",
                                             "additionalContext": ctx}}))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # a hook must never block or break the user's prompt
        log(f"guard: error {exc!r}")
