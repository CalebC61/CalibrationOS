#!/usr/bin/env bash
# SessionStart hook: install a curated subset of ComposioHQ/awesome-claude-skills.
#
# That repo (https://github.com/ComposioHQ/awesome-claude-skills) is a catalog of
# 800+ skills, most of which are Composio app-connectors that each need a Composio
# API key. This hook installs only the ~28 general-purpose, key-free skills
# (document handling, content/writing, file/org, dev tooling, media, etc.) and
# registers them as acs-* slash commands. The 832 Composio connectors are
# intentionally NOT installed.
#
# Web sessions run in an ephemeral container, so user-level skills under
# ~/.claude/skills do not survive between sessions; this hook re-installs them
# each remote session. It is idempotent: a skill already present is left as-is.
#
# Runtime notes (registration always works; these only matter when a skill runs):
#   - acs-webapp-testing uses Playwright Chromium (cdn.playwright.dev — blocked by
#     this environment's egress policy unless allowlisted).
#   - acs-video-downloader / acs-slack-gif-creator / acs-image-enhancer / acs-canvas-design
#     need yt-dlp / ffmpeg / Pillow etc., installed on demand by the skill itself.

set -uo pipefail

# Only run inside Claude Code on the web (the ephemeral remote environment).
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

REPO="https://github.com/ComposioHQ/awesome-claude-skills.git"
SRC="$HOME/.cache/awesome-claude-skills"   # cache OUTSIDE ~/.claude/skills
SKILLS_DIR="$HOME/.claude/skills"
PREFIX="acs"

# Curated, key-free skills as "<source-subpath>:<slug>". Excludes the Composio
# connectors (connect, connect-apps, skill-share) and the empty template-skill.
SKILLS=(
  "artifacts-builder:artifacts-builder"
  "brand-guidelines:brand-guidelines"
  "canvas-design:canvas-design"
  "changelog-generator:changelog-generator"
  "competitive-ads-extractor:competitive-ads-extractor"
  "content-research-writer:content-research-writer"
  "developer-growth-analysis:developer-growth-analysis"
  "domain-name-brainstormer:domain-name-brainstormer"
  "file-organizer:file-organizer"
  "image-enhancer:image-enhancer"
  "internal-comms:internal-comms"
  "invoice-organizer:invoice-organizer"
  "langsmith-fetch:langsmith-fetch"
  "lead-research-assistant:lead-research-assistant"
  "mcp-builder:mcp-builder"
  "meeting-insights-analyzer:meeting-insights-analyzer"
  "raffle-winner-picker:raffle-winner-picker"
  "skill-creator:skill-creator"
  "slack-gif-creator:slack-gif-creator"
  "tailored-resume-generator:tailored-resume-generator"
  "theme-factory:theme-factory"
  "twitter-algorithm-optimizer:twitter-algorithm-optimizer"
  "video-downloader:video-downloader"
  "webapp-testing:webapp-testing"
  "document-skills/docx:docx"
  "document-skills/pdf:pdf"
  "document-skills/pptx:pptx"
  "document-skills/xlsx:xlsx"
)

# Directories to materialize from the source repo (sparse checkout).
SPARSE_DIRS="artifacts-builder brand-guidelines canvas-design changelog-generator competitive-ads-extractor content-research-writer developer-growth-analysis domain-name-brainstormer file-organizer image-enhancer internal-comms invoice-organizer langsmith-fetch lead-research-assistant mcp-builder meeting-insights-analyzer raffle-winner-picker skill-creator slack-gif-creator tailored-resume-generator theme-factory twitter-algorithm-optimizer video-downloader webapp-testing document-skills"

log() { echo "[awesome-skills] $*"; }

# 1. Fetch source — sparse checkout so the 832 Composio connectors are not pulled.
if [ ! -d "$SRC/document-skills" ]; then
  rm -rf "$SRC"
  if git clone --no-checkout --depth 1 --filter=blob:none "$REPO" "$SRC" >/dev/null 2>&1; then
    (
      cd "$SRC" || exit 0
      git sparse-checkout init --cone >/dev/null 2>&1
      git sparse-checkout set $SPARSE_DIRS >/dev/null 2>&1
      git checkout >/dev/null 2>&1
    )
  fi
  # Fallback: plain shallow clone if partial/sparse checkout is unavailable.
  if [ ! -d "$SRC/document-skills" ]; then
    rm -rf "$SRC"
    git clone --depth 1 "$REPO" "$SRC" >/dev/null 2>&1 \
      || { log "clone failed; skills not installed (check egress allowlist for github.com)"; exit 0; }
  fi
fi

# 2. Copy each curated skill into ~/.claude/skills/acs-<slug>/ and patch its
#    name: field to match (skills are addressed by the frontmatter name).
count=0
for entry in "${SKILLS[@]}"; do
  sub="${entry%%:*}"
  slug="${entry##*:}"
  src="$SRC/$sub"
  dst="$SKILLS_DIR/${PREFIX}-${slug}"
  [ -f "$src/SKILL.md" ] || continue
  if [ ! -f "$dst/SKILL.md" ]; then
    rm -rf "$dst"
    mkdir -p "$dst"
    cp -R "$src/." "$dst/" 2>/dev/null || true
    if [ -f "$dst/SKILL.md" ]; then
      tmp="$(mktemp)"
      sed "1,/^---[[:space:]]*$/s|^name:.*|name: ${PREFIX}-${slug}|" "$dst/SKILL.md" > "$tmp" \
        && mv "$tmp" "$dst/SKILL.md"
    fi
  fi
  [ -f "$dst/SKILL.md" ] && count=$((count + 1))
done

log "registered $count curated skills as ${PREFIX}-* (Composio connectors intentionally skipped)"
exit 0
