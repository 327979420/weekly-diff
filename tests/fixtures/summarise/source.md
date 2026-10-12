## What's changed

- Added a `code` key to the Claude apps gateway's `managed.policies[]`: the same settings as `cli`, also applied in Claude Desktop's Code tab; beside `desktop`, it turns on Claude Desktop's gateway mode
- Added `autoCompactWindow` to subagent frontmatter and `--agents` definitions, so a subagent can auto-compact earlier than the main conversation's window
- Added `CLAUDE_CODE_WORKFLOW_SUBAGENT_MODEL` to run every workflow agent on one model while other subagents keep theirs
- Added `CLAUDE_CODE_OVERLOADED_RETRY_MAX_DELAY_MS` environment variable to set a longer maximum delay for the backoff when retrying an overloaded (529) request
- Added a note in `/plugin` on a plugin whose hooks are left out because another enabled plugin has the same name
- Added an `allow_large` option to the Read tool so Claude can read a text file past the usual size limits in one call when it needs the whole file and the context has room
- Fixed managed-settings `PreToolUse` hooks that deny a tool call with `"continue": false`, and managed `prompt` hooks that block one, refusing the call but not ending the turn
- Fixed PostToolUse hooks in managed settings not applying `updatedMCPToolOutput` in some sessions
- Fixed headless sessions starting a folder's `.mcp.json` or plugin MCP server that was switched off for that folder, after changing directory or reloading plugins
- Fixed a Claude apps gateway that serves `allowedProviders` with `"gateway"` locking out laptops that name that gateway in user settings
- Fixed a saved Claude apps gateway sign-in being ignored on machines whose managed settings set `forceLoginMethod` to `gateway` with no `forceLoginGatewayUrl` (regression in 2.1.295)
- Fixed `--teleport` opening an empty conversation when the session's history could not be r