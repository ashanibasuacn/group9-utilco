# Utilico Energy — Billing Reconciliation Agent Mock

## Setup

```bash
# 1. Copy env file and add your Anthropic API key
cp .env.example .env
# Edit .env and set ANTHROPIC_API_KEY=sk-ant-...

# 2. Install dependencies
pip install -r requirements.txt

# 3. Start the API server
uvicorn main:app --reload
```

The server starts at http://localhost:8000. On first boot it pings MongoDB and auto-seeds all 10 collections if empty.

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

Tests require a live MongoDB connection. Set `MONGODB_URI` in `.env`.

The test suite re-seeds the database at session start and runs 10 tests:

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
