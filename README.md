# group9-utilco — Utilico Energy Billing Reconciliation Agent (Mock)

A Python mock application that simulates an **AI-driven billing reconciliation agent**
for Utilico Energy. It reconciles a customer's billing situation across five
independent enterprise systems (CC&B, MDM, OMS, CRM, GL), detects post-disconnect
billing conflicts, generates an AI brief, gates every output behind a human DRI
approval step, and produces a regulator-grade audit trail.

> **North star:** a billing dispute that took 6–8 hours across 6–9 teams should take
> one person under 8 minutes, with a paper trail that holds up in front of a regulator.

The application lives in [`utilico-agent/`](utilico-agent/). See its
[README](utilico-agent/README.md) for full setup, run, and architecture details.

## Quick start

```bash
cd utilico-agent

# 1. (Optional) configure an LLM provider for the AI brief step
cp .env.example .env          # then edit .env

# 2. Install dependencies
pip install -r requirements.txt

# 3a. Run the web app  ............ http://localhost:8000
uvicorn main:app --reload

#  — or —

# 3b. Run the one-command terminal demo (rich UI)
python demo.py
```

There is **no external database to install** — the app uses an in-memory
`mongomock` store that auto-seeds three test accounts on startup.

## What you get

- **Web UI** (`/`) — role-based views for CSR, DRI, and Analyst Manager.
- **Terminal demo** (`python demo.py`) — a scripted, colour-rich end-to-end run
  of account `UTL-00421937` showing all four conflicts and the DRI gate.
- **REST API + Swagger** (`/docs`) — CSR, DRI, and Analyst Manager endpoints.
- **Audit trail** — every pipeline step records a source-cited entry.

## Repository layout

| Path | Contents |
|------|----------|
| [`utilico-agent/`](utilico-agent/) | The mock application (FastAPI + rich terminal demo) |
| [`req/`](req/) | Requirements, north-star, and architecture/journey docs |
| `CLAUDE.md` | Project objective, principles, and implementation rules |
