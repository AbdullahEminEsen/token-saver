---
name: handoff
description: Writes .claude/handoff.md so work can continue in a fresh, cheap session. Use when the user says "handoff", "continue in a new session", "context is full", or answers yes to a token-saver prompt.
---

# Handoff

Goal: the next session continues from where this one stopped, with the fewest tokens and no re-exploration.

## Steps

1. Write `.claude/handoff.md` in the project root using the template below. Keep it under 60 lines.
   Don't paste code; give file path + line range + what changed.
2. If the project has a `.gitignore` and it lacks `.claude/handoff*.md`, add that line.
3. Tell the user only this, in their language: **"Done. Type /clear, then say 'continue'."**
   No summary or list in the reply; it's all in the file.

## Template

```markdown
# Handoff — <short title> (<date time>)

## Goal
<the user's real goal, 1-3 sentences>

## Pending request
<the user's last request not yet carried out, VERBATIM in their words. "none" if there isn't one>

## Done so far
- <file:lines> — <what changed, why>

## Decisions and constraints
- <decisions made, things the user said not to do, versions in use>

## Open issues / next steps
1. <first concrete step>

## Relevant files (read only if needed)
- path/to/file — <why it matters>

## Verification
- <command/test to run and expected result>
```
