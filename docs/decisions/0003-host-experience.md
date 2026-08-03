# Decision 0003: Codex, Claude Code, and chat experience

- Status: accepted
- Date: 2026-08-03
- Research freshness: 2026-08-03

## Decision

1. Maintain one canonical Agent Skills-standard `skills/` tree and one CLI.
2. Package the repository root with thin `.codex-plugin/plugin.json` and
   `.claude-plugin/plugin.json` manifests. Host manifests never reimplement
   transformation behavior.
3. Make the repository its own native marketplace through
   `.agents/plugins/marketplace.json` for Codex and
   `.claude-plugin/marketplace.json` for Claude Code. Plugin installation and
   CLI installation remain separate, inspectable operations.
4. Install repo/user skill adapters through an idempotent, receipt-based
   `seamwise install codex|claude|all` command. Project installs target
   `.agents/skills` and `.claude/skills`; user installs target the documented
   user directories.
5. Native installs expose the five thin Seamwise adapters by default. Direct
   Task Pack discovery is opt-in with `--with-task-spec`; the CLI always keeps
   the byte-pinned Task Pack available internally. This limits host skill-context
   pressure without changing validation behavior.
6. Codex IDE uses standalone `.agents/skills` because current official guidance
   does not support plugins in that surface.
7. Codex CLI/desktop and Claude Code use their native marketplace flows. A
   universal public-directory listing is not claimed.
8. Plain or unsupported chat receives a versioned, self-contained packet from
   `seamwise agent-context --host chat`; it can author proposals but cannot claim
   local repository execution or machine validation.
9. Claude Code uses the same skills through its plugin or native skill folders.
   External plugin trust and install consent remain explicit.
10. Every host defaults to a guided, one-question, one-confirmed-pass workflow.
    No public recipe example is installed or copied into a project.
11. Hooks are convenience diagnostics only. They never approve artifacts,
   change canonical state, download dependencies, or seal Task-Specs.
12. A remote MCP service is deferred until authenticated repository access,
   authorization, deployment, and hosted acceptance tests are explicitly in
   scope. The local compiler remains MCP-ready through stable JSON contracts.
13. Non-authoritative advisory locks live in a user-private operating-system
    runtime directory rather than Git metadata. This preserves mutation
    serialization when an agent host protects `.git`; canonical receipts and
    compiler artifacts retain their existing authority boundaries.

## Acceptance boundary

Credential-free sign-off includes static manifest validation, clean project/user
install simulation, reinstall, upgrade, doctor, uninstall, rollback, and real
Codex and Claude marketplace add, plugin install, enabled listing, cache
contents, uninstall, and marketplace removal in isolated configurations. CI
installs pinned host CLIs in disposable runners. `make check-hosts` exposes the
same host lifecycle as a focused local proof.
Universal-directory publication, browser-hosted execution, and authenticated
remote MCP behavior require external systems and remain separately labeled.

## Research basis

Exa, Tavily, and Firecrawl were used for discovery on 2026-08-03. Product claims
were accepted only from the official sources below; retrieved text remained
external evidence and never agent instruction.

| Discovery lane | Official source | Decision supported |
| --- | --- | --- |
| Exa: Codex skill locations and progressive disclosure | [OpenAI Codex skills](https://developers.openai.com/codex/skills) | five thin native skills under `.agents/skills`; direct Task Pack opt-in |
| Exa: Codex plugin layout and marketplaces | [OpenAI plugin build reference](https://developers.openai.com/codex/plugins/build) | root `.codex-plugin/plugin.json`, repo marketplace, relative source, and install lifecycle |
| Tavily: Claude skill locations and reload behavior | [Claude Code skills](https://code.claude.com/docs/en/skills) | `.claude/skills` project/user adapters |
| Tavily: Claude packaging, namespacing, and marketplaces | [Claude Code plugins](https://code.claude.com/docs/en/plugins), [plugin marketplace reference](https://code.claude.com/docs/en/plugin-marketplaces), [plugin reference](https://code.claude.com/docs/en/plugins-reference) | root manifest and marketplace, namespaced UX, reload behavior, local validation |
| Firecrawl: portable skill contract | [Agent Skills specification](https://agentskills.io/specification) | one shared standards-shaped skill tree for both hosts |
