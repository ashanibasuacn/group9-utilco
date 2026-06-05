"""
Step 2 — Data Ingestion
Fetches all 5 stub collections in parallel using asyncio.gather.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorDatabase

from models.audit import AuditClaimType


async def _fetch_stub(db: AsyncIOMotorDatabase, collection: str, account_id: str) -> dict | None:
    doc = await db[collection].find_one({"account_id": account_id}, {"_id": 0})
    return doc


async def execute(
    db: AsyncIOMotorDatabase,
    escalation_id: str,
    account_id: str,
) -> dict:
    """
    Parallel ingestion of all 5 stub sources.
    Returns ingestion data dict with keys: ccb, mdm, oms, crm, gl.
    """
    start_ts = datetime.now(timezone.utc)

    ccb_doc, mdm_doc, oms_doc, crm_doc, gl_doc = await asyncio.gather(
        _fetch_stub(db, "ccb_stubs", account_id),
        _fetch_stub(db, "mdm_stubs", account_id),
        _fetch_stub(db, "oms_stubs", account_id),
        _fetch_stub(db, "crm_stubs", account_id),
        _fetch_stub(db, "gl_stubs", account_id),
    )

    extracted_at = datetime.now(timezone.utc)
    duration_ms = int((extracted_at - start_ts).total_seconds() * 1000)

    def _wrap(doc: dict | None) -> dict:
        return {"extracted_at": extracted_at, "snapshot": doc or {}}

    ingestion_data = {
        "ccb": _wrap(ccb_doc),
        "mdm": _wrap(mdm_doc),
        "oms": _wrap(oms_doc),
        "crm": _wrap(crm_doc),
        "gl": _wrap(gl_doc),
    }

    # Build audit entries
    now = datetime.now(timezone.utc)
    audit_entries = []

    # CC&B audit
    if ccb_doc:
        bp = ccb_doc.get("billing_period", {})
        bill = ccb_doc.get("bill", {})
        for field, value in [
            ("billing_period.start", str(bp.get("start", ""))),
            ("billing_period.end", str(bp.get("end", ""))),
            ("bill.generated_at", str(bill.get("generated_at", ""))),
            ("bill.total_amount", str(bill.get("total_amount", ""))),
        ]:
            audit_entries.append({
                "escalation_id": escalation_id,
                "pipeline_step": 2,
                "step_name": "ingestion",
                "claim_type": AuditClaimType.system_fact.value,
                "source_system": "ccb",
                "field": field,
                "value": value,
                "extracted_at": extracted_at,
                "recorded_at": now,
                "actor": "analyst_agent",
                "immutable": True,
            })

    # MDM audit
    if mdm_doc:
        ps = mdm_doc.get("period_summary", {})
        for field, value in [
            ("period_summary.total_estimated_kwh", str(ps.get("total_estimated_kwh", ""))),
            ("period_summary.estimated_days", str(ps.get("estimated_days", ""))),
        ]:
            audit_entries.append({
                "escalation_id": escalation_id,
                "pipeline_step": 2,
                "step_name": "ingestion",
                "claim_type": AuditClaimType.system_fact.value,
                "source_system": "mdm",
                "field": field,
                "value": value,
                "extracted_at": extracted_at,
                "recorded_at": now,
                "actor": "analyst_agent",
                "immutable": True,
            })

    # OMS audit
    if oms_doc:
        disconnect_wo = next(
            (wo for wo in oms_doc.get("work_orders", []) if wo.get("type") == "disconnect"),
            None,
        )
        if disconnect_wo:
            for field, value in [
                ("work_order.completed_at", str(disconnect_wo.get("completed_at", ""))),
                ("work_order.type", str(disconnect_wo.get("type", ""))),
            ]:
                audit_entries.append({
                    "escalation_id": escalation_id,
                    "pipeline_step": 2,
                    "step_name": "ingestion",
                    "claim_type": AuditClaimType.system_fact.value,
                    "source_system": "oms",
                    "field": field,
                    "value": value,
                    "extracted_at": extracted_at,
                    "recorded_at": now,
                    "actor": "analyst_agent",
                    "immutable": True,
                })

    # CRM audit
    if crm_doc:
        complaints = crm_doc.get("complaints", [])
        crm_fields = [("billing_hold", str(crm_doc.get("billing_hold", "")))]
        if complaints:
            crm_fields.append(("complaints[0].status", str(complaints[0].get("status", ""))))
            crm_fields.append(("complaints[0].regulatory_dispute", str(complaints[0].get("regulatory_dispute", ""))))
        for field, value in crm_fields:
            audit_entries.append({
                "escalation_id": escalation_id,
                "pipeline_step": 2,
                "step_name": "ingestion",
                "claim_type": AuditClaimType.system_fact.value,
                "source_system": "crm",
                "field": field,
                "value": value,
                "extracted_at": extracted_at,
                "recorded_at": now,
                "actor": "analyst_agent",
                "immutable": True,
            })

    # GL audit
    if gl_doc:
        entries = gl_doc.get("revenue_entries", [])
        if entries:
            for field, value in [
                ("revenue_entries[0].status", str(entries[0].get("status", ""))),
                ("revenue_entries[0].amount", str(entries[0].get("amount", ""))),
            ]:
                audit_entries.append({
                    "escalation_id": escalation_id,
                    "pipeline_step": 2,
                    "step_name": "ingestion",
                    "claim_type": AuditClaimType.system_fact.value,
                    "source_system": "gl",
                    "field": field,
                    "value": value,
                    "extracted_at": extracted_at,
                    "recorded_at": now,
                    "actor": "analyst_agent",
                    "immutable": True,
                })

    if audit_entries:
        await db["audit_trail"].insert_many(audit_entries)

    # Build IngestionStep document and update escalation
    ingestion_step_doc = {
        "completed_at": extracted_at,
        "duration_ms": duration_ms,
        "sources": {
            k: {"extracted_at": v["extracted_at"], "snapshot": v["snapshot"]}
            for k, v in ingestion_data.items()
        },
    }

    await db["escalations"].update_one(
        {"escalation_id": escalation_id},
        {
            "$set": {
                "pipeline.step_2_ingestion": ingestion_step_doc,
                "updated_at": now,
            }
        },
    )

    print(f"[STEP2] Ingestion complete for {escalation_id} in {duration_ms}ms")
    return ingestion_data
