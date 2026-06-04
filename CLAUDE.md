# CLAUDE.md — Utilico Energy Billing Reconciliation Agent (Mock)

## Objective

Python mock application simulating an AI-driven billing reconciliation agent for Utilico Energy. Full requirements: [req/utilico_requirements.md](req/utilico_requirements.md). North star & principles: [req/utilico_north_star.md](req/utilico_north_star.md).

## North Star

> A billing dispute that took 6–8 hours and 6–9 teams should take one person under 8 minutes, with a paper trail that holds up in front of a regulator.

## Guiding Principles

| Principle | What it means in practice |
|-----------|--------------------------|
| Explainability over automation | Agent only recommends — never acts. Every recommendation names its source system and record. |
| Conflicts surface, never resolve silently | When systems disagree, that contradiction is the finding. CC&B is never assumed authoritative. |
| One evidence base, many voices | Customer letter, exec brief, and engineering handoff are rendered from the same reconciliation object — divergent narratives are structurally impossible. |
| Human judgment at the threshold | DRI approval is the only mandatory human step — one touchpoint, not nine. |
| Speed is a safety property | Slow conflict detection = wider window for invalid bills, bad revenue posts, missed regulatory deadlines. < 15 sec and < 7 min are hard targets. |
| Auditability is a first-class output | The audit trail is a deliverable, not debug logging. 100% source citation is an acceptance criterion. |

## Implementation Rules

- This is a **demo app** — optimise for speed of delivery and clarity of demonstration, not production quality
- **Rich terminal UI** is mandatory — use the `rich` library for all output (tables, panels, progress, colour)
- Keep code **as small as possible** — no abstractions, no patterns, no layers unless they directly serve the demo
- Hardcode mock data and scenarios where it keeps things simple — no external databases or config files
- Functionality must be **visually compelling and complete** — every requirement in the brief should be demonstrable
- One command should run the full end-to-end scenario — zero setup friction for the demo
- No tests, no logging frameworks, no CI — only what is needed to make the demo work
- Every output must cite its source system — audit trail is a visible demo feature, not a background concern
- No output may proceed without the DRI approval step — the human-in-the-loop gate must be visible in the UI


