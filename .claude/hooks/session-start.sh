#!/usr/bin/env bash
# SessionStart hook: install the gstack skill pack for Claude Code on the web.
#
# gstack (https://github.com/garrytan/gstack) is a pack of slash-command skills
# (planning, review, ship, QA, security, design, ...). On the web, Claude Code
# runs in an ephemeral container, so user-level skills under ~/.claude/skills do
# not survive between sessions. This hook re-installs gstack and re-registers its
# skills at the start of each remote session.
#
# It is idempotent and safe to re-run: the expensive steps (clone, dependency
# install, binary build) are skipped when their outputs already exist, so repeat
# invocations within a cached container are fast.
#
# Browser-dependent skills (gstack-qa, gstack-scrape, gstack-connect-chrome, ...)
# additionally need Playwright's Chromium, which is downloaded from
# cdn.playwright.dev. If that host is not in the environment's network egress
# allowlist the browser download is skipped and only the non-browser skills are
# available. Add cdn.playwright.dev to the allowlist to enable the full set.

set -uo pipefail

# Only run inside Claude Code on the web (the ephemeral remote environment).
# Locally, install gstack yourself once with its own ./setup.
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

GSTACK_REPO="https://github.com/garrytan/gstack.git"
GSTACK_DIR="$HOME/.claude/skills/gstack"
LOG="$(mktemp)"

log() { echo "[gstack-setup] $*"; }

# 1. Clone gstack if it is not already present (idempotent).
if [ ! -e "$GSTACK_DIR/setup" ]; then
  rm -rf "$GSTACK_DIR"
  if ! git clone --single-branch --depth 1 "$GSTACK_REPO" "$GSTACK_DIR" >>"$LOG" 2>&1; then
    log "clone failed; gstack skills unavailable this session (check network egress policy for github.com)"
    exit 0
  fi
fi

cd "$GSTACK_DIR" || exit 0

if ! command -v bun >/dev/null 2>&1; then
  log "bun not found on PATH; cannot build gstack. Skills not registered."
  exit 0
fi

# 2. Install JS dependencies (npm registry is reachable). Skip Playwright's
#    browser download here; it is gated behind cdn.playwright.dev (step 4).
export PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1
export PUPPETEER_SKIP_DOWNLOAD=1
if [ ! -d node_modules ]; then
  bun install --frozen-lockfile >>"$LOG" 2>&1 \
    || bun install >>"$LOG" 2>&1 \
    || log "bun install reported issues (some skills may be limited)"
fi

# 3. Build the browse/design/pdf binaries. Building needs no Chromium.
if [ ! -x browse/dist/browse ]; then
  bun run build >>"$LOG" 2>&1 || log "binary build reported issues (browser/pdf skills may be limited)"
fi

# 4. Best-effort: fetch Playwright's Chromium so browser skills work too.
#    Non-fatal if the egress policy blocks cdn.playwright.dev.
if ! bun --eval 'import { chromium } from "playwright"; const b = await chromium.launch(); await b.close();' >/dev/null 2>&1; then
  if bunx playwright install chromium >>"$LOG" 2>&1; then
    log "Chromium installed; browser skills enabled"
  else
    log "Chromium unavailable (add cdn.playwright.dev to egress allowlist to enable browser skills)"
  fi
fi

# 5. Register every gstack skill as a gstack-* slash command. No Chromium needed.
#    Prefixed names avoid collisions with the harness's built-in skills
#    (/review, /run, ...). To use short names instead, run:
#        ~/.claude/skills/gstack/bin/gstack-config set skill_prefix false
bin/gstack-config set skill_prefix true >/dev/null 2>&1 || true
RELINK_OUT="$(bin/gstack-relink 2>>"$LOG" || true)"

log "${RELINK_OUT:-skills relinked}"
exit 0
