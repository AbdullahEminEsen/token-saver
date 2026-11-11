# Changelog

All notable changes to Token Saver. Versions follow [semantic versioning](https://semver.org).

## [1.1.0] - 2026-11-11

Reliability release: the hooks now have a test suite, and the problems it found are fixed.

### Fixed

- **Handoffs no longer need a "sensitive file" approval.** Claude Code treats `.claude/` as
  sensitive and asks for permission on every write there, even in accept-edits mode; without an
  answer the handoff was never written, and Claude could still reply "Done". Handoffs now go to
  `.token-saver/handoff.md`, and Claude is told to say so if the write fails. A handoff left in
  the old location is still loaded.
- **Status line crash on Windows.** The context bar characters can't be printed in legacy code
  pages; output is now UTF-8.
- **A typo in the thresholds no longer disables the guard.** A `warn_tokens` value such as
  `150k,300k` made the hook crash on every prompt, so no warning was ever shown. Unreadable entries
  are now skipped, and if none are usable the defaults (`150000,300000`) apply.
- **Wrong context size after an error reply.** Synthetic and error replies carry an all-zero usage
  block, which was read as "context is 0 tokens". The guard now looks past them to the last real
  reply.
- **Crashes on unusual transcript data.** Non-object lines, a `message` or `usage` of the wrong
  type, and non-numeric token fields are skipped instead of raising.
- **Crashes on unusual hook input.** Empty, invalid, or non-object JSON on stdin, `null` fields,
  and a corrupt per-session state file are all handled.
- **Handoff files saved with a byte-order mark** (common on Windows) no longer carry a stray
  character into the new session.
- A bad `handoff_max_age_h` value falls back to 24 hours instead of failing session start.

### Changed

- **Thresholds re-arm after `/compact`.** Each threshold used to fire once per session, full stop.
  Now, if the context drops back under a threshold and later grows past it again, you are asked
  again.
- A hook that hits an unexpected error logs it to `hook.log` and exits cleanly. It never blocks
  your prompt, and it no longer runs twice through the `python3 || python` fallback.
- Session ids are sanitized before they are used in a state file name.

### Added

- Test suite (`python -m unittest discover -s tests -t tests`, standard library only) covering
  threshold handling, missing or unusual context data, and the pending request surviving a handoff
  unchanged.
- CI on Linux, Windows, and macOS.
- [Compatibility table](README.md#compatibility), [roadmap](ROADMAP.md), and
  [contributing guide](CONTRIBUTING.md).

## [1.0.0] - 2026-10-30

First release.

- Context guard: asks before your request runs once the context passes 150k and 300k tokens, or
  after a 60-minute break with a large context.
- Handoff skill and loader: writes `.claude/handoff.md` with your pending request verbatim and
  loads it into the next session after `/clear`.
- Test filter: only failures and the last lines of test output reach the context.
- Working rules injected at session start.
- Optional status line with a context bar.

[1.1.0]: https://github.com/AbdullahEminEsen/token-saver/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/AbdullahEminEsen/token-saver/releases/tag/v1.0.0
