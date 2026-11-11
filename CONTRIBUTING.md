# Contributing

Bug reports, compatibility reports, and pull requests are all welcome.

## Run the tests

There is nothing to install: the hooks and the tests use only the Python standard library
(3.10 or newer).

```bash
python -m unittest discover -s tests -t tests
```

The test-filter execution tests need `bash` and are skipped without it. CI runs the suite on Linux,
Windows, and macOS for every pull request.

## How the tests work

Each test runs a hook the way Claude Code does: as a subprocess that gets JSON on stdin, with its
own temporary data and project folders. `tests/helpers.py` has the helpers, including `assistant()`
for building transcript entries of a given size.

| File | Covers |
|---|---|
| `tests/test_context_guard.py` | Choosing a threshold, the `token-saver` commands, thresholds, idle breaks, missing or unusual transcript data, status line fallback |
| `tests/test_handoff.py` | The pending request reaching the new session unchanged, one-time use, stale handoffs, working rules |
| `tests/test_test_filter.py` | Which commands are rewritten, and that exit code and failures survive |
| `tests/test_statusline_and_manifests.py` | Status line output, and that README, manifests, and code agree |

## Try a hook by hand

```bash
echo '{"session_id":"demo","prompt":"hi","transcript_path":"/path/to/session.jsonl"}' | TS_WARN_TOKENS=100k python hooks/context_guard.py
```

Set `CLAUDE_PLUGIN_DATA` to a scratch folder first if you don't want to touch your real state.

## Pull requests

- Add a test for the behavior you change. A bug fix should come with a test that fails without it.
- Keep the hooks dependency-free and fast: they run on every prompt with a 10-second limit.
- A hook must never block the user. On bad input, do nothing and exit 0.
- Add a line to `CHANGELOG.md` under an "Unreleased" heading.

## Compatibility reports

If you run Token Saver on a setup that the [compatibility table](README.md#compatibility) doesn't
list, open an issue with your OS, Claude Code version (`claude --version`), where you run it
(terminal, desktop app, IDE extension), and whether the question appeared at the threshold.
