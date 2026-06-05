"""
Seed script — loads mock data from database/mock_data.json into the in-memory DB.
To add more data: edit mock_data.json, then hit GET /seed to reload.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

MOCK_DATA_PATH = Path(__file__).parent / "mock_data.json"

COLLECTION_NAMES = [
    "accounts", "ccb_stubs", "mdm_stubs", "oms_stubs", "crm_stubs",
    "gl_stubs", "escalations", "audit_trail", "analyst_executions", "users",
]

NOW = datetime(2024, 12, 1, 0, 0, 0, tzinfo=timezone.utc)


def _parse_dates(obj):
    """Recursively convert ISO date strings to UTC datetime objects."""
    if isinstance(obj, dict):
        return {k: _parse_dates(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_parse_dates(i) for i in obj]
    if isinstance(obj, str):
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f"):
            try:
                return datetime.strptime(obj, fmt).replace(tzinfo=timezone.utc)
            except ValueError:
                pass
    return obj


def _build_mdm_reads(cfg: dict) -> list[dict]:
    """Generate MDM reads from _mdm_config block."""
    reads = []
    base = datetime.fromisoformat(cfg["start_date"])
    kwh = cfg["kwh_per_day"]
    basis = cfg.get("estimation_basis")
    for i in range(cfg["actual_days"]):
        reads.append({"date": (base + timedelta(days=i)).strftime("%Y-%m-%d"), "kwh": kwh, "read_type": "actual", "estimation_basis": None})
    for i in range(cfg["estimated_days"]):
        reads.append({"date": (base + timedelta(days=cfg["actual_days"] + i)).strftime("%Y-%m-%d"), "kwh": kwh, "read_type": "estimated", "estimation_basis": basis})
    return reads


def _load_mock_data() -> dict:
    with open(MOCK_DATA_PATH, encoding="utf-8") as f:
        raw = json.load(f)

    data = {}

    data["accounts"] = [_parse_dates(a) for a in raw["accounts"]]
    data["users"] = [_parse_dates(u) for u in raw["users"]]
    data["ccb_stubs"] = [_parse_dates({**s, "seeded_at": NOW}) for s in raw["ccb_stubs"]]
    data["oms_stubs"] = [_parse_dates({**s, "seeded_at": NOW}) for s in raw["oms_stubs"]]
    data["crm_stubs"] = [_parse_dates({**s, "seeded_at": NOW}) for s in raw["crm_stubs"]]
    data["gl_stubs"] = [_parse_dates({**s, "seeded_at": NOW}) for s in raw["gl_stubs"]]

    # MDM: expand _mdm_config into reads + period_summary
    mdm_stubs = []
    for s in raw["mdm_stubs"]:
        cfg = s.pop("_mdm_config", None)
        stub = dict(s)
        if cfg:
            reads = _build_mdm_reads(cfg)
            actual_kwh = sum(r["kwh"] for r in reads if r["read_type"] == "actual")
            est_kwh = sum(r["kwh"] for r in reads if r["read_type"] == "estimated")
            est_days = cfg["estimated_days"]
            stub["reads"] = reads
            stub["period_summary"] = {"total_actual_kwh": actual_kwh, "total_estimated_kwh": est_kwh, "estimated_days": est_days}
        stub["seeded_at"] = NOW
        mdm_stubs.append(stub)
    data["mdm_stubs"] = mdm_stubs

    # Optional pre-seeded escalations (DRI queue / ticket history demo data)
    data["escalations"] = [_parse_dates(e) for e in raw.get("escalations", [])]

    # Optional pre-seeded analyst executions (SUP tactical-ops demo data)
    data["analyst_executions"] = [_parse_dates(e) for e in raw.get("analyst_executions", [])]

    # Audit trail is generated deterministically from the executions so every
    # execution drill-down and the Full Audit Log are populated and consistent.
    data["audit_trail"] = _build_audit_trail(data["analyst_executions"])

    return data


# Conflict index → (id, system that owns the breached fact) — matches FR-04 invariants.
_CONFLICT_SYS = {1: ("C1", "oms"), 2: ("C2", "mdm"), 3: ("C3", "crm"), 4: ("C4", "gl")}

_INGEST_FACTS = [
    ("ccb", "bill.total_amount", "Full-cycle bill issued — ${amt}"),
    ("mdm", "reads.estimated_days", "{est} estimated read day(s) in period"),
    ("oms", "disconnect.confirmed_at", "Disconnect work order {dc}"),
    ("crm", "complaint.status", "Customer complaint logged — billing dispute"),
    ("gl", "revenue.recognition", "Revenue entry posted for billing period"),
]


def _build_audit_trail(executions: list[dict]) -> list[dict]:
    """Generate immutable audit entries (FR-09) for each seeded execution."""
    entries: list[dict] = []

    for ex in executions:
        esc = ex["escalation_id"]
        acct = ex["account_id"]
        stage = ex.get("pipeline_stage", 7 if ex.get("overall_status") == "complete" else 2)
        nconf = ex.get("conflicts_detected", 0)
        t0 = ex["created_at"]
        if not isinstance(t0, datetime):
            t0 = NOW
        offset = [0]  # minutes, mutable for closure

        def add(step, name, claim, system, field, value, actor="analyst_agent"):
            offset[0] += 1
            entries.append({
                "escalation_id": esc,
                "pipeline_step": step,
                "step_name": name,
                "claim_type": claim,
                "source_system": system,
                "field": field,
                "value": value,
                "extracted_at": None,
                "recorded_at": t0 + timedelta(minutes=offset[0]),
                "actor": actor,
                "immutable": True,
            })

        # Step 1 — Trigger
        if stage >= 1:
            add(1, "trigger", "system_fact", "system", "escalation_opened",
                f"Escalation {esc} opened for account {acct} ({ex.get('trigger_type', 'manual_csr')})")

        # Step 2 — Parallel ingestion across all 5 systems
        if stage >= 2:
            for system, field, tmpl in _INGEST_FACTS:
                value = tmpl.format(
                    amt="756.00", est=nconf * 3 if nconf else 0,
                    dc="confirmed mid-cycle" if nconf else "none on record",
                )
                add(2, "ingestion", "system_fact", system, field, value)

        # Step 3 — Reconciliation
        if stage >= 3:
            add(3, "reconciliation", "system_fact", "system", "timeline",
                "Cross-system billing timeline assembled; no system treated as authoritative (BR-02)")

        # Step 4 — Conflict detection
        if stage >= 4:
            if nconf == 0:
                add(4, "conflict_detection", "system_fact", "system", "conflicts",
                    "0 conflicts — all 4 invariants clear")
            else:
                for i in range(1, nconf + 1):
                    cid, csys = _CONFLICT_SYS[i]
                    add(4, "conflict_detection", "conflict", csys, cid,
                        f"{cid} invariant breached — flagged against {csys.upper()} evidence")

        # Step 5 — Brief generation
        if stage >= 5:
            add(5, "brief_generation", "system_fact", "analyst_agent", "citation_coverage",
                f"Brief generated · citation coverage {int(ex.get('citation_coverage', 1.0) * 100)}%")
            for i in range(1, nconf + 1):
                cid, csys = _CONFLICT_SYS[i]
                add(5, "brief_generation", "recommendation", csys, cid,
                    f"Recommended remediation for {cid} (cited {csys.upper()})")

        # Step 6 — DRI decision
        if stage >= 6:
            add(6, "dri_decision", "dri_decision", "dri", "decision",
                "APPROVED by USR-DRI-001", actor="USR-DRI-001")

        # Step 7 — Output dispatch
        if stage >= 7:
            add(7, "output_dispatch", "output_dispatch", "system", "outputs_dispatched",
                "3 outputs dispatched: customer summary, executive brief, engineering handoff")

    return entries


async def seed_all(db=None) -> None:
    from database.connection import get_database
    if db is None:
        db = get_database()

    print("[SEED] Loading mock_data.json...")
    data = _load_mock_data()

    print("[SEED] Recreating collections...")
    for name in COLLECTION_NAMES:
        await db.drop_collection(name)
        await db.create_collection(name)

    # Insert
    for col in ["accounts", "ccb_stubs", "mdm_stubs", "oms_stubs", "crm_stubs", "gl_stubs", "users"]:
        await db[col].insert_many(data[col])
        print(f"[SEED] {col}: {len(data[col])} documents inserted")

    mock_escalations = data.get("escalations", [])
    if mock_escalations:
        await db["escalations"].insert_many(mock_escalations)
    print(f"[SEED] escalations: {len(mock_escalations)} mock documents inserted")

    mock_executions = data.get("analyst_executions", [])
    if mock_executions:
        await db["analyst_executions"].insert_many(mock_executions)
    print(f"[SEED] analyst_executions: {len(mock_executions)} mock documents inserted")

    mock_audit = data.get("audit_trail", [])
    if mock_audit:
        await db["audit_trail"].insert_many(mock_audit)
    print(f"[SEED] audit_trail: {len(mock_audit)} entries generated from executions")

    # Indexes
    await db["accounts"].create_index("account_id", unique=True)
    for col in ["ccb_stubs", "mdm_stubs", "oms_stubs", "crm_stubs", "gl_stubs"]:
        await db[col].create_index("account_id", unique=True)
    await db["escalations"].create_index("escalation_id", unique=True)
    await db["escalations"].create_index([("account_id", 1), ("status", 1), ("dri_id", 1)])
    await db["audit_trail"].create_index([("escalation_id", 1), ("pipeline_step", 1)])
    await db["audit_trail"].create_index("recorded_at")
    await db["analyst_executions"].create_index("execution_id", unique=True)
    await db["analyst_executions"].create_index("escalation_id")
    await db["users"].create_index("user_id", unique=True)
    await db["users"].create_index("role")
    print("[SEED] Indexes created.")
    print("[SEED] Seed complete.")
