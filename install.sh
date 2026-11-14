#!/bin/bash
set -e

BOLD=$(tput bold 2>/dev/null || echo "")
RESET=$(tput sgr0 2>/dev/null || echo "")
GREEN=$(tput setaf 2 2>/dev/null || echo "")
YELLOW=$(tput setaf 3 2>/dev/null || echo "")

# Where this script lives (source of truth for freeloader files)
FREELOADER_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# Optional --hooks=<1-5> skips the hook prompt; the remaining argument is the
# target project for hooks/CLAUDE.md (default: current directory)
hook_choice=""
TARGET_DIR=""
for arg in "$@"; do
  case "$arg" in
    --hooks=*) hook_choice="${arg#--hooks=}" ;;
    *) TARGET_DIR="$arg" ;;
  esac
done
TARGET_DIR="${TARGET_DIR:-$(pwd)}"

echo "${BOLD}freeloader installer${RESET}"
echo "--------------------"
[ "$TARGET_DIR" != "$(pwd)" ] && echo "Target project: $TARGET_DIR"

# 1. Install the freeloader script
BIN_DIR="$HOME/.local/bin"
mkdir -p "$BIN_DIR"
cp "$FREELOADER_DIR/freeloader" "$BIN_DIR/freeloader"
chmod +x "$BIN_DIR/freeloader"
echo "${GREEN}✓${RESET} Installed freeloader to $BIN_DIR/freeloader"

# Check PATH
if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
  echo "${YELLOW}⚠${RESET}  $BIN_DIR is not in your PATH. Add this to your shell profile:"
  echo "   export PATH=\"\$HOME/.local/bin:\$PATH\""
fi

# 2. Install config (skip if already exists)
CONFIG_DIR="$HOME/.config/freeloader"
CONFIG_FILE="$CONFIG_DIR/config.json"
mkdir -p "$CONFIG_DIR"
if [ -f "$CONFIG_FILE" ]; then
  echo "${YELLOW}⚠${RESET}  Config already exists at $CONFIG_FILE — skipping. Edit it manually to add/update API keys."
else
  cp "$FREELOADER_DIR/config.template.json" "$CONFIG_FILE"
  echo "${GREEN}✓${RESET} Created config at $CONFIG_FILE"
  echo "   ${BOLD}Add your API keys.${RESET} See the Installation and Providers sections in"
  echo "   $FREELOADER_DIR/README.md for where to get them and the free tiers."
fi

# 3. Install Claude Code skill
SKILL_DIR="$HOME/.claude/skills/freeloader"
mkdir -p "$SKILL_DIR"
cp "$FREELOADER_DIR/skills/freeloader/SKILL.md" "$SKILL_DIR/SKILL.md"
echo "${GREEN}✓${RESET} Installed Claude Code skill to $SKILL_DIR"

# 4. Hook selection
echo ""
echo "${BOLD}Claude Code hooks (optional):${RESET}"
echo "  1) block-webfetch   — hard-blocks WebFetch, forces freeloader (strongest)"
echo "  2) suggest-webfetch — lets WebFetch run but hints freeloader (softer)"
echo "  3) intercept-read   — blocks Read on files >10KB, forces freeloader (recommended)"
echo "  4) block-webfetch + intercept-read"
echo "  5) none"
echo ""
if [ -z "$hook_choice" ]; then
  # No terminal (piped, CI, agents): read hits EOF, so fall back to "none"
  read -r -p "Install hooks for current project? [1-5, default=5] " hook_choice || hook_choice=5
fi

install_hook() {
  local src="$1"
  local dst="$TARGET_DIR/.claude/hooks/$(basename "$src")"
  mkdir -p "$TARGET_DIR/.claude/hooks"
  cp "$FREELOADER_DIR/hooks/$src" "$dst"
  chmod +x "$dst"
  echo "${GREEN}✓${RESET} Installed $dst"
}

case "$hook_choice" in
  1)
    install_hook "block-webfetch.sh"
    SHOW_SETTINGS=1
    WEBFETCH_HOOK="$TARGET_DIR/.claude/hooks/block-webfetch.sh"
    ;;
  2)
    install_hook "suggest-webfetch.sh"
    SHOW_SETTINGS=1
    WEBFETCH_HOOK="$TARGET_DIR/.claude/hooks/suggest-webfetch.sh"
    ;;
  3)
    install_hook "intercept-read.sh"
    SHOW_SETTINGS=1
    READ_HOOK="$TARGET_DIR/.claude/hooks/intercept-read.sh"
    ;;
  4)
    install_hook "block-webfetch.sh"
    install_hook "intercept-read.sh"
    SHOW_SETTINGS=1
    WEBFETCH_HOOK="$TARGET_DIR/.claude/hooks/block-webfetch.sh"
    READ_HOOK="$TARGET_DIR/.claude/hooks/intercept-read.sh"
    ;;
  *)
    echo "   Skipping hooks."
    ;;
esac

if [ -n "$SHOW_SETTINGS" ]; then
  echo ""
  echo "   Add the following to your .claude/settings.local.json:"
  echo ""
  echo '   "hooks": {'
  echo '     "PreToolUse": ['
  if [ -n "$WEBFETCH_HOOK" ]; then
    # Comma only when another entry follows, so the snippet stays valid JSON
    sep=""
    [ -n "$READ_HOOK" ] && sep=","
    echo "       { \"matcher\": \"WebFetch\", \"hooks\": [{ \"type\": \"command\", \"command\": \"$WEBFETCH_HOOK\" }] }$sep"
  fi
  if [ -n "$READ_HOOK" ]; then
    echo "       { \"matcher\": \"Read\", \"hooks\": [{ \"type\": \"command\", \"command\": \"$READ_HOOK\" }] }"
  fi
  echo '     ]'
  echo '   }'
fi

# 5. Remind about CLAUDE.md
echo ""
echo "${BOLD}Last step:${RESET} add the Token Savings Rule to your project's CLAUDE.md:"
echo "   cat $FREELOADER_DIR/CLAUDE.md.snippet >> $TARGET_DIR/CLAUDE.md"
echo ""
echo "${GREEN}Done!${RESET} Test it: echo 'hello world' | freeloader 'repeat back what I said'"
echo ""
echo "Other commands:"
echo "   freeloader --list-providers   check API key status"
echo "   freeloader --stats            show cumulative token savings"
echo "   freeloader --discover         find missed savings in session history"
