# REQ-15

Intent: a highlighted Support agent sits at the top of the Agent Router sidepane, is selected by default, and onboards the operator.

Success:
1. Support has product role `support` (badge + warning highlight). It is not grouped under API/CLI/Remote.
2. Hide-all keeps Support plus the three typed starters (CLI, API, Remote). Default selection is Support.
3. On first open of Support with an empty transcript, inject a briefing that lists visible agents and inference (LiteLLM profiles / installed CLIs). If inference is missing, the briefing and pill D link to Settings.
4. Support pills: Explain Operating Swarm, Build my first team, Code a blueprint, and either Configure inference or Customise experience.
5. Chat renders markdown; Python fenced blocks are pretty-printed (language label + token colors). No extra UI framework.

Constraints: Do not merge unrelated open PRs. Do not invent TBD remote ports.

Owner: open-swarm engineer.
