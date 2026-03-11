#!/bin/bash
set -e

BOLD=$(tput bold 2>/dev/null || echo "")
RESET=$(tput sgr0 2>/dev/null || echo "")
GREEN=$(tput setaf 2 2>/dev/null || echo "")
YELLOW=$(tput setaf 3 2>/dev/null || echo "")

echo "${BOLD}freeloader installer${RESET}"
echo "--------------------"

# 1. Install the freeloader script
BIN_DIR="$HOME/.local/bin"
mkdir -p "$BIN_DIR"
cp freeloader "$BIN_DIR/freeloader"
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
  cp config.template.json "$CONFIG_FILE"
  echo "${GREEN}✓${RESET} Created config at $CONFIG_FILE"
  echo "   ${BOLD}Add your API keys:${RESET}"
  echo "   - Gemini: https://aistudio.google.com  (free, 1500 req/day)"
  echo "   - Groq:   https://console.groq.com     (free, 14.4K req/day)"
fi

# 3. Install Claude Code skill
SKILL_DIR="$HOME/.claude/skills/freeloader"
mkdir -p "$SKILL_DIR"
cp skill/SKILL.md "$SKILL_DIR/SKILL.md"
echo "${GREEN}✓${RESET} Installed Claude Code skill to $SKILL_DIR"

# 4. Hook selection
echo ""
echo "${BOLD}Claude Code hooks (optional):${RESET}"
echo "  1) block-webfetch   — hard-blocks WebFetch, forces freeloader (strongest)"
echo "  2) suggest-webfetch — allows WebFetch but hints freeloader (softer)"
echo "  3) intercept-read   — blocks Read on files >10KB, forces freeloader (recommended)"
echo "  4) all of the above"
echo "  5) none"
echo ""
read -p "Install hooks for current project? [1-5, default=5] " hook_choice

install_hook() {
  local src="$1"
  local dst=".claude/hooks/$(basename "$src")"
  mkdir -p ".claude/hooks"
  cp "hooks/$src" "$dst"
  chmod +x "$dst"
  echo "${GREEN}✓${RESET} Installed $dst"
}

case "$hook_choice" in
  1)
    install_hook "block-webfetch.sh"
    SHOW_SETTINGS=1
    WEBFETCH_HOOK=".claude/hooks/block-webfetch.sh"
    ;;
  2)
    install_hook "suggest-webfetch.sh"
    SHOW_SETTINGS=1
    WEBFETCH_HOOK=".claude/hooks/suggest-webfetch.sh"
    ;;
  3)
    install_hook "intercept-read.sh"
    SHOW_SETTINGS=1
    READ_HOOK=".claude/hooks/intercept-read.sh"
    ;;
  4)
    install_hook "block-webfetch.sh"
    install_hook "intercept-read.sh"
    SHOW_SETTINGS=1
    WEBFETCH_HOOK=".claude/hooks/block-webfetch.sh"
    READ_HOOK=".claude/hooks/intercept-read.sh"
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
    echo "       { \"matcher\": \"WebFetch\", \"hooks\": [{ \"type\": \"command\", \"command\": \"$WEBFETCH_HOOK\" }] },"
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
echo "   cat CLAUDE.md.snippet >> /path/to/your/project/CLAUDE.md"
echo ""
echo "${GREEN}Done!${RESET} Test it: echo 'hello world' | freeloader 'repeat back what I said'"
echo ""
echo "Other commands:"
echo "   freeloader --list-providers   check API key status"
echo "   freeloader --stats            show cumulative token savings"
echo "   freeloader --discover         find missed savings in session history"
