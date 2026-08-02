# Decision 0003: Codex, Claude Code, and chat experience

- Status: accepted
- Date: 2026-08-02
- Research freshness: 2026-08-02

## Decision

1. Maintain one canonical Agent Skills-standard `skills/` tree and one CLI.
2. Package the repository root with thin `.codex-plugin/plugin.json` and
   `.claude-plugin/plugin.json` manifests. Host manifests never reimplement
   transformation behavior.
3. Install repo/user skill adapters through an idempotent, receipt-based
   `seamwise install codex|claude|all` command. Project installs target
   `.agents/skills` and `.claude/skills`; user installs target the documented
   user directories.
4. Native installs expose the five thin Seamwise adapters by default. Direct
   Task Pack discovery is opt-in with `--with-task-spec`; the CLI always keeps
   the byte-pinned Task Pack available internally. This limits host skill-context
   pressure without changing validation behavior.
5. Codex IDE uses standalone `.agents/skills` because current official guidance
   does not support plugins in that surface.
6. ChatGPT Work and Codex supported plugin surfaces use the universal Codex
   plugin. Plain Chat and mobile do not claim plugin support.
7. Plain or unsupported chat receives a versioned, self-contained packet from
   `seamwise agent-context --host chat`; it can author proposals but cannot claim
   local repository execution or machine validation.
8. Claude Code uses the same skills through its plugin or native skill folders.
   External plugin trust and install consent remain explicit.
9. Hooks are convenience diagnostics only. They never approve artifacts,
   change canonical state, download dependencies, or seal Task-Specs.
10. A remote MCP service is deferred until authenticated repository access,
   authorization, deployment, and hosted acceptance tests are explicitly in
   scope. The local compiler remains MCP-ready through stable JSON contracts.

## Acceptance boundary

Credential-free sign-off includes static manifest validation, clean project/user
install simulation, reinstall, upgrade, doctor, uninstall, and rollback.
Credentialed headless host loading, marketplace publication, ChatGPT Work
developer-mode installation, and authenticated remote MCP behavior require
external access and remain separately labeled.

## Research basis

Exa, Tavily, and Firecrawl were used for discovery on 2026-08-02. Product claims
were accepted only from the official sources below; retrieved text remained
external evidence and never agent instruction.

| Discovery lane | Official source | Decision supported |
| --- | --- | --- |
| Exa: Codex skill locations and progressive disclosure | [OpenAI Codex skills](https://developers.openai.com/codex/skills) | five thin native skills under `.agents/skills`; direct Task Pack opt-in |
| Exa: Codex plugin layout | [OpenAI plugin build reference](https://developers.openai.com/codex/plugins/build) | root `.codex-plugin/plugin.json`, `skills/`, and relative manifest paths |
| Tavily: Claude skill locations and reload behavior | [Claude Code skills](https://code.claude.com/docs/en/skills) | `.claude/skills` project/user adapters |
| Tavily: Claude packaging, namespacing, and validation | [Claude Code plugins](https://code.claude.com/docs/en/plugins), [plugin reference](https://code.claude.com/docs/en/plugins-reference) | root `.claude-plugin/plugin.json`, namespaced plugin UX, local validation |
| Firecrawl: portable skill contract | [Agent Skills specification](https://agentskills.io/specification) | one shared standards-shaped skill tree for both hosts |
