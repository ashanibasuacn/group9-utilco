"""
Step 4 — Conflict Detection
Pure Python rule checks, no LLM. Completes in <15 seconds.
"""
from __future__ import annotations

from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorDatabase

from models.audit import AuditClaimType
from models.escalation import Conflict, ConflictStep, ReconciliationStep


async def execute(
    db: AsyncIOMotorDatabase,
    escalation_id: str,
    ingestion_data: dict,
    reconciliation: ReconciliationStep,
) -> list[Conflict]:
    start_ts = datetime.now(timezone.utc)

    ccb_snapshot = ingestion_data.get("ccb", {}).get("snapshot", {})
    mdm_snapshot = ingestion_data.get("mdm", {}).get("snapshot", {})
    oms_snapshot = ingestion_data.get("oms", {}).get("snapshot", {})
    crm_snapshot = ingestion_data.get("crm", {}).get("snapshot", {})
    gl_snapshot = ingestion_data.get("gl", {}).get("snapshot", {})

    summary = reconciliation.summary

    # ---------------------------------------------------------------------------
    # C1: OMS ↔ CC&B — full cycle billed despite post-disconnect days
    # ---------------------------------------------------------------------------
    c1_post_disconnect = summary.post_disconnect_days if summary else 0
    c1_detected = c1_post_disconnect > 0
    c1_billing_rules = ccb_snapshot.get("billing_rules", {})
    c1_evidence = (
        f"OMS confirmed disconnect; CC&B billed full cycle with "
        f"{c1_post_disconnect} post-disconnect days. "
        f"disconnect_suppression={c1_billing_rules.get('disconnect_suppression')}, "
        f"proration_enabled={c1_billing_rules.get('proration_enabled')}"
        if c1_detected
        else None
    )
    c1 = Conflict(
        id="C1",
        systems=["OMS", "CC&B"],
        detected=c1_detected,
        invariant="full_cycle_post_disconnect",
        evidence=c1_evidence,
    )

    # ---------------------------------------------------------------------------
    # C2: MDM ↔ OMS — estimated reads exist after disconnect (phantom consumption)
    # ---------------------------------------------------------------------------
    c2_estimated_post = summary.estimated_read_days_post_disconnect if summary else 0
    c2_detected = c2_estimated_post > 0
    mdm_ps = mdm_snapshot.get("period_summary", {})
    c2_evidence = (
        f"MDM has {c2_estimated_post} estimated read days after OMS-confirmed disconnect. "
        f"estimation_basis=historical_avg; "
        f"total_estimated_kwh={mdm_ps.get('total_estimated_kwh')}"
        if c2_detected
        else None
    )
    c2 = Conflict(
        id="C2",
        systems=["MDM", "OMS"],
        detected=c2_detected,
        invariant="phantom_consumption",
        evidence=c2_evidence,
    )

    # ---------------------------------------------------------------------------
    # C3: CRM ↔ CC&B — active complaint but no billing hold applied
    # ---------------------------------------------------------------------------
    billing_hold = crm_snapshot.get("billing_hold", False)
    complaints = crm_snapshot.get("complaints", [])
    c3_detected = (not billing_hold) and len(complaints) > 0
    c3_evidence = (
        f"CRM has {len(complaints)} open complaint(s) but billing_hold={billing_hold}. "
        f"Complaint IDs: {', '.join(c.get('complaint_id', '') for c in complaints)}"
        if c3_detected
        else None
    )
    c3 = Conflict(
        id="C3",
        systems=["CRM", "CC&B"],
        detected=c3_detected,
        invariant="billing_hold_not_propagated",
        evidence=c3_evidence,
    )

    # ---------------------------------------------------------------------------
    # C4: GL ↔ CRM — revenue posted while complaint is open
    # ---------------------------------------------------------------------------
    gl_entries = gl_snapshot.get("revenue_entries", [])
    gl_posted = any(e.get("status") == "posted" for e in gl_entries)
    open_complaints = [c for c in complaints if c.get("status") == "open"]
    c4_detected = gl_posted and len(open_complaints) > 0
    posted_entries = [e for e in gl_entries if e.get("status") == "posted"]
    c4_evidence = (
        f"GL has {len(posted_entries)} posted revenue entry(ies) "
        f"while CRM has {len(open_complaints)} open complaint(s). "
        f"Posted entry IDs: {', '.join(e.get('entry_id', '') for e in posted_entries)}"
        if c4_detected
        else None
    )
    c4 = Conflict(
        id="C4",
        systems=["GL", "CRM"],
        detected=c4_detected,
        invariant="revenue_posted_under_dispute",
        evidence=c4_evidence,
    )

    conflicts = [c1, c2, c3, c4]
    detected_conflicts = [c for c in conflicts if c.detected]

    # Confidence signal if any snapshot is missing
    missing_sources = [
        src for src in ["ccb", "mdm", "oms", "crm", "gl"]
        if not ingestion_data.get(src, {}).get("snapshot")
    ]
    confidence_signal = (
        f"Data incomplete: missing snapshots for {', '.join(missing_sources)}"
        if missing_sources
        else None
    )

    completed_at = datetime.now(timezone.utc)
    duration_ms = int((completed_at - start_ts).total_seconds() * 1000)

    # Audit: one entry per detected conflict
    now = datetime.now(timezone.utc)
    audit_entries = []
    for conflict in detected_conflicts:
        audit_entries.append({
            "escalation_id": escalation_id,
            "pipeline_step": 4,
            "step_name": "conflict_detection",
            "claim_type": AuditClaimType.conflict.value,
            "source_system": "+".join(conflict.systems),
            "field": conflict.id,
            "value": f"DETECTED: {conflict.invariant} — {conflict.evidence}",
            "extracted_at": None,
            "recorded_at": now,
            "actor": "analyst_agent",
            "immutable": True,
        })

    if audit_entries:
        await db["audit_trail"].insert_many(audit_entries)

    conflict_step_doc = ConflictStep(
        completed_at=completed_at,
        duration_ms=duration_ms,
        conflicts=conflicts,
    )

    update_data: dict = {
        "pipeline.step_4_conflicts": conflict_step_doc.model_dump(),
        "updated_at": now,
    }
    if confidence_signal:
        # Store in step_5_brief.confidence_signal provisionally
        update_data["pipeline.step_5_brief"] = {"confidence_signal": confidence_signal, "citation_coverage": 0.0, "recommendations": []}

    await db["escalations"].update_one(
        {"escalation_id": escalation_id},
        {"$set": update_data},
    )

    print(
        f"[STEP4] Conflict detection complete for {escalation_id}: "
        f"{len(detected_conflicts)}/{len(conflicts)} detected. Duration={duration_ms}ms"
    )
    return conflicts
