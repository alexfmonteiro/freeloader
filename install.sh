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

# 4. Optional: install WebFetch hook
echo ""
read -p "Install WebFetch hook for current project? (blocks WebFetch, redirects to freeloader) [y/N] " install_hook
if [[ "$install_hook" =~ ^[Yy]$ ]]; then
  mkdir -p ".claude/hooks"
  cp hooks/block-webfetch.sh .claude/hooks/block-webfetch.sh
  chmod +x .claude/hooks/block-webfetch.sh
  echo "${GREEN}✓${RESET} Installed hook to .claude/hooks/block-webfetch.sh"
  echo "   Add this to your .claude/settings.local.json:"
  cat << 'EOF'
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "WebFetch",
        "hooks": [{ "type": "command", "command": ".claude/hooks/block-webfetch.sh" }]
      }
    ]
  }
EOF
fi

# 5. Remind about CLAUDE.md
echo ""
echo "${BOLD}Last step:${RESET} add the Token Savings Rule to your project's CLAUDE.md:"
echo "   cat CLAUDE.md.snippet >> /path/to/your/project/CLAUDE.md"
echo ""
echo "${GREEN}Done!${RESET} Test it: echo 'hello world' | freeloader 'repeat back what I said'"
