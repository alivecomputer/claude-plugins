#!/bin/bash
# Hook: Context Watch -- UserPromptSubmit
# External change detection -- if another session modified walnut state files,
# tell the model to re-read before continuing.
#
# Previously also did periodic context-percentage re-injection (rules refresh
# at 20/40/60/80% usage, surfacing "Context is at NN%" to the model). Removed
# per issue #86: surfacing a context-budget countdown makes the model manage
# its own context instead of the task, and repeating instructions on a cadence
# breaks preserved-thinking's history-editing check. Session-health signals
# belong in the statusline (human-facing), not injected into the model's turn.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/alive-common.sh"

read_hook_input

# fn-15-la5.6: bridge fan-out -- helper is the SOLE emitter on the
# no-world-found path. find_world_or_warn emits hook-shaped JSON on
# stdout (or {} when the SessionStart sentinel is already taken /
# event isn't message-bearing) and returns 1 in-bash so we exit 0
# cleanly without printing JSON ourselves.
# // TODO(world-resolution-contract-v2): swap to find_world_or_die in cutover release
if ! find_world_or_warn "${HOOK_EVENT:-UserPromptSubmit}"; then
  exit 0
fi

SESSION_ID="${HOOK_SESSION_ID}"
[ -z "$SESSION_ID" ] && exit 0

# -- EXTERNAL CHANGE DETECTION --

# Find which walnut this session is working on
SQUIRRELS_DIR="$WORLD_ROOT/.alive/_squirrels"
ENTRY="$SQUIRRELS_DIR/$SESSION_ID.yaml"
[ ! -f "$ENTRY" ] && exit 0

WALNUT=$(grep '^walnut:' "$ENTRY" 2>/dev/null | sed 's/walnut: *//' || true)
[ -z "${WALNUT:-}" ] || [ "$WALNUT" = "null" ] && exit 0

# Find walnut's state files directory -- check _kernel/ first, fall back to walnut root
WALNUT_DIR=$(find "$WORLD_ROOT" -path "*/01_Archive" -prune -o -type d -name "$WALNUT" -print -quit 2>/dev/null || true)
[ -z "${WALNUT_DIR:-}" ] || [ ! -d "$WALNUT_DIR" ] && exit 0

if [ -d "$WALNUT_DIR/_kernel" ]; then
  WALNUT_KERNEL="$WALNUT_DIR/_kernel"
else
  WALNUT_KERNEL="$WALNUT_DIR"
fi

# Timestamp file tracks when this session last checked
LASTCHECK="/tmp/alive-lastcheck-${SESSION_ID}"

# On first run, just create the timestamp and exit
if [ ! -f "$LASTCHECK" ]; then
  date +%s > "$LASTCHECK"
  exit 0
fi

LAST_CHECK_TIME=$(cat "$LASTCHECK" 2>/dev/null || echo "0")

# Check if now.json or log.md were modified after our last check
# v3 flat: _kernel/now.json, _kernel/tasks.json  |  v2: _kernel/_generated/now.json  |  v1: now.md
CHANGED=""
for file in "$WALNUT_KERNEL/now.json" "$WALNUT_KERNEL/_generated/now.json" "$WALNUT_KERNEL/tasks.json" "$WALNUT_KERNEL/now.md" "$WALNUT_KERNEL/log.md" "$WALNUT_KERNEL/tasks.md"; do
  if [ -f "$file" ]; then
    # Get file mtime as epoch seconds
    if stat --version >/dev/null 2>&1; then
      MTIME=$(stat -c %Y "$file" 2>/dev/null || echo "0")
    else
      MTIME=$(stat -f %m "$file" 2>/dev/null || echo "0")
    fi
    if [ "$MTIME" -gt "$LAST_CHECK_TIME" ] 2>/dev/null; then
      CHANGED="${CHANGED} $(basename "$file")"
    fi
  fi
done

# Update timestamp
date +%s > "$LASTCHECK"

# If nothing changed, exit silently
[ -z "${CHANGED:-}" ] && exit 0

# Check if the change was made by US (same session_id in now.json squirrel field)
# now.json uses short IDs (first 8 chars), hook gets full UUID -- check both
# v3 flat: _kernel/now.json  |  v2: _kernel/_generated/now.json  |  v1: now.md
LAST_SQUIRREL=""
NOW_JSON_PATH=""
if [ -f "$WALNUT_KERNEL/now.json" ]; then
  NOW_JSON_PATH="$WALNUT_KERNEL/now.json"
elif [ -f "$WALNUT_KERNEL/_generated/now.json" ]; then
  NOW_JSON_PATH="$WALNUT_KERNEL/_generated/now.json"
fi
if [ -n "$NOW_JSON_PATH" ]; then
  if [ "$ALIVE_JSON_RT" = "python3" ]; then
    LAST_SQUIRREL=$(python3 -c "import json; d=json.load(open('$NOW_JSON_PATH')); print(d.get('squirrel',''))" 2>/dev/null || true)
  elif [ "$ALIVE_JSON_RT" = "node" ]; then
    LAST_SQUIRREL=$(node -e "try{const d=JSON.parse(require('fs').readFileSync('$NOW_JSON_PATH','utf8'));console.log(d.squirrel||'')}catch(e){console.log('')}" 2>/dev/null || true)
  fi
elif [ -f "$WALNUT_KERNEL/now.md" ]; then
  LAST_SQUIRREL=$(grep '^squirrel:' "$WALNUT_KERNEL/now.md" 2>/dev/null | sed 's/squirrel: *//' | tr -d '[:space:]' || true)
fi
SHORT_SID="${SESSION_ID:0:8}"
if [ "${LAST_SQUIRREL:-}" = "$SESSION_ID" ] || [ "${LAST_SQUIRREL:-}" = "$SHORT_SID" ]; then
  exit 0
fi

# Another session modified the walnut -- notify
CONTEXT_MSG="Another session just saved to ${WALNUT}. Changed:${CHANGED}. Re-read _kernel/now.json, _kernel/tasks.json and _kernel/log.md before continuing -- your context may be stale."
CONTEXT_ESCAPED=$(escape_for_json "$CONTEXT_MSG")
cat <<CHANGEEOF
{
  "hookSpecificOutput": {
    "hookEventName": "UserPromptSubmit",
    "additionalContext": "${CONTEXT_ESCAPED}"
  }
}
CHANGEEOF
exit 0
