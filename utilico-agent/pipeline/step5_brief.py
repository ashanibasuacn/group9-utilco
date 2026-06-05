"""
Step 5 — AI Brief Generation
Calls analyst_agent with structured context; validates citation_coverage == 1.0.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorDatabase

from agent.analyst import get_analyst_agent
from models.audit import AuditClaimType
from models.escalation import BriefStep, Conflict, ReconciliationStep


def _build_prompt(
    account_id: str,
    account_doc: dict,
    ingestion_data: dict,
    reconciliation: ReconciliationStep,
    conflicts: list[Conflict],
) -> str:
    ccb = ingestion_data.get("ccb", {}).get("snapshot", {})
    mdm = ingestion_data.get("mdm", {}).get("snapshot", {})
    oms = ingestion_data.get("oms", {}).get("snapshot", {})
    crm = ingestion_data.get("crm", {}).get("snapshot", {})
    gl = ingestion_data.get("gl", {}).get("snapshot", {})

    bp = ccb.get("billing_period", {})
    bill = ccb.get("bill", {})
    mdm_ps = mdm.get("period_summary", {})
    oms_wos = oms.get("work_orders", [])
    disconnect_wo = next((wo for wo in oms_wos if wo.get("type") == "disconnect"), None)
    crm_complaints = crm.get("complaints", [])
    gl_entries = gl.get("revenue_entries", [])

    summary = reconciliation.summary

    conflict_lines = []
    for c in conflicts:
        status = "DETECTED" if c.detected else "NOT DETECTED"
        line = f"  {c.id} [{status}] systems={c.systems} invariant={c.invariant}"
        if c.evidence:
            line += f"\n    Evidence: {c.evidence}"
        conflict_lines.append(line)

    prompt = f"""
## Escalation Context

**Account:** {account_id} — {account_doc.get('customer_name', 'Unknown')} ({account_doc.get('account_type', 'unknown')} / {account_doc.get('tariff_code', '')})

### CC&B Data
- Billing period: {bp.get('start')} to {bp.get('end')} ({bp.get('cycle_days')} days)
- Bill total: {bill.get('total_kwh')} kWh / ${bill.get('total_amount')} USD
- Bill status: {bill.get('status')}
- disconnect_suppression: {ccb.get('billing_rules', {}).get('disconnect_suppression')}
- proration_enabled: {ccb.get('billing_rules', {}).get('proration_enabled')}

### MDM Data
- Total actual kWh: {mdm_ps.get('total_actual_kwh')}
- Total estimated kWh: {mdm_ps.get('total_estimated_kwh')}
- Estimated days: {mdm_ps.get('estimated_days')}

### OMS Data
- Disconnect work order: {disconnect_wo.get('work_order_id') if disconnect_wo else 'None'}
- Disconnect completed at: {disconnect_wo.get('completed_at') if disconnect_wo else 'None'}
- Technician confirmed: {disconnect_wo.get('technician', {}).get('confirmed') if disconnect_wo else 'N/A'}

### CRM Data
- Billing hold: {crm.get('billing_hold')}
- Complaints: {len(crm_complaints)} complaint(s)
{chr(10).join(f"  - {c.get('complaint_id')}: {c.get('type')} [{c.get('status')}] regulatory={c.get('regulatory_dispute')}" for c in crm_complaints)}

### GL Data
- Revenue entries: {len(gl_entries)}
{chr(10).join(f"  - {e.get('entry_id')}: ${e.get('amount')} [{e.get('status')}] reversal_required={e.get('reversal_required')}" for e in gl_entries)}

### Reconciliation Summary
- Pre-disconnect days: {summary.pre_disconnect_days if summary else 0}
- Disconnect day: {summary.disconnect_day if summary else 0}
- Post-disconnect days: {summary.post_disconnect_days if summary else 0}
- Estimated read days (post-disconnect): {summary.estimated_read_days_post_disconnect if summary else 0}

### Conflict Manifest
{chr(10).join(conflict_lines)}

---
Generate the BriefResult JSON.
Only produce recommendations for conflicts with DETECTED status.
citation_coverage must be 1.0 — cite [CC&B], [OMS], [MDM], [CRM], [GL] in brief_text for every factual claim.
"""
    return prompt.strip()


async def execute(
    db: AsyncIOMotorDatabase,
    escalation_id: str,
    account_id: str,
    ingestion_data: dict,
    reconciliation: ReconciliationStep,
    conflicts: list[Conflict],
) -> BriefStep:
    start_ts = datetime.now(timezone.utc)

    # Fetch account doc for customer name/type
    account_doc = await db["accounts"].find_one({"account_id": account_id}, {"_id": 0}) or {}

    prompt = _build_prompt(account_id, account_doc, ingestion_data, reconciliation, conflicts)

    # Run analyst agent (lazy-initialised to avoid requiring API key at import)
    result = await get_analyst_agent().run(prompt)
    brief_result = result.output

    # Validate citation_coverage
    if brief_result.citation_coverage != 1.0:
        raise ValueError(
            f"[STEP5] citation_coverage must be 1.0, got {brief_result.citation_coverage} for {escalation_id}"
        )

    # Validate all detected conflicts have a recommendation
    detected_ids = {c.id for c in conflicts if c.detected}
    recommended_ids = {r.conflict_id for r in brief_result.recommendations}
    missing = detected_ids - recommended_ids
    if missing:
        raise ValueError(
            f"[STEP5] Missing recommendations for detected conflicts: {missing} in {escalation_id}"
        )

    completed_at = datetime.now(timezone.utc)
    duration_ms = int((completed_at - start_ts).total_seconds() * 1000)

    brief_step = BriefStep(
        completed_at=completed_at,
        duration_ms=duration_ms,
        recommendations=brief_result.recommendations,
        brief_text=brief_result.brief_text,
        confidence_signal=brief_result.confidence_signal,
        citation_coverage=brief_result.citation_coverage,
    )

    now = datetime.now(timezone.utc)
    audit_entries = []

    # Audit: one entry per recommendation
    for rec in brief_result.recommendations:
        audit_entries.append({
            "escalation_id": escalation_id,
            "pipeline_step": 5,
            "step_name": "brief_generation",
            "claim_type": AuditClaimType.recommendation.value,
            "source_system": rec.cited_system,
            "field": rec.conflict_id,
            "value": rec.action,
            "extracted_at": None,
            "recorded_at": now,
            "actor": "analyst_agent",
            "immutable": True,
        })

    # Audit: brief generated
    audit_entries.append({
        "escalation_id": escalation_id,
        "pipeline_step": 5,
        "step_name": "brief_generation",
        "claim_type": AuditClaimType.system_fact.value,
        "source_system": "agent",
        "field": "brief_generated",
        "value": f"citation_coverage={brief_result.citation_coverage}, recommendations={len(brief_result.recommendations)}",
        "extracted_at": None,
        "recorded_at": now,
        "actor": "analyst_agent",
        "immutable": True,
    })

    if audit_entries:
        await db["audit_trail"].insert_many(audit_entries)

    # Update escalation: set brief + status -> awaiting_dri
    await db["escalations"].update_one(
        {"escalation_id": escalation_id},
        {
            "$set": {
                "pipeline.step_5_brief": brief_step.model_dump(),
                "status": "awaiting_dri",
                "updated_at": now,
            }
        },
    )

    print(
        f"[STEP5] Brief generated for {escalation_id}: "
        f"{len(brief_result.recommendations)} recommendations, "
        f"citation_coverage={brief_result.citation_coverage}, "
        f"duration={duration_ms}ms"
    )
    return brief_step
