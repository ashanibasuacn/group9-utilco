# CLAUDE.md — Utilico Energy Billing Reconciliation Agent (Mock)

## Objective

Python mock application simulating an AI-driven billing reconciliation agent for Utilico Energy. Full requirements: [req/utilico_requirements.md](req/utilico_requirements.md). North star & principles: [req/utilico_north_star.md](req/utilico_north_star.md).

## North Star

> A billing dispute that took 6–8 hours and 6–9 teams should take one person under 8 minutes, with a paper trail that holds up in front of a regulator.

## Requirement context

 five enterprise systems (CC&B, MDM, OMS, CRM, GL) each hold a piece of the truth about a customer's billing situation, but they operate independently. When a disconnect event happens mid-cycle, none of them automatically tells the others. CC&B keeps billing. MDM keeps estimating reads. CRM logs the complaint. GL posts the revenue. Nobody reconciles the full picture until a human manually pulls data from all five — which takes 6–8 hours across 6–9 teams, produces inconsistent outputs, and leaves a 60% audit gap.


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


