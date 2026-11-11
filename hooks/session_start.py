#!/usr/bin/env python3
"""
SessionStart hook (startup | clear | compact).

1. Injects a short set of token-saving working rules (plugins can't ship a CLAUDE.md).
   Skipped when TS_INJECT_RULES=0 or the plugin option inject_rules is false.
2. On startup/clear: if .token-saver/handoff.md exists in the project and is recent, loads it
   into the new session and renames it to handoff.done.md so it is used only once.
   (.claude/handoff.md, where v1.0 wrote it, is still read. New handoffs go to .token-saver/
   because Claude Code treats .claude/ as sensitive and asks for permission on every write.)
"""
import json, os, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import log, opt  # noqa: E402

RULES = """[token-saver] Working rules for this session (to keep token usage low):
- Keep replies short: state what you did in 1-3 sentences; don't recap your steps or re-paste code unless asked.
- Don't re-read a file you already read this session unless it changed. In large files read only the relevant range.
- Explore narrowly: locate with Grep/Glob first, then open only what you need. No whole-repo sweeps.
- Hand verbose work (broad code search, log analysis, reading docs) to a subagent and bring back only the result.
- For test/log output, look at failures and the tail, not the full dump.
- When the user switches to an unrelated task and the context is large, suggest a fresh session (handoff skill).
- If you are compacting: keep the user's goal, the pending request verbatim, changed files and why, decisions, and the next step; drop tool output and resolved debugging."""


HANDOFF_DIRS = (".token-saver", ".claude")  # current location first, then the v1.0 one


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        data = {}
    if not isinstance(data, dict):
        data = {}
    source = data.get("source") or ""
    parts = []

    if opt("inject_rules", "true").lower() not in ("0", "false", "no"):
        parts.append(RULES)

    root = Path(os.environ.get("CLAUDE_PROJECT_DIR") or data.get("cwd") or ".")
    candidates = [root / d / "handoff.md" for d in HANDOFF_DIRS]
    f = next((c for c in candidates if c.is_file()), candidates[0])
    has = f.is_file()
    log(f"session-start: {source} ({root}) handoff={'yes' if has else 'no'}")
    try:
        max_age_h = float(opt("handoff_max_age_h", "24"))
    except ValueError:
        max_age_h = 24.0
    if source in ("startup", "clear", "") and has and time.time() - f.stat().st_mtime <= max_age_h * 3600:
        body = f.read_text(encoding="utf-8-sig", errors="replace").strip()
        if body:
            try:
                f.replace(f.with_name("handoff.done.md"))
            except Exception:
                pass
            parts.append(f"""[token-saver] Handoff from the previous session (the user deliberately moved to a
fresh session to save tokens). Don't re-explore the files listed below; read only what the next
step needs. If the user's first message is "continue", "devam", "yes", "go" or similar, carry out
the "Pending request" directly without asking for confirmation again.

{body}""")

    if parts:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart",
                                                 "additionalContext": "\n\n".join(parts)}}))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # never break session start
        log(f"session-start: error {exc!r}")
