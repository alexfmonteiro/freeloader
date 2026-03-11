#!/bin/bash
# Claude Code PreToolUse hook — suggests freeloader for WebFetch without hard-blocking.
# Softer alternative to block-webfetch.sh: WebFetch proceeds but Claude sees a token tip.
#
# Add to .claude/settings.local.json:
#   "hooks": {
#     "PreToolUse": [
#       { "matcher": "WebFetch", "hooks": [{ "type": "command", "command": ".claude/hooks/suggest-webfetch.sh" }] }
#     ]
#   }

INPUT=$(cat -)
URL=$(echo "$INPUT" | jq -r '.tool_input.url // empty' 2>/dev/null)

if [ -n "$URL" ]; then
  jq -n --arg url "$URL" '{
    hookSpecificOutput: {
      hookEventName: "PreToolUse",
      permissionDecision: "allow",
      permissionDecisionReason: ("Token tip: curl -s \($url) | freeloader \"<what you need>\" saves tokens vs WebFetch")
    }
  }'
else
  jq -n '{
    hookSpecificOutput: {
      hookEventName: "PreToolUse",
      permissionDecision: "allow"
    }
  }'
fi
