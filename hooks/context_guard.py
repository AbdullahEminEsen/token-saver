#!/usr/bin/env python3
"""
UserPromptSubmit hook — context guard.

When the conversation context crosses a token threshold, tells Claude to ask the user
(before doing anything) whether to continue the request in a fresh session.

There is no built-in threshold. Until the user has chosen one, the first prompt of a session
makes Claude ask "at how many tokens should I notify you?"; this hook reads the answer from
the user's next message and saves it. "token-saver 200k", "token-saver off" and
"token-saver status" change or show it later.

Thresholds are ABSOLUTE TOKENS, not percentages: every message re-processes the whole
context, so 300k tokens costs the same whether the window is 200k or 1M. This also means
we never need to know the window size (the Desktop app doesn't run status lines).

Options (plugin /config, or TS_* env vars for a manual install):
  warn_tokens        e.g. "150k,300k" thresholds; overrides the saved answer
  idle_minutes       "60"             after a break this long the prompt cache is cold...
  idle_min_tokens    "60000"          ...so suggest a fresh session if context is at least this big
"""
import json, re, sys, time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (data_dir, fmt, log, opt, parse_levels, save_config,  # noqa: E402
                     thresholds, _NUMBER)

COMMAND = re.compile(r"^/?token-saver(?::threshold)?(?![\w-])[\s:=]*(.*)$", re.I | re.S)
OFF_WORDS = {"off", "disable", "none", "kapat", "kapalı", "kapali"}
STATUS_WORDS = {"", "status", "durum", "?"}
FILLER = re.compile(r"\b(tokens?|tokende|and|ve|at|or|veya|da|de)\b|[~\s.,;:!?'\"()-]")


def num(name, default):
    try:
        return int(float(opt(name, default)))
    except (ValueError, OverflowError):
        return int(default)


def is_bare_answer(text):
    """True when the text is nothing but threshold numbers: "100k", "150k ve 300k tokens"."""
    low = text.strip().lower()
    if not low or len(low) > 60 or not parse_levels(low):
        return False
    return FILLER.sub("", _NUMBER.sub("", low)) == ""


def emit(ctx, notice=None):
    """ctx goes to Claude; notice (optional) is shown to the user by Claude Code itself."""
    out = {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": ctx}}
    if notice:
        out["systemMessage"] = notice
    print(json.dumps(out))


SETUP_NOTICE = ("Token Saver: no notification threshold set yet. Reply with a number such as 100k "
                "(or two, like 150k,300k) to choose when a fresh session is offered, "
                "or type: token-saver off")


def listing(levels):
    return " and ".join(fmt(lv) for lv in levels) + " tokens"


CHANGE_HINT = ("They can change it any time by typing \"token-saver 200k\", or turn the "
               "notification off with \"token-saver off\".")


def save_levels(levels):
    save_config(levels=levels, off=False)
    log(f"guard: threshold saved {levels}")
    _, source = thresholds()
    note = ("" if source != "settings" else
            " Note for the user: a warn_tokens value in the plugin options or TS_WARN_TOKENS is "
            "set and takes priority over this saved value until it is removed.")
    return (f"[token-saver] Saved: the user will be asked about a fresh session when the context "
            f"passes {listing(levels)}. Tell them so in one short line, in their language. "
            f"{CHANGE_HINT}{note}")


def handle_command(arg):
    """"token-saver <something>" typed by the user. Returns True if it was a command."""
    word = arg.strip().lower()
    if word in STATUS_WORDS:
        levels, source = thresholds()
        state = (f"notifying at {listing(levels)} ({'from settings' if source == 'settings' else 'saved'})"
                 if levels else "turned off" if source == "off" else "not set yet")
        emit(f"[token-saver] The user asked for the Token Saver setting. It is: {state}. "
             f"Tell them in one short line, in their language. {CHANGE_HINT}")
        return True
    if word in OFF_WORDS:
        save_config(levels=[], off=True)
        log("guard: threshold turned off")
        emit("[token-saver] Saved: the context-size notification is now off. Tell the user so in "
             "one short line, in their language. They can turn it back on by typing "
             "\"token-saver 150k\" with the number they want.")
        return True
    if is_bare_answer(arg):
        emit(save_levels(parse_levels(arg)))
        return True
    return False


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
    cmd = COMMAND.match(prompt)
    if cmd and handle_command(cmd.group(1)):
        return
    if prompt.startswith("/") or "handoff" in prompt.lower():
        return

    state = data_dir() / "state"
    state.mkdir(exist_ok=True)
    levels, source = thresholds()
    if source is None:  # the user hasn't chosen a threshold yet
        asked_f = state / f"{sid}.setup"
        if asked_f.exists():
            if is_bare_answer(prompt):
                emit(save_levels(parse_levels(prompt)) + " Their message was only this answer; "
                     "if a request of theirs is still unfinished, carry on with it.")
                return
        else:
            asked_f.write_text("asked")
            log("guard: setup question shown")
            emit("""[token-saver] First-time setup: the user has not chosen when to be notified about
context size. Start your reply with one short question in the user's own language, equivalent to:
"Token Saver: at how many tokens of context should I offer a fresh session? Reply with a number
like 100k, two like 150k,300k, or 'token-saver off'."
This one line comes first even if the user asked for a short or one-line reply. Then carry on
with their request as normal. Don't save anything yourself: the plugin reads the number from
their next message.""", notice=SETUP_NOTICE)
            return

    used, last_ts = read_transcript(data.get("transcript_path", ""))
    if used is None:
        used = from_statusline(sid)
    if used is None:
        log("guard: context size unknown")
        return
    kt = f"~{used/1000:.0f}k tokens"
    log(f"guard: context {kt}")

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
    emit(ctx)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # a hook must never block or break the user's prompt
        log(f"guard: error {exc!r}")
