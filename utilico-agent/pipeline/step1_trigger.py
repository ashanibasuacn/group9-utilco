"""
Step 1 — Trigger
Creates the escalation and execution documents.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorDatabase

from models.escalation import EscalationStatus, Pipeline, TriggerStep
from models.audit import AuditClaimType

_lock = asyncio.Lock()


async def _next_sequence(db: AsyncIOMotorDatabase) -> int:
    """Return next escalation sequence number (1-based)."""
    count = await db["escalations"].count_documents({})
    return count + 1


async def execute(
    db: AsyncIOMotorDatabase,
    account_id: str,
    csr_id: str,
    trigger_type: str,
    notes: str | None,
) -> tuple[str, str]:
    """
    Create escalation + execution documents.
    Returns (escalation_id, execution_id).
    """
    async with _lock:
        seq = await _next_sequence(db)

    seq_str = str(seq).zfill(4)
    escalation_id = f"ESC-{seq_str}"
    execution_id = f"EX-{seq_str}"

    now = datetime.now(timezone.utc)

    # Resolve DRI from account dri_pool (first active DRI)
    account_doc = await db["accounts"].find_one({"account_id": account_id})
    dri_id: str | None = None
    if account_doc and account_doc.get("dri_pool"):
        for candidate in account_doc["dri_pool"]:
            user_doc = await db["users"].find_one({"user_id": candidate, "active": True, "role": "dri"})
            if user_doc:
                dri_id = candidate
                break

    trigger_step = TriggerStep(
        trigger_type=trigger_type,  # type: ignore[arg-type]
        dispute_type="billing_post_disconnect",
        notes=notes,
        triggered_at=now,
    )

    escalation_doc = {
        "escalation_id": escalation_id,
        "account_id": account_id,
        "status": EscalationStatus.analysing.value,
        "dri_id": dri_id,
        "csr_id": csr_id,
        "opened_at": now,
        "resolved_at": None,
        "pipeline": {
            "step_1_trigger": trigger_step.model_dump(),
            "step_2_ingestion": None,
            "step_3_reconciliation": None,
            "step_4_conflicts": None,
            "step_5_brief": None,
            "step_6_dri": None,
            "step_7_outputs": None,
        },
        "created_at": now,
        "updated_at": now,
    }

    execution_doc = {
        "execution_id": execution_id,
        "escalation_id": escalation_id,
        "account_id": account_id,
        "trigger_type": trigger_type,
        "overall_status": "running",
        "steps": [],
        "total_duration_ms": None,
        "agent_duration_ms": None,
        "conflicts_detected": 0,
        "citation_coverage": 0.0,
        "nfr_breaches": 0,
        "created_at": now,
        "completed_at": None,
    }

    await db["escalations"].insert_one(escalation_doc)
    await db["analyst_executions"].insert_one(execution_doc)

    # Audit: escalation opened
    audit_entry = {
        "escalation_id": escalation_id,
        "pipeline_step": 1,
        "step_name": "trigger",
        "claim_type": AuditClaimType.system_fact.value,
        "source_system": "system",
        "field": "escalation_opened",
        "value": f"Escalation {escalation_id} opened for account {account_id} by {csr_id}",
        "extracted_at": None,
        "recorded_at": now,
        "actor": "analyst_agent",
        "immutable": True,
    }
    await db["audit_trail"].insert_one(audit_entry)

    # Update DRI's assigned escalations list
    if dri_id:
        await db["users"].update_one(
            {"user_id": dri_id},
            {"$addToSet": {"assigned_escalations": escalation_id}},
        )

    print(f"[STEP1] Created {escalation_id} / {execution_id}, DRI={dri_id}")
    return escalation_id, execution_id
