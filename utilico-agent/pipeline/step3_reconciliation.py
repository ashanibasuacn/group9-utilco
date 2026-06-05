"""
Step 3 — Reconciliation
Pure Python, no LLM.
Classifies each billing day as pre_disconnect / disconnect_day / post_disconnect.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone, date as date_type

from motor.motor_asyncio import AsyncIOMotorDatabase

from models.audit import AuditClaimType
from models.escalation import DayClassification, ReconciliationStep, ReconciliationSummary


def _parse_date(s: str) -> date_type:
    return datetime.fromisoformat(s.split("T")[0]).date()


def _ensure_date(val) -> date_type | None:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date_type):
        return val
    if isinstance(val, str):
        return _parse_date(val)
    return None


async def execute(
    db: AsyncIOMotorDatabase,
    escalation_id: str,
    ingestion_data: dict,
) -> ReconciliationStep:
    start_ts = datetime.now(timezone.utc)

    oms_snapshot = ingestion_data.get("oms", {}).get("snapshot", {})
    ccb_snapshot = ingestion_data.get("ccb", {}).get("snapshot", {})
    mdm_snapshot = ingestion_data.get("mdm", {}).get("snapshot", {})

    # 1. Extract disconnect timestamp from OMS
    disconnect_timestamp: datetime | None = None
    disconnect_date: date_type | None = None

    work_orders = oms_snapshot.get("work_orders", [])
    completed_disconnects = [
        wo for wo in work_orders
        if wo.get("type") == "disconnect" and wo.get("status") == "completed" and wo.get("completed_at")
    ]
    if completed_disconnects:
        # Most recent
        completed_disconnects.sort(key=lambda wo: str(wo.get("completed_at", "")), reverse=True)
        raw_ts = completed_disconnects[0]["completed_at"]
        if isinstance(raw_ts, datetime):
            disconnect_timestamp = raw_ts
        elif isinstance(raw_ts, str):
            disconnect_timestamp = datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
        if disconnect_timestamp:
            disconnect_date = disconnect_timestamp.date()

    # 2. Extract billing period from CC&B
    billing_period = ccb_snapshot.get("billing_period", {})
    bp_start_str: str = billing_period.get("start", "")
    bp_end_str: str = billing_period.get("end", "")

    period_map: list[DayClassification] = []
    pre_disconnect_days = 0
    disconnect_day_count = 0
    post_disconnect_days = 0
    estimated_read_days_post_disconnect = 0

    if bp_start_str and bp_end_str:
        bp_start = _parse_date(bp_start_str)
        bp_end = _parse_date(bp_end_str)

        # Build MDM lookup: date_str -> read_type
        mdm_reads = mdm_snapshot.get("reads", [])
        mdm_lookup: dict[str, str] = {r["date"]: r["read_type"] for r in mdm_reads}

        current = bp_start
        while current <= bp_end:
            current_str = current.strftime("%Y-%m-%d")
            mdm_read_type = mdm_lookup.get(current_str)

            if disconnect_date is None:
                classification = "pre_disconnect"
                pre_disconnect_days += 1
            elif current < disconnect_date:
                classification = "pre_disconnect"
                pre_disconnect_days += 1
            elif current == disconnect_date:
                classification = "disconnect_day"
                disconnect_day_count += 1
            else:
                classification = "post_disconnect"
                post_disconnect_days += 1
                if mdm_read_type == "estimated":
                    estimated_read_days_post_disconnect += 1

            period_map.append(
                DayClassification(
                    date=current_str,
                    classification=classification,  # type: ignore[arg-type]
                    mdm_read_type=mdm_read_type,  # type: ignore[arg-type]
                )
            )
            current += timedelta(days=1)

    summary = ReconciliationSummary(
        pre_disconnect_days=pre_disconnect_days,
        post_disconnect_days=post_disconnect_days,
        disconnect_day=disconnect_day_count,
        estimated_read_days_post_disconnect=estimated_read_days_post_disconnect,
    )

    completed_at = datetime.now(timezone.utc)
    duration_ms = int((completed_at - start_ts).total_seconds() * 1000)

    recon_step = ReconciliationStep(
        completed_at=completed_at,
        disconnect_timestamp=disconnect_timestamp,
        billing_period={"start": bp_start_str, "end": bp_end_str},
        period_map=period_map,
        summary=summary,
    )

    # Audit entries
    now = datetime.now(timezone.utc)
    audit_entries = [
        {
            "escalation_id": escalation_id,
            "pipeline_step": 3,
            "step_name": "reconciliation",
            "claim_type": AuditClaimType.system_fact.value,
            "source_system": "oms",
            "field": "disconnect_timestamp",
            "value": str(disconnect_timestamp) if disconnect_timestamp else "None",
            "extracted_at": ingestion_data.get("oms", {}).get("extracted_at"),
            "recorded_at": now,
            "actor": "analyst_agent",
            "immutable": True,
        },
        {
            "escalation_id": escalation_id,
            "pipeline_step": 3,
            "step_name": "reconciliation",
            "claim_type": AuditClaimType.system_fact.value,
            "source_system": "ccb",
            "field": "billing_period",
            "value": f"{bp_start_str} to {bp_end_str}",
            "extracted_at": ingestion_data.get("ccb", {}).get("extracted_at"),
            "recorded_at": now,
            "actor": "analyst_agent",
            "immutable": True,
        },
        {
            "escalation_id": escalation_id,
            "pipeline_step": 3,
            "step_name": "reconciliation",
            "claim_type": AuditClaimType.system_fact.value,
            "source_system": "ccb",
            "field": "post_disconnect_days",
            "value": str(post_disconnect_days),
            "extracted_at": ingestion_data.get("ccb", {}).get("extracted_at"),
            "recorded_at": now,
            "actor": "analyst_agent",
            "immutable": True,
        },
        {
            "escalation_id": escalation_id,
            "pipeline_step": 3,
            "step_name": "reconciliation",
            "claim_type": AuditClaimType.system_fact.value,
            "source_system": "mdm",
            "field": "estimated_read_days_post_disconnect",
            "value": str(estimated_read_days_post_disconnect),
            "extracted_at": ingestion_data.get("mdm", {}).get("extracted_at"),
            "recorded_at": now,
            "actor": "analyst_agent",
            "immutable": True,
        },
    ]
    await db["audit_trail"].insert_many(audit_entries)

    # Update escalation
    await db["escalations"].update_one(
        {"escalation_id": escalation_id},
        {
            "$set": {
                "pipeline.step_3_reconciliation": recon_step.model_dump(),
                "updated_at": now,
            }
        },
    )

    print(
        f"[STEP3] Reconciliation complete for {escalation_id}: "
        f"pre={pre_disconnect_days}, post={post_disconnect_days}, "
        f"estimated_post={estimated_read_days_post_disconnect}"
    )
    return recon_step
