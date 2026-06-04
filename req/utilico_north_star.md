# Utilico Energy — Billing Reconciliation Agent
## North Star & Principles

---

## North Star

> **A billing dispute that took 6–8 hours and 6–9 teams should take one person under 8 minutes, with a paper trail that holds up in front of a regulator.**

Everything else — speed, consistency, audit completeness — flows from that single sentence.

---

## Principles

### 1. Explainability over automation

The agent never acts — it only recommends. Every recommendation cites exactly which system and which data point produced it. A regulator or VP should be able to trace any line in any output back to a raw record without asking anyone.

*In practice:* no recommendation may appear in any output without a named source system and, where available, a specific record or timestamp.

---

### 2. Conflicts surface, never resolve silently

When two systems disagree, that disagreement is the finding — not something to paper over with a default. CC&B is never assumed authoritative. The human sees the contradiction and decides.

*In practice:* the system must surface all four cross-system conflict types explicitly. Silent reconciliation is a bug, not a feature.

---

### 3. One evidence base, many voices

The customer letter, the executive brief, and the engineering handoff are the same facts in different clothes. The system makes it structurally impossible to tell the customer one thing and the regulator another.

*In practice:* all three stakeholder outputs are rendered from a single reconciliation object. Divergent narratives cannot exist if there is only one source of truth.

---

### 4. Human judgment at the threshold, not throughout

The agent does the legwork — ingestion, classification, conflict detection, brief assembly. The DRI does the one thing only a human should do: approve action. One touchpoint, not nine.

*In practice:* no credit note, proration adjustment, or communication may be dispatched without explicit DRI approval. The approval gate is the only mandatory human step.

---

### 5. Speed is a safety property

The faster a conflict is detected and a brief is in front of the DRI, the smaller the window for an invalid bill to generate, revenue to post, or a regulatory deadline to pass. Latency is not just a UX concern — it is a risk control.

*In practice:* conflict detection must complete in under 15 seconds. Full context assembly must complete in under 7 minutes. These are hard targets, not aspirational ones.

---

### 6. Auditability is a first-class output

The audit trail is not logging for debugging — it is a deliverable. It gets the same care as the customer letter. Every claim in every output must be attributable, and the trail must be queryable for regulatory submissions.

*In practice:* 100% audit trail coverage is an acceptance criterion, not a stretch goal. The current baseline of ~40% is a risk, not a benchmark.

---

## How the principles connect

| Principle | Primary requirement | Key metric |
|-----------|-------------------|------------|
| Explainability over automation | FR-05, FR-06, FR-09 | 100% source citation |
| Conflicts surface, never silently resolve | FR-04, BR-07 | 0 silent reconciliations |
| One evidence base, many voices | FR-07, BR-08 | Regulatory consistency > 98% |
| Human judgment at the threshold | FR-08, BR-05 | 1 touchpoint per escalation |
| Speed is a safety property | NFR-01 | Context assembly < 7 min |
| Auditability is a first-class output | FR-09, NFR-02 | Audit completeness 100% |

---

## What success looks like at 90 days

- Billing error recurrence below 3% (down from 18%)
- First-contact resolution above 78% (up from 31%)
- CSR handle time 3–8 minutes (down from 45–90 min)
- Zero regulatory fines in the first full quarter of deployment
- Audit trail completeness at 100% on every escalation
- CSR trust score above 7/10 post-pilot

---

*Document owner: DRI assigned at escalation open. Last updated: June 2026.*
