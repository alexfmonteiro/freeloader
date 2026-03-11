#!/bin/bash
# Claude Code PreToolUse hook — blocks WebFetch and redirects to freeloader.
# Add to .claude/settings.local.json:
#
#   "hooks": {
#     "PreToolUse": [
#       { "matcher": "WebFetch", "hooks": [{ "type": "command", "command": ".claude/hooks/block-webfetch.sh" }] }
#     ]
#   }

jq -n '{
  hookSpecificOutput: {
    hookEventName: "PreToolUse",
    permissionDecision: "deny",
    permissionDecisionReason: "WebFetch blocked. Use freeloader instead: curl -s <url> | freeloader \"<instructions>\""
  }
}'
