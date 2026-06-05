"""
Step 6 — DRI Decision
Records the human DRI decision and updates escalation status.
"""
from __future__ import annotations

from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorDatabase

from models.audit import AuditClaimType
from models.escalation import DRIStep, EscalationStatus


async def execute(
    db: AsyncIOMotorDatabase,
    escalation_id: str,
    decision: str,
    decided_by: str,
    reason: str | None,
    started_at: datetime,
) -> DRIStep:
    """
    Record DRI decision.
    decision: approved | rejected | exception
    reason is required if decision is rejected or exception.
    """
    if decision in ("rejected", "exception") and not reason:
        raise ValueError(
            f"[STEP6] A reason is required for decision '{decision}' on {escalation_id}"
        )

    decided_at = datetime.now(timezone.utc)
    decision_latency_ms = int((decided_at - started_at).total_seconds() * 1000)

    # Map decision to status
    status_map = {
        "approved": EscalationStatus.approved.value,
        "rejected": EscalationStatus.rejected.value,
        "exception": EscalationStatus.rejected.value,
    }
    new_status = status_map.get(decision, EscalationStatus.rejected.value)

    dri_step = DRIStep(
        decision=decision,  # type: ignore[arg-type]
        decided_at=decided_at,
        decided_by=decided_by,
        reason=reason,
        decision_latency_ms=decision_latency_ms,
    )

    now = datetime.now(timezone.utc)

    # Audit entry
    audit_entry = {
        "escalation_id": escalation_id,
        "pipeline_step": 6,
        "step_name": "dri_decision",
        "claim_type": AuditClaimType.dri_decision.value,
        "source_system": "dri",
        "field": "decision",
        "value": f"{decision}" + (f" — reason: {reason}" if reason else ""),
        "extracted_at": None,
        "recorded_at": now,
        "actor": decided_by,
        "immutable": True,
    }
    await db["audit_trail"].insert_one(audit_entry)

    # Update escalation
    await db["escalations"].update_one(
        {"escalation_id": escalation_id},
        {
            "$set": {
                "pipeline.step_6_dri": dri_step.model_dump(),
                "status": new_status,
                "updated_at": now,
            }
        },
    )

    print(
        f"[STEP6] DRI decision for {escalation_id}: {decision} by {decided_by}, "
        f"latency={decision_latency_ms}ms"
    )
    return dri_step
