# Requirements: Utilico Energy — Billing Reconciliation Agent

*Extracted from the Utilico Energy Billing Escalation Case Study*

---

## Problem Statement

Design an AI agent system that cross-references 5 independent enterprise billing systems in real time, detects architectural conflicts that produce invalid bills, and generates a decision-ready reconciliation brief with a consistent, regulator-defensible audit trail — replacing a manual process that takes 6–8 hours, exposes the business to regulatory risk, and produces inconsistent responses across teams.

---

## Functional Requirements

### FR-01 — System Ingestion (5 Sources)
The system must connect to and query all five of the following enterprise systems:

| # | System | Data Required |
|---|--------|--------------|
| 1 | Oracle CC&B (Customer Care & Billing) | Account status, billing period boundaries, billing rules applied, bill generation timestamp |
| 2 | MDM (Meter Data Management) | Meter read type (actual vs estimated), reads by date, consumption values mapped to billing period |
| 3 | Field Service / OMS (Operations Management) | Work order type, disconnect/reconnect timestamps, field technician confirmation records |
| 4 | CRM (Customer Care Platform) | Prior complaint history, complaint type, any billing-hold flags or manual notes on account |
| 5 | GL / Financials (General Ledger) | Revenue posting status, period of posting, reversal implications |

### FR-02 — Disconnect Event Trigger
- The agent workflow must be initiated automatically when an OMS disconnect event is detected
- The trigger must fire **before** the next CC&B billing run for the affected account
- Where a dispute has already been filed, the workflow must also be triggerable manually by a CSR or DRI

### FR-03 — Billing Period Reconciliation
- The agent must map the OMS disconnect timestamp against the CC&B billing period boundaries to determine whether billing overlap occurred
- The agent must classify each day in the billing period as: **pre-disconnect (billable)**, **post-disconnect (non-billable)**, or **disconnect day (requires proration rule)**
- MDM meter reads must be classified as **actual** or **estimated** and mapped to the same period breakdown

### FR-04 — Conflict Detection
The system must automatically identify and flag the following architectural conflicts:

| Conflict | Systems Involved |
|----------|-----------------|
| Full-cycle bill generated despite mid-cycle disconnect | OMS ↔ CC&B |
| Estimated reads applied to post-disconnect days (phantom consumption) | MDM ↔ OMS |
| Prior billing complaint on record with no billing-hold propagated | CRM ↔ CC&B |
| Revenue posted to GL for a bill currently under formal dispute | GL ↔ CRM / Customer Care |

- Conflict detection must complete in **< 15 seconds**
- Conflicts must be surfaced explicitly — the system must never silently resolve a contradiction

### FR-05 — Recommendation Engine
Based on reconciliation findings, the agent must generate one of the following recommended actions:

| Scenario | Recommended Action |
|----------|--------------------|
| Bill covers post-disconnect days | Suppress post-disconnect portion; issue prorated credit |
| MDM estimated reads applied post-disconnect | Flag as phantom consumption; adjust to zero for non-billable days |
| CRM complaint unlinked from billing record | Link complaint; apply billing-hold flag; trigger review |
| GL revenue already posted | Generate credit note; flag for revenue adjustment and regulatory filing |

Recommendations must cite the specific source system for every element of the rationale.

### FR-06 — Decision-Ready Context Brief
The system must produce a structured brief containing:
- **Confirmed facts** — per-system, with source citation and timestamp
- **Billing period breakdown** — pre/post/disconnect-day classification
- **Conflicts detected** — explicitly named, with systems in disagreement identified
- **Recommended action** — suppress / prorate / credit / flag exception
- **Confidence signals** — where data is incomplete or estimated reads cannot be verified, this must be stated

The brief must be readable and actionable by a regulator, VP, or DRI without additional context.

### FR-07 — Stakeholder Output Generation
From the same reconciliation evidence base, the system must auto-generate three audience-specific outputs:

| Output | Audience | Format |
|--------|----------|--------|
| Customer Summary | Affected customer | Non-technical, < 2 min read: what we found / what we've done / what happens next / next update date |
| Executive Brief | Internal leadership | 1-page: situation, impact, findings, next steps |
| Engineering Handoff | Engineering / CC&B configuration team | Jira story format: priority, linked systems, acceptance criteria for architectural fix |

All three outputs must be derived from the same evidence base — same facts, same citations, different format. The regulatory response must never contradict the customer summary or executive brief.

### FR-08 — Human-in-the-Loop Approval
- The DRI must review all reconciliation output before any action is taken or communication sent
- No credit note, proration adjustment, or regulatory submission may be initiated without explicit DRI approval
- All approvals, overrides, and exceptions must be logged with timestamp and approver identity
- The system must support a confidence signal that flags cases where human judgment is especially warranted

### FR-09 — Audit Trail
- Every claim in every output must cite the specific source system and, where available, the specific record or timestamp it was drawn from
- Audit trail coverage must be **100%** — no unattributed assertions permitted
- The trail must meet regulatory defensibility standards — traceable from recommendation back to raw system data
- Logs must be queryable for regulatory submissions and pattern analysis

### FR-10 — DRI Assignment
- A named DRI must be assigned at the point the escalation is opened
- The DRI owns the regulatory response and all stakeholder communications
- DRI identity must appear on all generated outputs

---

## Non-Functional Requirements

### NFR-01 — Speed

| Task | Target |
|------|--------|
| Full context assembly | < 7 minutes end-to-end |
| Conflict detection | < 15 seconds |
| First coherent stakeholder update | < 24 hours from escalation opened |
| Dispute resolution (target outcome) | < 5 minutes for reconciliation decision |

This replaces a manual process currently taking 6–8 hours and 2–5 days elapsed.

### NFR-02 — Audit Trail Completeness
- Must be maintained at **100%** on every escalation
- Current baseline: ~40% (manual, inconsistent)
- Required for regulatory defensibility

### NFR-03 — Regulatory Consistency
- All outputs must present identical facts and citations
- Regulatory inconsistency rate target: **< 2%** (down from ~30%)
- Regulatory submission consistency target: **> 98%**

### NFR-04 — Billing Error Recurrence
- Target: **< 3%** recurrence rate (down from ~18%)
- Achieved through architectural fix (OMS disconnect as CC&B suppression trigger) validated in 90-day roadmap

### NFR-05 — CSR Handle Time
- Target: **3–8 minutes** per escalation (down from 45–90 min)

### NFR-06 — First-Contact Resolution
- Target: **> 78%** first-contact resolution rate (up from ~31%)

### NFR-07 — Manual Touchpoints
- Target: **1 touchpoint per escalation** (exception review only), down from 6–9 teams involved manually

---

## Integration Requirements

### IR-01 — Phase 1 Priority (Day 0–30)
- OMS real-time disconnect event stream — must be live for the < 5 min SLA to hold
- Test with 10 real escalations in parallel with manual process

### IR-02 — Phase 2 (Day 30–60)
- MDM real read-type flagging (actual vs estimated) — real integration replacing manual IT data pull
- Expand to 3 CSR teams + regulatory affairs
- Add confidence scoring for proration recommendations

### IR-03 — Phase 3 (Day 60–90)
- Full production deployment across all billing escalation types
- CC&B billing rule update: OMS disconnect event = suppression trigger (architectural fix)
- Role-tailored output variants: CSR / Finance / Regulatory Affairs

### IR-04 — Architectural Fix (CC&B)
The following CC&B changes are in scope as a downstream engineering requirement:
- OMS disconnect timestamp must be cross-referenced at CC&B billing run time
- MDM estimated reads must be suppressed for disconnected premises
- CRM billing-hold flags must propagate to CC&B automatically

---

## Business Rules

| Rule | Description |
|------|-------------|
| BR-01 | A DRI must be named before any reconciliation output is finalised or communication sent |
| BR-02 | CC&B bill validity must never be the sole input to a dispute resolution decision — OMS, MDM, and CRM must always be cross-referenced |
| BR-03 | Estimated MDM reads applied to post-disconnect days must always be classified as phantom consumption and flagged for suppression |
| BR-04 | A prior CRM complaint on a billing account must trigger a review flag — billing-hold propagation to CC&B is mandatory |
| BR-05 | No credit note, proration adjustment, or regulatory response may be dispatched without DRI approval |
| BR-06 | Revenue already posted to GL for a disputed bill must be flagged immediately — GL reversal implications must be included in every executive brief where applicable |
| BR-07 | Conflicts between systems must be surfaced explicitly — the system must never silently reconcile a contradiction or default to CC&B as authoritative |
| BR-08 | The regulatory response must be generated from the same evidence base as the customer summary — no divergent narratives |

---

## Out of Scope (Initial Build)

- CC&B architectural fix (OMS suppression trigger) — engineering deliverable, not agent deliverable; scoped to day 90
- MDM real integration for read-type flagging (Phase 2, day 60)
- Role-tailored output variants for Finance and Regulatory Affairs (Phase 3, day 90)
- Confidence scoring for proration recommendations (Phase 2, day 60)
- Full production deployment across all billing escalation types (day 90)

---

## Acceptance Criteria

| Criterion | Target |
|-----------|--------|
| Context assembly time | < 7 minutes end-to-end |
| Conflict detection time | < 15 seconds |
| Audit trail completeness | 100% of outputs cite sources |
| Regulatory submission consistency | > 98% |
| Comms consistency | Same facts across all 3 stakeholder formats |
| First coherent stakeholder update | < 24 hours from escalation opened |
| Billing error recurrence rate | < 3% |
| First-contact resolution rate | > 78% |
| CSR handle time | 3–8 minutes |
| CSR trust score (post-pilot) | > 7/10 |
| Regulatory fines in first full quarter of deployment | 0 |
| Revenue at risk per dispute | < $150 |
