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

## awesome-claude-skills (curated set)

[`hooks/install-awesome-skills.sh`](hooks/install-awesome-skills.sh) installs a
curated subset of [ComposioHQ/awesome-claude-skills](https://github.com/ComposioHQ/awesome-claude-skills)
and registers them as `acs-*` slash commands (e.g. `/acs-pdf`, `/acs-docx`,
`/acs-content-research-writer`, `/acs-skill-creator`). It is wired up in
[`settings.json`](settings.json) alongside the gstack hook.

That upstream repo is a catalog of 800+ skills, but most are **Composio
app-connectors** that each need a Composio API key. This hook installs only the
**~28 general-purpose, key-free skills** (document handling, content/writing,
file & invoice organizing, dev tooling like `mcp-builder`/`skill-creator`, media,
etc.). The 832 Composio connectors are intentionally **not** installed, to keep
the skill namespace clean and avoid skills that can't run without API setup.

Source is sparse-checked-out into `~/.cache/awesome-claude-skills` (outside the
skills dir) so the Composio connectors are never even downloaded. Each curated
skill is copied to `~/.claude/skills/acs-<name>/` with its `name:` field patched
to match. The hook is remote-only and idempotent (a skill already present is left
as-is).

### Runtime notes
Registration always succeeds; these only matter when a skill actually runs:
- `acs-webapp-testing` uses Playwright Chromium (`cdn.playwright.dev`, blocked by
  this environment's egress policy unless allowlisted — same as gstack's browser
  skills).
- `acs-video-downloader`, `acs-slack-gif-creator`, `acs-image-enhancer`, and
  `acs-canvas-design` need tools like `yt-dlp` / `ffmpeg` / Pillow, installed on
  demand by the skill.
