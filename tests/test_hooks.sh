#!/bin/bash
# Shell tests for the Claude Code PreToolUse hooks in hooks/.
#
# Runs each hook as a subprocess with sample PreToolUse JSON on stdin and a
# temp HOME. A PreToolUse hook must never auto-approve a tool: deny cases say
# "deny", pass-through cases print nothing (no output means no decision, so
# the normal permission flow applies).
#
# Needs only bash and jq — the hooks' own dependencies. No Python required.
#
# Run with:
#     bash tests/test_hooks.sh

set -u

HOOKS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/hooks"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

PASS=0
FAIL=0
HOOK_OUT=""
HOOK_ERR=""
HOOK_EXIT=0
HOME_DIR=""

# ── Helpers ─────────────────────────────────────────────────────────────────

if ! command -v jq >/dev/null 2>&1; then
  echo "error: jq is required (brew install jq)" >&2
  exit 1
fi

ok() {
  PASS=$((PASS + 1))
  echo "  ok  $1"
}

not_ok() {
  FAIL=$((FAIL + 1))
  echo "  FAIL  $1"
  [ -n "${2:-}" ] && echo "        $2"
}

# Fresh HOME for one test
new_home() {
  HOME_DIR="$(mktemp -d "$WORK/home.XXXXXX")"
}

# Kill switch: touch ~/.config/freeloader/disabled to bypass all hooks
disable() {
  mkdir -p "$HOME_DIR/.config/freeloader"
  touch "$HOME_DIR/.config/freeloader/disabled"
}

# run_hook <script> <payload> [NAME=VALUE ...] -> captures HOOK_OUT/HOOK_ERR/HOOK_EXIT.
# Strips FREELOADER_MIN_SIZE_KB from the environment before applying overrides.
run_hook() {
  local script="$1" payload="$2"
  shift 2
  HOOK_OUT="$(printf '%s' "$payload" | env -u FREELOADER_MIN_SIZE_KB "$@" HOME="$HOME_DIR" bash "$HOOKS_DIR/$script" 2>"$WORK/stderr")"
  HOOK_EXIT=$?
  HOOK_ERR="$(cat "$WORK/stderr")"
  if [ "$HOOK_EXIT" -ne 0 ]; then
    not_ok "$script exits $HOOK_EXIT" "stderr: $HOOK_ERR"
  fi
  # Regression guard (#28): a PreToolUse hook must never auto-approve a tool.
  if printf '%s' "$HOOK_OUT" | grep -qF '"allow"'; then
    not_ok "$script auto-approves via \"allow\"" "output: $HOOK_OUT"
  fi
}

assert_passes_through() {
  if [ -z "$HOOK_OUT" ]; then
    ok "$1"
  else
    not_ok "$1" "expected no output (no decision), got: $HOOK_OUT"
  fi
}

assert_denies() {
  local decision
  decision="$(printf '%s' "$HOOK_OUT" | jq -r '.hookSpecificOutput.permissionDecision // empty')"
  if [ "$decision" = "deny" ]; then
    ok "$1"
  else
    not_ok "$1" "expected permissionDecision \"deny\", got: \"${decision:-<none>}\""
  fi
}

# Output must contain a fixed substring (reason text, tip text, ...)
assert_output_contains() {
  if printf '%s' "$HOOK_OUT" | grep -qF "$2"; then
    ok "$1"
  else
    not_ok "$1" "output does not contain: $2 — output: $HOOK_OUT"
  fi
}

# ── Payloads ────────────────────────────────────────────────────────────────

read_payload() { # <file_path> [offset] [limit]
  jq -n --arg path "$1" --argjson offset "${2:-null}" --argjson limit "${3:-null}" \
    '{hook_event_name: "PreToolUse", tool_name: "Read", tool_input: {file_path: $path, offset: $offset, limit: $limit}}'
}

webfetch_payload() { # [url]
  jq -n --arg url "${1:-https://example.com/docs}" \
    '{hook_event_name: "PreToolUse", tool_name: "WebFetch", tool_input: {url: $url, prompt: "summarize"}}'
}

# ── intercept-read ───────────────────────────────────────────────────────────

big_file() { # <path> — 11KB, above the default 10KB threshold
  head -c $((11 * 1024)) /dev/zero | tr '\0' x > "$1"
}

t_intercept_read_large_file_denied() {
  new_home
  big_file "$WORK/big.log"
  run_hook intercept-read.sh "$(read_payload "$WORK/big.log")"
  assert_denies "large file denied"
  assert_output_contains "reason reports the size" "11KB"
  assert_output_contains "reason reports the path" "$WORK/big.log"
}

t_intercept_read_small_file_passes_through() {
  new_home
  echo hello > "$WORK/small.txt"
  run_hook intercept-read.sh "$(read_payload "$WORK/small.txt")"
  assert_passes_through "small file passes through"
}

t_intercept_read_missing_file_passes_through() {
  new_home
  run_hook intercept-read.sh "$(read_payload "$WORK/nope.txt")"
  assert_passes_through "missing file passes through"
}

t_intercept_read_no_file_path_passes_through() {
  new_home
  run_hook intercept-read.sh '{"tool_name": "Read", "tool_input": {}}'
  assert_passes_through "no file_path passes through"
}

t_intercept_read_threshold_env_var() {
  new_home
  big_file "$WORK/big.log"
  run_hook intercept-read.sh "$(read_payload "$WORK/big.log")" FREELOADER_MIN_SIZE_KB=20
  assert_passes_through "11KB file passes with FREELOADER_MIN_SIZE_KB=20"
}

t_intercept_read_ranged_reads_pass_through() {
  new_home
  big_file "$WORK/big.log"
  run_hook intercept-read.sh "$(read_payload "$WORK/big.log" 50)"
  assert_passes_through "ranged read with offset passes through"
  run_hook intercept-read.sh "$(read_payload "$WORK/big.log" null 100)"
  assert_passes_through "ranged read with limit passes through"
}

t_intercept_read_binary_types_pass_through() {
  new_home
  local ext
  for ext in png PNG pdf ipynb; do
    big_file "$WORK/big.$ext"
    run_hook intercept-read.sh "$(read_payload "$WORK/big.$ext")"
    assert_passes_through ".$ext passes through"
    rm "$WORK/big.$ext"
  done
}

t_intercept_read_kill_switch() {
  new_home
  disable
  big_file "$WORK/big.log"
  run_hook intercept-read.sh "$(read_payload "$WORK/big.log")"
  assert_passes_through "kill switch passes large file through"
}

# ── block-webfetch ──────────────────────────────────────────────────────────

t_block_webfetch_denied() {
  new_home
  run_hook block-webfetch.sh "$(webfetch_payload)"
  assert_denies "WebFetch denied"
  assert_output_contains "reason suggests freeloader" "freeloader"
}

t_block_webfetch_kill_switch() {
  new_home
  disable
  run_hook block-webfetch.sh "$(webfetch_payload)"
  assert_passes_through "kill switch passes WebFetch through"
}

# ── suggest-webfetch ─────────────────────────────────────────────────────────

t_suggest_webfetch_tip_reaches_claude() {
  new_home
  run_hook suggest-webfetch.sh "$(webfetch_payload "https://example.com/a")"
  assert_output_contains "tip goes to Claude via additionalContext" "curl -s https://example.com/a | freeloader"
  if printf '%s' "$HOOK_OUT" | jq -e '.hookSpecificOutput | has("permissionDecision") or has("permissionDecisionReason")' >/dev/null; then
    not_ok "tip carries no permission decision" "output: $HOOK_OUT"
  else
    ok "tip carries no permission decision"
  fi
}

t_suggest_webfetch_no_url_passes_through() {
  new_home
  run_hook suggest-webfetch.sh '{"tool_name": "WebFetch", "tool_input": {}}'
  assert_passes_through "no url passes through"
}

t_suggest_webfetch_kill_switch() {
  new_home
  disable
  run_hook suggest-webfetch.sh "$(webfetch_payload)"
  assert_passes_through "kill switch passes WebFetch through"
}

# ── Runner ───────────────────────────────────────────────────────────────────

run_section() { # <title> <test>...
  local title="$1"
  shift
  echo "$title"
  local t
  for t in "$@"; do
    "$t"
  done
}

run_section "intercept-read.sh" \
  t_intercept_read_large_file_denied \
  t_intercept_read_small_file_passes_through \
  t_intercept_read_missing_file_passes_through \
  t_intercept_read_no_file_path_passes_through \
  t_intercept_read_threshold_env_var \
  t_intercept_read_ranged_reads_pass_through \
  t_intercept_read_binary_types_pass_through \
  t_intercept_read_kill_switch

run_section "block-webfetch.sh" \
  t_block_webfetch_denied \
  t_block_webfetch_kill_switch

run_section "suggest-webfetch.sh" \
  t_suggest_webfetch_tip_reaches_claude \
  t_suggest_webfetch_no_url_passes_through \
  t_suggest_webfetch_kill_switch

echo ""
if [ "$FAIL" -eq 0 ]; then
  echo "$PASS assertions passed"
  exit 0
else
  echo "$PASS passed, $FAIL FAILED"
  exit 1
fi
