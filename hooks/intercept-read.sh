#!/bin/bash
# Claude Code PreToolUse hook — blocks Read on large files and redirects to freeloader.
# Files below the threshold, ranged reads (offset/limit), images, PDFs and
# notebooks pass through to the normal permission flow.
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
# No output means no decision, so the normal permission flow still applies.
if [ -f "$HOME/.config/freeloader/disabled" ]; then
  exit 0
fi

INPUT=$(cat -)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null)

# No file path or file doesn't exist — pass through with no decision
if [ -z "$FILE_PATH" ] || [ ! -f "$FILE_PATH" ]; then
  exit 0
fi

# Ranged Read (offset/limit) — Claude needs the raw text, e.g. before an Edit
if echo "$INPUT" | jq -e '.tool_input.offset != null or .tool_input.limit != null' >/dev/null 2>&1; then
  exit 0
fi

# Images, PDFs and notebooks — Read handles them natively, freeloader only reads text
EXT=$(echo "${FILE_PATH##*.}" | tr '[:upper:]' '[:lower:]')
case "$EXT" in
  png|jpg|jpeg|gif|webp|pdf|ipynb)
    exit 0
    ;;
esac

FILE_SIZE=$(wc -c < "$FILE_PATH" 2>/dev/null || echo 0)

if [ "$FILE_SIZE" -gt "$MIN_SIZE_BYTES" ]; then
  SIZE_KB=$((FILE_SIZE / 1024))
  jq -n --arg path "$FILE_PATH" --arg size "${SIZE_KB}KB" '{
    hookSpecificOutput: {
      hookEventName: "PreToolUse",
      permissionDecision: "deny",
      permissionDecisionReason: ("File is \($size) — use freeloader to extract what you need without loading it into context:\nfreeloader \"<what you need>\" \"\($path)\"\nTo edit, Read only the lines you need with offset/limit.")
    }
  }'
fi
