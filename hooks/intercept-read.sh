#!/bin/bash
# Claude Code PreToolUse hook — blocks Read on large files and redirects to freeloader.
# Files below the threshold pass through normally.
#
# Configure threshold (default 10KB):
#   export FREELOADER_MIN_SIZE_KB=20
#
# Add to .claude/settings.local.json:
#   "hooks": {
#     "PreToolUse": [
#       { "matcher": "Read", "hooks": [{ "type": "command", "command": ".claude/hooks/intercept-read.sh" }] }
#     ]
#   }

MIN_SIZE_KB=${FREELOADER_MIN_SIZE_KB:-10}
MIN_SIZE_BYTES=$((MIN_SIZE_KB * 1024))

# Kill switch: touch ~/.config/freeloader/disabled to bypass all hooks
if [ -f "$HOME/.config/freeloader/disabled" ]; then
  jq -n '{ hookSpecificOutput: { hookEventName: "PreToolUse", permissionDecision: "allow" } }'
  exit 0
fi

INPUT=$(cat -)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null)

allow() {
  jq -n '{ hookSpecificOutput: { hookEventName: "PreToolUse", permissionDecision: "allow" } }'
}

# No file path or file doesn't exist — allow through
if [ -z "$FILE_PATH" ] || [ ! -f "$FILE_PATH" ]; then
  allow
  exit 0
fi

FILE_SIZE=$(wc -c < "$FILE_PATH" 2>/dev/null || echo 0)

if [ "$FILE_SIZE" -gt "$MIN_SIZE_BYTES" ]; then
  SIZE_KB=$((FILE_SIZE / 1024))
  jq -n --arg path "$FILE_PATH" --arg size "${SIZE_KB}KB" '{
    hookSpecificOutput: {
      hookEventName: "PreToolUse",
      permissionDecision: "deny",
      permissionDecisionReason: ("File is \($size) — use freeloader to extract what you need without loading it into context:\nfreeloader \"<what you need>\" \"\($path)\"")
    }
  }'
else
  allow
fi
