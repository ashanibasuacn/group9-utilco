# Utilico Energy — Billing Reconciliation Agent Mock

A mock AI agent that reconciles a customer's billing situation across five enterprise
systems (CC&B, MDM, OMS, CRM, GL), detects post-disconnect billing conflicts, drafts an
AI brief, gates every output behind a human DRI approval, and writes a fully cited audit
trail.

## Prerequisites

- Python 3.10+
- **No external database** — the app runs on an in-memory `mongomock` store
  (see [database/connection.py](database/connection.py)). Nothing to install or run;
  data is reseeded on every startup and lost on shutdown.

## Setup

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. (Optional) configure an LLM provider for the AI brief (step 5)
cp .env.example .env
# Edit .env — see "LLM configuration" below.
```

> The pipeline runs end-to-end **without** an LLM key — steps 1–4, 6, and 7 are pure
> Python. Only the **AI brief (step 5)** calls a model; without valid credentials that
> step falls back to a stub/empty brief but the run still completes.

## How to run

### Option A — Web application

```bash
uvicorn main:app --reload
```

Open **http://localhost:8000**. On boot the app initialises the in-memory store and
auto-seeds all 10 collections (3 test accounts, 5 system stubs, users, etc.).

### Option B — One-command terminal demo

```bash
python demo.py
```

A scripted, colour-rich (`rich`) walkthrough of account **UTL-00421937**
(Acme Manufacturing) where all four conflicts fire. It steps through the full pipeline
and pauses at the DRI gate for an approve/reject decision.

## What to expect

### Web UI (`/`)

You land on a split-panel **login page** — pick one of three role cards (Sarah Chen /
James Okafor / Priya Nair), which auto-fills credentials, then **Sign in**. Each role
opens its own interface (Accenture-style, white background):

| Tab | Persona | What you do |
|-----|---------|-------------|
| **CSR** | Sarah Chen (`USR-CSR-112`) | Raise an escalation for an account and track its status. Raising one kicks off the reconciliation pipeline in the background. |
| **DRI** | James Okafor (`USR-DRI-001`) | Review the AI brief + detected conflicts in the backlog, then **Approve** or **Reject** (rejection requires a reason). No output dispatches until you decide. |
| **Analyst Manager** | Priya Nair (`USR-AM-001`) | Dashboard metrics, recent executions, and the per-escalation audit trail. |

A typical flow: raise a ticket as CSR on `UTL-00421937` → watch the agent run → switch to
DRI, review the brief showing conflicts **C1–C4** with citations → approve → see the three
structured outputs and a complete 7-step audit trail under Analyst Manager.

### Terminal demo

Sequential panels for each pipeline step, a live progress spinner during ingestion, a
conflicts table (C1–C4 with source systems), the generated brief, an interactive DRI
prompt, and the final dispatched outputs — each line citing its source system.

## Test accounts

| Account       | Customer              | Scenario         | Conflicts       |
|---------------|-----------------------|------------------|-----------------|
| UTL-00421937  | Acme Manufacturing    | Full escalation  | C1, C2, C3, C4  |
| UTL-00389204  | Riverside Commercial  | Partial          | C1, C2          |
| UTL-00371055  | Metro Offices         | Clean            | None            |

## Conflict types

| ID | Systems     | Invariant                        | Trigger                                         |
|----|-------------|----------------------------------|-------------------------------------------------|
| C1 | OMS ↔ CC&B  | full_cycle_post_disconnect       | Full cycle billed after confirmed disconnect    |
| C2 | MDM ↔ OMS   | phantom_consumption              | Estimated reads exist after disconnect          |
| C3 | CRM ↔ CC&B  | billing_hold_not_propagated      | Complaint open but billing_hold=false           |
| C4 | GL ↔ CRM    | revenue_posted_under_dispute     | Revenue posted while CRM complaint is open      |

## Pipeline steps

| Step | Name              | NFR Target | Description                              |
|------|-------------------|------------|------------------------------------------|
| 1    | Trigger           | —          | Create escalation + execution documents  |
| 2    | Ingestion         | 420s       | Parallel fetch all 5 stub systems        |
| 3    | Reconciliation    | 420s       | Classify billing days vs disconnect date |
| 4    | Conflict Detection| 15s        | Pure Python rule checks, no LLM          |
| 5    | AI Brief          | 60s        | Claude generates recommendations + brief |
| 6    | DRI Decision      | 300s       | Human approves / rejects / exception     |
| 7    | Output Dispatch   | —          | 3 structured outputs generated           |

## LLM configuration

Only the **AI brief (step 5)** uses a model. Configure it in `.env`
(copied from [.env.example](.env.example)); see [config.py](config.py) for defaults.

```bash
LLM_PROVIDER=anthropic   # "anthropic" (direct API) or "bedrock" (AWS)

# When LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...

# When LLM_PROVIDER=bedrock (ap-south-1 requires an apac.* inference-profile ID)
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_DEFAULT_REGION=ap-south-1
BEDROCK_MODEL_ID=apac.anthropic.claude-sonnet-4-20250514-v1:0
```

Leaving credentials unset still lets the pipeline complete — step 5 just produces an
empty/stub brief.

## API docs

Interactive Swagger UI: http://localhost:8000/docs

### CSR endpoints
```
POST /csr/tickets                          Raise escalation (background)
GET  /csr/tickets/{csr_id}                 List CSR's escalations
GET  /csr/tickets/detail/{escalation_id}   Full escalation document
```

### DRI endpoints
```
GET  /dri/queue/{dri_id}                   Queue (awaiting_dri first)
GET  /dri/brief/{escalation_id}            Brief + conflicts for review
POST /dri/decision                         Record decision
```

### Analyst Manager endpoints
```
GET  /analyst-manager/health               Dashboard metrics
GET  /analyst-manager/executions           Recent executions
GET  /analyst-manager/audit-trail/{id}     Per-escalation audit trail
GET  /analyst-manager/audit-trail          Queryable audit trail
```

## Tests

```bash
pytest tests/ -v
```

No database setup is needed — tests run against the same in-memory `mongomock` store as
the app. The suite re-seeds at session start and runs 10 tests:

1. `test_seed_database` — all 10 collections populated
2. `test_step2_ingestion_parallel` — all 5 sources for UTL-00421937
3. `test_step3_reconciliation_full_conflict` — 13 post-disconnect days
4. `test_step4_all_4_conflicts` — C1, C2, C3, C4 detected
5. `test_step4_2_conflicts` — only C1, C2 for UTL-00389204
6. `test_step4_no_conflicts` — 0 conflicts for UTL-00371055
7. `test_step5_citation_coverage` — citation_coverage == 1.0
8. `test_full_pipeline_approved` — end-to-end → resolved
9. `test_full_pipeline_rejected` — DRI reject → rejected
10. `test_audit_trail_completeness` — entries for all 7 steps

### UI tests (Playwright)

`tests/test_ui_playwright.py` exercises the web UI. Install browsers once, then run with
the server up:

```bash
playwright install chromium
uvicorn main:app          # in one terminal
pytest tests/test_ui_playwright.py -v   # in another
```

## Users

| User ID       | Name          | Role             | Email                       |
|---------------|---------------|------------------|-----------------------------|
| USR-CSR-112   | Sarah Chen    | csr              | sarah.chen@utilico.com      |
| USR-DRI-001   | James Okafor  | dri              | james.okafor@utilico.com    |
| USR-AM-001    | Priya Nair    | analyst_manager  | priya.nair@utilico.com      |

## Force reseed

```
GET /seed
```

Drops and recreates all 10 collections with fresh mock data.
