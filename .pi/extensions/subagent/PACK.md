# Pack: subagent

Official Pi spawn: a fresh `pi` process per task (`--mode json -p --no-session`). Copied from `packages/coding-agent/examples/extensions/subagent`. Do not replace this with same-session hats.

| Tool | Modes |
|------|--------|
| `task` | `{ agent, task }` single; `{ tasks: [...] }` parallel; `{ chain: [...] }` sequential `{previous}` |

Project agents: `.pi/agents/*.md` (this repo defaults `agentScope: "both"`).
