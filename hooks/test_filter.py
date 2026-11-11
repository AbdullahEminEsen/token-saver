#!/usr/bin/env python3
"""
PreToolUse (Bash) hook — test output filter (extends the example in the Claude Code cost docs).

When Claude runs a test command, only failure lines plus the last few lines of output enter the
context instead of thousands of passing-test lines. The exit code is preserved and the full output
is kept in a temp file.

Covers: php artisan test, vendor/bin/phpunit, vendor/bin/pest, npm/pnpm/yarn test, pytest, go test,
cargo test. Disable with plugin option test_filter=false (or TS_TEST_FILTER=0).
"""
import json, re, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import log, opt  # noqa: E402

PATTERN = re.compile(
    r"^(php artisan test|(\./)?vendor/bin/(phpunit|pest)|npm test|npm run test|pnpm test|yarn test"
    r"|pytest|python3? -m pytest|go test|cargo test)"
    r"( [^;&|<>`$\\\n]*)?$"
)


def main():
    if opt("test_filter", "true").lower() in ("0", "false", "no"):
        print("{}")
        return
    try:
        data = json.load(sys.stdin)
    except Exception:
        print("{}")
        return
    ti = data.get("tool_input") if isinstance(data, dict) else None
    if not isinstance(ti, dict):
        print("{}")
        return
    cmd = str(ti.get("command") or "").strip()
    if not PATTERN.match(cmd):
        print("{}")
        return
    filtered = (
        f"__ts_out=$(mktemp); {cmd} > \"$__ts_out\" 2>&1; __ts_rc=$?; "
        f"grep -n -A 6 -E '(FAIL|FAILED|ERROR|Error:|error:|Exception|✗|⨯|panic:)' \"$__ts_out\" | head -120; "
        f"echo '--- tail ---'; tail -n 5 \"$__ts_out\"; "
        f"echo \"[token-saver: full output $(wc -l < \"$__ts_out\") lines in $__ts_out]\"; "
        f"exit $__ts_rc"
    )
    log(f"test-filter: {cmd[:60]}")
    new_input = dict(ti, command=filtered)
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "updatedInput": new_input}}))


if __name__ == "__main__":
    main()
