# Token Saver — a Claude Code plugin

Cuts Claude Code token usage automatically. Every message re-sends the whole conversation, so a
600k-token session pays for 600k tokens on every one-line question. Token Saver notices this and
offers to move to a fresh session without losing your place.

## Install

In Claude Code (terminal):

```
/plugin marketplace add AbdullahEminEsen/token-saver
/plugin install token-saver@token-saver
```

In the **Claude desktop app (Code tab)**, which has no `/plugin` screen, add this to
`~/.claude/settings.json` and restart the app:

```json
{
  "extraKnownMarketplaces": {
    "token-saver": { "source": { "source": "github", "repo": "AbdullahEminEsen/token-saver" } }
  },
  "enabledPlugins": { "token-saver@token-saver": true }
}
```

Requires Python 3 on your `PATH` (`python3` or `python`).

## What it does

| Part | Hook | Effect |
|---|---|---|
| Context guard | `UserPromptSubmit` | When context passes **150k** and **300k** tokens, Claude asks *before* starting your request: "Context is at ~152k tokens. Continue this in a fresh session?" Also asks after a 60+ min break (cold prompt cache). Once per threshold. |
| Handoff skill | — | On "yes", writes `.claude/handoff.md` with your goal, changes, decisions, next steps and your **pending request verbatim**. |
| Handoff loader | `SessionStart` | After `/clear`, loads the handoff into the new session. Say "continue" and the pending request runs. Used once. |
| Working rules | `SessionStart` | ~250 tokens of rules: short replies, no re-reading files, narrow exploration, subagents for verbose work, what to keep when compacting. |
| Test filter | `PreToolUse` (Bash) | `php artisan test`, phpunit, pest, npm/pnpm/yarn test, pytest, go test, cargo test: only failures + last lines reach the context. Exit code kept. |

```
… context hits 150k → Claude: "Context is at ~152k tokens. Continue in a fresh session?"
you: yes      → .claude/handoff.md written
you: /clear   → fresh session, handoff auto-loaded
you: continue → pending request runs
```

Thresholds are absolute tokens, not percentages: cost depends on how many tokens are in the
context, not on the window size. It also works where the status line doesn't run (desktop app).

## Settings

Change them in `/config` (plugin options), or with env vars in `settings.json` → `"env"`:

| Option | Env var | Default |
|---|---|---|
| Warning thresholds | `TS_WARN_TOKENS` | `150000,300000` |
| Idle break (min) | `TS_IDLE_MINUTES` | `60` |
| Filter test output | `TS_TEST_FILTER` | `true` |
| Working rules | `TS_INJECT_RULES` | `true` |

## Check it's working

Each hook writes a line to `~/.claude/plugins/data/token-saver-token-saver/hook.log`
(`/hooks` also lists them in the terminal).

## Optional: status line (terminal only)

Plugins can't set the status line. To see a context bar, add to `~/.claude/settings.json`:

```json
"statusLine": { "type": "command", "command": "python3 /path/to/token-saver/hooks/statusline.py" }
```

## Notes

- Claude can't run `/clear` itself, so that one keystroke is yours.
- Add `.claude/handoff*.md` to `.gitignore` (the handoff skill does this for you).

---

## Türkçe

Bağlam 150k ve 300k tokeni geçtiğinde Claude, isteğine başlamadan önce "temiz oturumda devam edeyim
mi?" diye sorar. "Evet" dersen bekleyen isteğin de dahil bir handoff dosyası yazar. `/clear` yazıp
"devam" dediğinde kaldığın yerden sürer. Test çıktısını da yalnızca hatalara indirir. Kurulum
yukarıda; Desktop uygulamasında `settings.json` yöntemini kullan.

MIT License.
