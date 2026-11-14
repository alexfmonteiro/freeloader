#!/bin/bash
# Claude Code PreToolUse hook — suggests freeloader for WebFetch without hard-blocking.
# Softer alternative to block-webfetch.sh: WebFetch goes through the normal permission flow and
# Claude sees a token tip via additionalContext.
#
# Add to .claude/settings.local.json:
#   "hooks": {
#     "PreToolUse": [
#       { "matcher": "WebFetch", "hooks": [{ "type": "command", "command": ".claude/hooks/suggest-webfetch.sh" }] }
#     ]
#   }

# Kill switch: touch ~/.config/freeloader/disabled to bypass all hooks
# No output means no decision, so the normal permission flow still applies.
if [ -f "$HOME/.config/freeloader/disabled" ]; then
  exit 0
fi

INPUT=$(cat -)
URL=$(echo "$INPUT" | jq -r '.tool_input.url // empty' 2>/dev/null)

# No permissionDecision: WebFetch keeps its normal permission prompt.
# additionalContext goes to Claude; permissionDecisionReason would go to the user.
if [ -n "$URL" ]; then
  jq -n --arg url "$URL" '{
    hookSpecificOutput: {
      hookEventName: "PreToolUse",
      additionalContext: ("Token tip: curl -s \($url) | freeloader \"<what you need>\" saves tokens vs WebFetch")
    }
  }'
fi
