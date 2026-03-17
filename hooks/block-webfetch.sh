#!/bin/bash
# Claude Code PreToolUse hook — blocks WebFetch and redirects to freeloader.
# Add to .claude/settings.local.json:
#
#   "hooks": {
#     "PreToolUse": [
#       { "matcher": "WebFetch", "hooks": [{ "type": "command", "command": ".claude/hooks/block-webfetch.sh" }] }
#     ]
#   }

# Kill switch: touch ~/.config/freeloader/disabled to bypass all hooks
if [ -f "$HOME/.config/freeloader/disabled" ]; then
  jq -n '{ hookSpecificOutput: { hookEventName: "PreToolUse", permissionDecision: "allow" } }'
  exit 0
fi

jq -n '{
  hookSpecificOutput: {
    hookEventName: "PreToolUse",
    permissionDecision: "deny",
    permissionDecisionReason: "WebFetch blocked. Use freeloader instead: curl -s <url> | freeloader \"<instructions>\""
  }
}'
