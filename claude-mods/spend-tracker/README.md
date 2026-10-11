# spend-tracker

A Claude Code mod that keeps a running dollar total of what you've spent on Claude Code, across every session (chats, `/clear`s, resumes) and every agent/subagent.

- Status line under the prompt: `Claude spend: $X this session · $Y all-time`
- `/spend` — all-time total, session count, this session's cost, last 10 sessions
- `/spend import` — add sessions from before the tracker was installed (reads Claude Code's saved transcripts, subagents included; safe to run again)
- `/spend reset` — clear the history

## Install

In a Claude Code terminal session:

```
/plugin install spend-tracker --marketplace shrihaanzaroo/portfolio_analyzer
```

Answer `y` to add the marketplace, then pick the **user** scope so it runs in every session.

## Notes

- Figures are Claude Code's own `/cost` estimate at API list prices. On a Pro/Max subscription your actual bill is the flat fee.
- Imported sessions are priced from the token counts saved in each transcript. They can read a little low (under ~10% in testing), since a few small background requests aren't saved.
- Only Claude Code sessions are counted; claude.ai web/mobile chats aren't visible to Claude Code.
- History is stored in the plugin's store under your local Claude config directory, so it accumulates per machine.
