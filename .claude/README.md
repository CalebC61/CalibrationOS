# `.claude/` — Claude Code configuration

## gstack skill pack (SessionStart hook)

[`hooks/session-start.sh`](hooks/session-start.sh) installs the
[gstack](https://github.com/garrytan/gstack) skill pack at the start of every
**Claude Code on the web** session and registers its slash commands as
`gstack-*` (e.g. `/gstack-ship`, `/gstack-review`, `/gstack-cso`,
`/gstack-autoplan`). It is wired up in [`settings.json`](settings.json).

Why a hook: web sessions run in an ephemeral container, so user-level skills
under `~/.claude/skills` do not survive between sessions. The hook re-installs
gstack each session. It is idempotent — clone, dependency install, and binary
build are skipped when their outputs already exist — so repeat runs are fast.

The hook only runs in the remote (web) environment. Locally, install gstack
once yourself with its own installer.

### Browser-dependent skills

Skills that drive a real browser (`gstack-qa`, `gstack-scrape`,
`gstack-connect-chrome`, ...) need Playwright's Chromium, downloaded from
`cdn.playwright.dev`. If that host is not in this environment's network egress
allowlist, the browser download is skipped and only the non-browser skills are
available. Add `cdn.playwright.dev` to the allowlist to enable the full set.

### Naming

Skills are registered with the `gstack-` prefix to avoid collisions with
built-in commands like `/review` and `/run`. To switch to short names
(`/ship`, `/review`, ...):

```bash
~/.claude/skills/gstack/bin/gstack-config set skill_prefix false
```
