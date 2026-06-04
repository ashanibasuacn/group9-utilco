# Requirements: Utilico Energy — Billing Reconciliation Agent
## Version 2.0 — Updated June 2026

*Original requirements extracted from the Utilico Energy Billing Escalation Case Study.
This version incorporates design decisions made during the Accenture engagement session:
agent workflow pipeline, role-based UI specification, MongoDB data architecture,
persona definitions, trigger strategy, and mock application scope.*

---

## North Star

> *A billing dispute that took 6–8 hours and 6–9 teams should take one person under 8 minutes, with a paper trail that holds up in front of a regulator.*

---

## Design Principles

1. **Explainability over automation** — every recommendation cites source system and timestamp. No black-box outputs.
2. **Conflicts surface, never resolve silently** — BR-07: the system never defaults to CC&B as authoritative.
3. **One evidence base, many voices** — customer letter, exec brief, and Jira ticket rendered from the same object. Divergent narratives structurally impossible.
4. **Human judgment at the threshold** — the agent does the legwork; the DRI holds the authority. One touchpoint, not nine.
5. **Speed is a safety property** — latency is risk. The faster a conflict is detected, the smaller the window for an invalid bill.
6. **Auditability is a first-class output** — the audit trail is a deliverable, not a log.

---

## Problem Statement

Billing truth is distributed across 5 independent enterprise systems. When a disconnect event occurs mid-cycle, none of the systems notifies the others. CC&B keeps billing. MDM applies estimated reads (phantom consumption). CRM logs complaints. GL posts revenue. No architectural mechanism prevents invalid bills from being generated.

Result: 4 compounding failures —
- **Operational** — 6–8 hours per dispute, 6–9 teams involved
- **Financial** — $800–$4,200 revenue at risk per dispute
- **Regulatory** — ~30% inconsistency rate between customer and regulatory responses
- **Customer trust** — ~31% first-contact resolution rate, 54/100 billing CSAT

Root cause: not data quality — architectural isolation. The data exists across all 5 systems. It is never assembled in one place, in time, with explicit conflict detection, before a decision is made.

---

## Stakeholder Personas

### 5 Human Personas

| Persona | Role | Type | Key pain (before) | Key gain (after) |
|---|---|---|---|---|
| Customer | Affected account holder | External | 2–5 days, ~31% FCR, inconsistent answers | <24 hrs update, >78% FCR, plain-language summary |
| CSR | Customer Service Representative | Internal · Frontline | 45–90 min, 5 systems, 6–9 teams | 3–8 min, one-click trigger, agent brief |
| DRI | Directly Responsible Individual | Internal · Decision authority | No brief, no trail, unclear ownership | Decision-ready brief, 1-click approval, 100% audit |
| Executive | VP / Senior Leadership | Internal · Strategic oversight | No structured brief, exposure unquantified | 1-page brief, GL reversal included, 0 fines target |
| Engineering | CC&B Configuration Team | Internal · Technical | No structured handoff, 18% recurrence | Auto-generated Jira, acceptance criteria, <3% recurrence |

### The Analyst — AI Persona

The Analyst is the AI reconciliation agent. It is not a background process — it is a named actor in the workflow with defined responsibilities, performance targets, and a hard constraint: it never makes the final decision.

| Attribute | Value |
|---|---|
| Type | AI Actor |
| Availability | Always on · Zero-latency |
| Trigger | OMS auto-trigger (proactive) or CSR/DRI manual trigger (reactive) |
| Output | Decision-ready context brief with 100% citation coverage |
| Hard constraint | Never dispatches outputs without explicit DRI approval (BR-05) |

**Performance targets (NFR-01):**

| Task | Target |
|---|---|
| Full context assembly end-to-end | < 7 minutes |
| Conflict detection | < 15 seconds |
| Brief generation | < 60 seconds |
| Citation coverage | 100% |
| Conflicts silently resolved | 0 |

---

## Agent Workflow — 7-Step Pipeline

### Step 1 — Trigger & DRI Assignment
**Pattern:** Event-driven trigger with dual entry points (FR-02)

**Trigger A — Proactive (preferred):** OMS disconnect event fires automatically before the next CC&B billing run. The bad bill never reaches the customer.

**Trigger B — Reactive:** CSR or DRI manually triggers from the escalation screen when a dispute has already been filed. Replaces the 45–90 min manual investigation.

**Output:** Escalation ID created · DRI assigned and stamped on all outputs (FR-10, BR-01) · Pipeline state: *Initiated*

---

### Step 2 — Parallel Ingestion
**Pattern:** Parallel fan-out retrieval across all 5 systems (FR-01)

All 5 system queries issued concurrently. No system treated as authoritative over another (BR-02). Every field extracted is stamped with source system and timestamp for the audit trail (FR-09).

| System | Data extracted |
|---|---|
| CC&B | Account status · billing period boundaries · billing rules · bill generation timestamp |
| MDM | Meter read type (actual vs estimated) · reads by date · consumption values mapped to period |
| OMS | Work order type · disconnect/reconnect timestamps · field technician confirmation records |
| CRM | Prior complaint history · complaint type · billing-hold flags · manual account notes |
| GL | Revenue posting status · period of posting · reversal implications |

**Output:** Unified evidence object — all 5 system payloads normalised and timestamped · Pipeline state: *Evidence assembled*

---

### Step 3 — Reconciliation
**Pattern:** Temporal cross-reference and day-level classification (FR-03)

The agent aligns three independent time axes — CC&B billing period boundaries, OMS disconnect timestamp, and MDM read dates — into a single reconciled timeline. Every day in the billing period is assigned exactly one classification.

| Classification | Condition |
|---|---|
| Pre-disconnect (billable) | Day falls before OMS disconnect timestamp |
| Disconnect day (proration required) | Day of disconnect — proration rule applied |
| Post-disconnect (non-billable) | Day falls after OMS disconnect timestamp |

MDM reads are mapped to the same day-level breakdown. Estimated reads on post-disconnect days are flagged as phantom consumption (BR-03).

**Output:** Day-level period map · MDM read classification per day · Billing overlap confirmed/denied · Reconciliation object written to audit trail

---

### Step 4 — Conflict Detection
**Pattern:** Rule-based cross-system validation against reconciled evidence (FR-04)

Four deterministic checks applied to the reconciled evidence object. Conflicts are binary — present or absent. No probabilistic scoring. BR-07 prohibits silent resolution.

| ID | Systems | Invariant |
|---|---|---|
| C1 | OMS ↔ CC&B | Full-cycle bill generated despite mid-cycle disconnect — no proration or suppression triggered |
| C2 | MDM ↔ OMS | Estimated reads applied to post-disconnect days — phantom consumption on disconnected premise |
| C3 | CRM ↔ CC&B | Prior billing complaint on record with no billing-hold propagated to CC&B |
| C4 | GL ↔ CRM | Revenue posted to GL for a bill currently under formal regulatory dispute |

**NFR target:** < 15 seconds (NFR-01)

**Output:** Conflict manifest — all triggered conflicts with systems named, invariant violated, and evidence cited · Each conflict written to audit trail · Confidence signal raised if any system data is missing

---

### Step 5 — Recommendation & Decision-Ready Brief
**Pattern:** LLM reasoning over structured evidence + deterministic brief assembly (FR-05, FR-06)

Two sub-steps: (a) LLM maps each detected conflict to the correct recommended action; (b) brief assembler stitches confirmed facts, period breakdown, conflicts, and recommendations into the FR-06 structured format with 100% citation coverage.

| Conflict | Recommended action |
|---|---|
| C1 — OMS ↔ CC&B | Suppress post-disconnect portion · issue prorated credit |
| C2 — MDM ↔ OMS | Flag phantom consumption · adjust MDM to zero for non-billable days |
| C3 — CRM ↔ CC&B | Link CRM complaint · apply billing-hold flag · trigger review |
| C4 — GL ↔ CRM | Generate credit note · flag GL for revenue adjustment · regulatory filing |

**Brief must contain (FR-06):**
- Confirmed facts per system with source citation and timestamp
- Billing period breakdown with day-level classification
- Conflicts detected with systems in disagreement explicitly named
- Recommended action per conflict
- Confidence signals where data is incomplete or reads cannot be verified

**NFR target:** < 60 seconds brief generation · 100% citation coverage (NFR-01, NFR-02)

**Output:** Decision-ready context brief · Brief written to audit trail · Ticket status: *Awaiting DRI* · CSR and DRI dashboards notified

---

### Step 6 — DRI Approval Gate
**Pattern:** Human-in-the-loop approval gate (FR-08, FR-09, FR-10)

Hard gate — pipeline cannot proceed without explicit DRI action. Three decision paths:

| Decision | Consequence |
|---|---|
| **Approve** | Pipeline proceeds to step 7. All outputs dispatched automatically. Approval logged with timestamp + DRI identity. |
| **Reject** | Mandatory reason required. Ticket returned to CSR with rejection note. Logged with timestamp, DRI identity, and reason. |
| **Flag exception** | Case escalated for manual review. Analyst Manager notified. Pipeline paused. |

**NFR target:** < 5 minutes DRI decision time (NFR-01) — requires brief to be actionable without further research

**Output:** Decision logged to immutable audit trail (FR-09) · Pipeline state updated · CSR notified of outcome

---

### Step 7 — 3 Outputs Dispatched
**Pattern:** Single-source multi-format generation (FR-07, BR-08)

All three outputs rendered from the same reconciliation evidence object. BR-08 makes divergent narratives structurally impossible.

| Output | Audience | Format |
|---|---|---|
| Customer Summary | Affected customer | Plain language · < 2 min read · what we found / what we've done / what happens next / next update date |
| Executive Brief | Internal leadership | 1-page · situation, impact, findings, next steps · GL reversal implications · regulatory exposure stated |
| Engineering Handoff | CC&B Configuration Team | Jira story · P1 priority · linked systems (OMS-DISCON, MDM-EST-READS) · 6 acceptance criteria |

**Engineering Jira acceptance criteria (BILL-NEW-1147):**
1. OMS disconnect timestamp cross-referenced at CC&B billing run time
2. MDM estimated reads suppressed for disconnected premises automatically
3. CRM billing-hold flags propagated to CC&B without manual link
4. Proration logic tested across mixed-cycle scenarios
5. Staged deploy with 4-week parallel validation
6. Regulator-ready audit log per case — every claim cites source system

**NFR target:** < 24 hours first coherent stakeholder update from escalation opened (NFR-01)

**Output:** 3 outputs dispatched · Audit trail finalised · Ticket status: *Resolved* · Analyst Manager execution log updated

---

## Functional Requirements

### FR-01 — System Ingestion (5 Sources)
The system must connect to and query all five enterprise systems in parallel. No system may be treated as authoritative over the others (BR-02).

| # | System | Data Required |
|---|---|---|
| 1 | Oracle CC&B | Account status · billing period boundaries · billing rules applied · bill generation timestamp |
| 2 | MDM | Meter read type (actual vs estimated) · reads by date · consumption values mapped to billing period |
| 3 | OMS / Field Service | Work order type · disconnect/reconnect timestamps · field technician confirmation records |
| 4 | CRM | Prior complaint history · complaint type · billing-hold flags · manual notes on account |
| 5 | GL / Financials | Revenue posting status · period of posting · reversal implications |

### FR-02 — Disconnect Event Trigger (Dual Strategy)
- **Trigger A (proactive):** Agent workflow initiated automatically when OMS disconnect event detected. Must fire before the next CC&B billing run for the affected account.
- **Trigger B (reactive):** Where a dispute has already been filed, workflow must be triggerable manually by a CSR or DRI from the escalation screen.

### FR-03 — Billing Period Reconciliation
- Agent must map OMS disconnect timestamp against CC&B billing period boundaries
- Every day in the billing period must be classified as: pre-disconnect (billable), post-disconnect (non-billable), or disconnect day (proration required)
- MDM meter reads must be classified as actual or estimated and mapped to the same day-level breakdown
- Estimated reads on post-disconnect days must be flagged as phantom consumption (BR-03)

### FR-04 — Conflict Detection
- System must automatically detect and explicitly surface all 4 architectural conflict types (C1–C4)
- Conflict detection must complete in < 15 seconds
- Conflicts must never be silently resolved (BR-07)
- Each conflict must cite the systems in disagreement and the invariant violated

### FR-05 — Recommendation Engine
- Agent must generate a recommended action for each detected conflict
- Every recommendation must cite the specific source system for every element of the rationale
- Recommendations map to the 4 scenarios defined in the agent workflow step 5

### FR-06 — Decision-Ready Context Brief
- Must contain: confirmed facts (cited), period breakdown, conflicts, recommendations, confidence signals
- Must be readable and actionable by a regulator, VP, or DRI without additional context
- 100% citation coverage — no unattributed assertions (NFR-02)

### FR-07 — Stakeholder Output Generation
- Three audience-specific outputs generated from the same evidence base (BR-08)
- Customer Summary · Executive Brief · Engineering Handoff (Jira)
- Regulatory response must never contradict customer summary

### FR-08 — Human-in-the-Loop Approval
- DRI must review all reconciliation output before any action is taken or communication sent
- No credit note, proration adjustment, or regulatory submission may be dispatched without DRI approval (BR-05)
- Three decision paths: approve · reject (mandatory reason) · flag exception
- All decisions logged with timestamp and approver identity (FR-09)
- System must support confidence signal that flags cases where human judgment is especially warranted

### FR-09 — Audit Trail
- Every claim must cite specific source system and, where available, the specific record or timestamp
- Coverage must be 100% on every escalation (NFR-02)
- Trail must meet regulatory defensibility standards — traceable from recommendation back to raw system data
- Logs must be queryable for regulatory submissions and pattern analysis
- Append-only — records must never be updated or deleted

### FR-10 — DRI Assignment
- A named DRI must be assigned at the point the escalation is opened (BR-01)
- DRI owns the regulatory response and all stakeholder communications
- DRI identity must appear on all generated outputs

---

## Role-Based User Interface

### Three roles — one application with role-based login

#### CSR — Customer Service Representative
**Screens:** Raise ticket · My tickets

- Raise ticket: Account ID · dispute type · notes · submit triggers The Analyst immediately (FR-02 Trigger B)
- On submit: DRI assigned (BR-01, FR-10) · agent triggered · ticket status set to *Analysing*
- Ticket list: status badges (Analysing → Awaiting DRI → Approved/Rejected → Resolved)
- Notified when DRI approves (outputs ready to send) or rejects (reason shown)

**Key NFR:** Handle time 3–8 min (NFR-05) · FCR > 78% (NFR-06)

#### DRI — Directly Responsible Individual
**Screens:** Ticket queue · Analyst brief + decision

- Queue shows: new tickets (brief ready) · pending (agent still running) · historical
- Brief review screen: full context brief · 4 conflicts summary · Approve / Reject / Flag exception
- Rejection requires mandatory reason field — logged to audit trail (FR-09)
- On approval: outputs dispatched automatically (FR-07) · DRI does not send manually
- Sees all unassigned tickets + tickets assigned to them

**Key NFR:** DRI decision time < 5 min (NFR-01)

#### Analyst Manager — System Oversight
**Screens:** Health dashboard · Audit trail query

- Health dashboard: avg assembly time vs < 7 min target · audit completeness · regulatory consistency · DRI approval backlog · recent execution feed
- Audit trail: filterable by account, system, date · one row per claim · timestamp + source system + claim text
- Alerts: NFR-01 breach (assembly > 7 min) · audit completeness < 100% · DRI backlog threshold exceeded

**Key NFRs:** NFR-01 · NFR-02 · NFR-03 · FR-09

### Ticket status flow
`CSR submits` → `Analyst: Analysing` → `DRI: Awaiting review` → `Approved → Resolved` or `Rejected → Back to CSR`

---

## Non-Functional Requirements

### NFR-01 — Speed

| Task | Target | Scope |
|---|---|---|
| Full context assembly end-to-end | < 7 minutes | Agent steps 2–5 |
| Conflict detection | < 15 seconds | Agent step 4 only |
| Brief generation | < 60 seconds | Agent step 5 only |
| DRI reconciliation decision | < 5 minutes | Human step 6 |
| First coherent stakeholder update | < 24 hours | From escalation opened |

*Note: The < 5 min figure applies specifically to the DRI decision time (step 6), not to full context assembly. The < 7 min target applies to agent steps 2–5 (ingestion through brief generation).*

### NFR-02 — Audit Trail Completeness
- Must be maintained at 100% on every escalation
- Current baseline: ~40% (manual, inconsistent)
- Required for regulatory defensibility

### NFR-03 — Regulatory Consistency
- All outputs must present identical facts and citations
- Regulatory inconsistency rate target: < 2% (down from ~30%)
- Regulatory submission consistency target: > 98%

### NFR-04 — Billing Error Recurrence
- Target: < 3% recurrence rate (down from ~18%)
- Achieved through CC&B architectural fix (OMS disconnect as suppression trigger) — Day 90 roadmap

### NFR-05 — CSR Handle Time
- Target: 3–8 minutes per escalation (down from 45–90 min)

### NFR-06 — First-Contact Resolution
- Target: > 78% first-contact resolution rate (up from ~31%)

### NFR-07 — Manual Touchpoints
- Target: 1 touchpoint per escalation (DRI approval only), down from 6–9 teams

---

## Data Architecture — MongoDB

### Design principles
- Document model chosen for heterogeneous source system payloads (no forced normalisation)
- Single document read for full DRI brief context (no joins required at query time)
- Append-only audit trail with write concern `majority` for regulatory defensibility
- 5 separate stub collections mirror real integration architecture — one per system

### 10 Collections

#### Mock Source Systems (6 collections)

| Collection | Purpose | Join key |
|---|---|---|
| `accounts` | Master customer data — shared reference across all 5 systems | `account_id` |
| `ccb_stubs` | Oracle CC&B mock — billing period, rules, bill timestamp | `account_id` |
| `mdm_stubs` | MDM mock — meter reads per day, actual vs estimated, consumption | `account_id` |
| `oms_stubs` | OMS mock — work orders, disconnect timestamp, field tech records | `account_id` |
| `crm_stubs` | CRM mock — complaint history, billing-hold flags, account notes | `account_id` |
| `gl_stubs` | GL mock — revenue posting status, period, reversal implications | `account_id` |

All 5 stub collections share `account_id` as the universal join key. Agent fans out across all 5 in parallel during step 2 ingestion (FR-01).

#### Transactional (1 collection)

| Collection | Purpose |
|---|---|
| `escalations` | Core transactional. One document per escalation. All 7 pipeline step outputs embedded as sub-documents under a `pipeline` object. |

**Pipeline sub-documents within `escalations`:**

| Field | Step | Contents |
|---|---|---|
| `pipeline.step_1_trigger` | 1 | Trigger type · dispute type · notes · triggered_at |
| `pipeline.step_2_ingestion` | 2 | Snapshots of all 5 system payloads · extracted_at per source · duration_ms |
| `pipeline.step_3_reconciliation` | 3 | Day-level period map array · disconnect timestamp · summary counts |
| `pipeline.step_4_conflicts` | 4 | Conflict manifest array — C1–C4 detected flags · invariants · duration_ms |
| `pipeline.step_5_brief` | 5 | Recommendations array · brief_text · confidence_signal · citation_coverage |
| `pipeline.step_6_dri` | 6 | Decision (approved/rejected/exception) · decided_at · decided_by · reason · decision_latency_ms |
| `pipeline.step_7_outputs` | 7 | customer_summary · executive_brief · engineering_handoff — all embedded |

**Escalation status values:** `initiated` → `analysing` → `awaiting_dri` → `approved` → `rejected` → `resolved`

#### Operational (3 collections)

| Collection | Purpose |
|---|---|
| `audit_trail` | Append-only. One document per claim. Source system + timestamp citation per entry. Independently queryable for regulatory submissions (FR-09). Write concern: `majority`. Never updated or deleted. |
| `analyst_executions` | One document per agent run. Step-level timing with `nfr_target_ms` and `breach` flag per step. Powers Analyst Manager health dashboard. Separate `agent_duration_ms` vs `total_duration_ms`. |
| `users` | CSR · DRI · Analyst Manager. Role enum · assigned escalations array for DRI queue. DRI identity required for FR-10 and BR-01. |

---

## Business Rules

| Rule | Description |
|---|---|
| BR-01 | A DRI must be named before any reconciliation output is finalised or communication sent |
| BR-02 | CC&B bill validity must never be the sole input to a dispute resolution decision — OMS, MDM, and CRM must always be cross-referenced |
| BR-03 | Estimated MDM reads applied to post-disconnect days must always be classified as phantom consumption and flagged for suppression |
| BR-04 | A prior CRM complaint on a billing account must trigger a review flag — billing-hold propagation to CC&B is mandatory |
| BR-05 | No credit note, proration adjustment, or regulatory response may be dispatched without DRI approval |
| BR-06 | Revenue already posted to GL for a disputed bill must be flagged immediately — GL reversal implications must be included in every executive brief where applicable |
| BR-07 | Conflicts between systems must be surfaced explicitly — the system must never silently reconcile a contradiction or default to CC&B as authoritative |
| BR-08 | The regulatory response must be generated from the same evidence base as the customer summary — no divergent narratives |

---

## Integration Requirements

### IR-01 — Phase 1 (Day 0–30)
- OMS real-time disconnect event stream — required for Trigger A (proactive) to function. Without this, only Trigger B (reactive CSR) is available.
- Test with 10 real escalations in parallel with manual process
- Mock: `oms_stubs` collection seeded with realistic disconnect scenarios

### IR-02 — Phase 2 (Day 30–60)
- MDM real read-type flagging (actual vs estimated) — replaces manual IT data pull
- Expand to 3 CSR teams + regulatory affairs
- Add confidence scoring for proration recommendations
- Mock: `mdm_stubs` updated with real read-type data

### IR-03 — Phase 3 (Day 60–90)
- Full production deployment across all billing escalation types
- CC&B billing rule update: OMS disconnect event = suppression trigger (architectural fix)
- Role-tailored output variants: CSR / Finance / Regulatory Affairs

### IR-04 — CC&B Architectural Fix
Engineering deliverable, not agent deliverable. Scoped to Day 90.
- OMS disconnect timestamp cross-referenced at CC&B billing run time
- MDM estimated reads suppressed for disconnected premises automatically
- CRM billing-hold flags propagated to CC&B without manual link required

---

## Mock Application Scope

### In scope for initial mock build
- Single-page HTML application with role-based login (CSR · DRI · Analyst Manager)
- 5 separate MongoDB stub collections seeded with realistic Utilico account data
- Agent pipeline implemented via Claude API (claude-sonnet-4-20250514)
- All 7 pipeline steps producing real outputs (not simulated)
- Decision-ready brief rendered in DRI interface
- Approve / reject / exception decision flow with audit trail write
- 3 outputs generated and displayed post-approval
- Analyst Manager health dashboard reading from `analyst_executions`
- Audit trail query interface reading from `audit_trail`

### Out of scope for mock
- OMS real-time event stream — mock uses manual CSR trigger (Trigger B only)
- MDM real read-type flagging — mock uses seeded stub data
- CC&B architectural fix — engineering deliverable, Day 90
- Confidence scoring for proration — Phase 2, Day 60
- Role-tailored output variants for Finance / Regulatory Affairs — Phase 3, Day 90
- Full production deployment across all billing escalation types

---

## Acceptance Criteria

| Criterion | Target |
|---|---|
| Agent context assembly time (steps 2–5) | < 7 minutes |
| Conflict detection time | < 15 seconds |
| Brief generation time | < 60 seconds |
| DRI decision time | < 5 minutes |
| Audit trail completeness | 100% of outputs cite sources |
| Regulatory submission consistency | > 98% |
| First coherent stakeholder update | < 24 hours from escalation opened |
| Billing error recurrence rate (post architectural fix) | < 3% |
| First-contact resolution rate | > 78% |
| CSR handle time | 3–8 minutes |
| CSR trust score (post-pilot) | > 7/10 |
| Regulatory fines in first full quarter | 0 |
| Revenue at risk per dispute | < $150 |
| MongoDB collections | 10 (6 stubs + 1 transactional + 3 operational) |
| Pipeline steps stored per escalation | 7 (all embedded in escalations document) |
| UI roles | 3 (CSR · DRI · Analyst Manager) |

---

*Version 2.0 — Accenture · Utilico Energy Engagement · June 2026*
*Supersedes v1.0 extracted from the case study problem statement.*