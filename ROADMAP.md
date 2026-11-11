# Roadmap

What's planned for Token Saver, roughly in order. Nothing here is a promise or a date. If you want
something moved up, or have an idea that isn't listed, open an issue.

## Now

- **Verify more setups.** The [compatibility table](README.md#compatibility) only lists what has
  actually been run. Wanted: reports from macOS and Linux terminals, and from the VS Code and
  JetBrains extensions.
- **Recorded demo.** A short terminal recording of the real ask → handoff → `/clear` → continue flow.

## Next

- **Savings report.** A `/token-saver:stats` command that reads `hook.log` and shows how often the
  guard fired, how large the context was each time, and how many test-output lines were filtered.
- **More test runners.** `vitest`, `jest`, `bun test`, `deno test`, `dotnet test`, `mvn test`,
  `gradle test`, `rspec`, `make test`.
- **Windows without Git Bash.** The test filter rewrites the command with POSIX shell syntax, so it
  needs the Bash tool. Skip it cleanly when the command is headed for PowerShell.
- **Per-project settings.** Thresholds in a project file, so a large monorepo and a small script
  can have different limits.

## Later

- **Cost in the question.** Show an estimated price per message next to the token count, based on
  the model in use.
- **Handoff history.** Keep the last few handoffs instead of only `handoff.done.md`.
- **Smarter idle check.** Use the real cache lifetime of the session (5 minutes or 1 hour) instead
  of one fixed idle setting.

## Not planned

- Running `/clear` automatically. Claude Code doesn't let a plugin do it, and starting a fresh
  session should stay your decision.
- Rewriting or summarizing your prompts. Token Saver only changes what it tells you about.
- Telemetry of any kind. The only log is the local `hook.log`.
