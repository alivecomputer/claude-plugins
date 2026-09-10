# ALIVE v3.2.1 permissions

ALIVE v3.2.1 declares **14 command invocations across 5 Claude Code hook event types**. Those invocations call 13 unique hook scripts; `alive-repo-detect.sh` runs after both a new session and compaction.

The machine-readable declaration is [`plugins/alive/hooks/hooks.json`](plugins/alive/hooks/hooks.json). This page explains the same surface in user-facing terms.

| Claude Code event | When it runs | Declared scripts | Local reads | Local writes | External behaviour |
|---|---|---|---|---|---|
| `SessionStart` | New, resumed and compacted sessions | `alive-session-new.sh`, `alive-repo-detect.sh`, `alive-github-star-prompt.sh`, `alive-session-resume.sh`, `alive-session-compact.sh` | ALIVE rules, preferences, world index, walnut state and session records | Session records under `.alive/_squirrels/`, local statusline/configuration, generated world state and local star-prompt counters | None automatically. The star prompt can run `gh repo star` or open GitHub only after the user explicitly chooses to star. |
| `PreToolUse` | Before Claude Code writes files or invokes an MCP tool | `alive-log-guardian.sh`, `alive-rules-guardian.sh`, `alive-root-guardian.sh`, `alive-external-guard.sh` | Proposed tool name, target path and tool input | None | Can require confirmation or deny an undeclared external or protected-file action. It does not perform the external action itself. |
| `PostToolUse` | After Claude Code writes or edits a file | `alive-post-write.sh`, `alive-inbox-check.sh` | The changed path, relevant walnut state and inbox count | Local activity counters, projections and generated indexes | None. |
| `UserPromptSubmit` | When the user submits a prompt | `alive-context-watch.sh` | The session record and the active walnut's state-file timestamps and generated state | A per-session last-checked timestamp under the operating system's temporary directory | None. |
| `PreCompact` | Before Claude Code compacts its context window | `alive-pre-compact.sh` | The current session record | Appends a compaction timestamp and preserves local session state | None. |

## What the plugin can change

ALIVE manages files inside the selected ALIVE world and its `.alive/` system directory. It may also maintain the ALIVE statusline entry in the world's `.claude/settings.json`. Write guards are intended to prevent accidental edits to signed history, runtime rules and paths outside the selected world.

ALIVE's core context handling does not require an ALIVE account or hosted context service. Installing the plugin, following links, invoking external tools and choosing to star the repository are explicit network-capable actions governed by the destination and the user's confirmation.

Set `github_star_ask: false` in `.alive/preferences.yaml` to disable the local star invitations.
