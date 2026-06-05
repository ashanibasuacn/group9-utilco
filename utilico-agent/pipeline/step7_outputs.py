"""
Step 7 — Output Dispatch
Generates all 3 structured outputs from the brief evidence base (BR-08).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from motor.motor_asyncio import AsyncIOMotorDatabase

from models.audit import AuditClaimType
from models.escalation import BriefStep, Conflict, OutputContent, OutputsStep


def _next_business_day(dt: datetime, days: int) -> str:
    """Advance dt by `days` business days."""
    current = dt
    added = 0
    while added < days:
        current = current + timedelta(days=1)
        if current.weekday() < 5:  # Mon-Fri
            added += 1
    return current.strftime("%Y-%m-%d")


async def execute(
    db: AsyncIOMotorDatabase,
    escalation_id: str,
    brief: BriefStep,
    account: dict,
    conflicts: list[Conflict],
) -> OutputsStep:
    now = datetime.now(timezone.utc)
    detected = [c for c in conflicts if c.detected]

    # -----------------------------------------------------------------------
    # Customer Summary (plain language)
    # -----------------------------------------------------------------------
    action_items = []
    for rec in brief.recommendations:
        action_items.append(rec.action)

    c4_detected = any(c.id == "C4" and c.detected for c in conflicts)
    regulatory = any(c.id in ("C1", "C4") and c.detected for c in conflicts)

    customer_summary_content = {
        "what_we_found": (
            f"We identified {len(detected)} billing discrepancy(ies) on your account "
            f"({account.get('account_id')}) for the recent billing cycle. "
            f"A service disconnection event was cross-referenced against your meter reads "
            f"and billing records."
        ),
        "what_we_done": (
            "Our reconciliation system has automatically flagged the affected charges "
            "and escalated to a Designated Review Individual for approval. "
            f"Recommended actions: {'; '.join(action_items) if action_items else 'No adjustments required.'}."
        ),
        "what_happens_next": (
            "Once your DRI approves the resolution, any applicable credits or adjustments "
            "will be applied to your account within 3-5 business days. "
            "You will receive a revised statement."
        ),
        "next_update_date": _next_business_day(now, 3),
    }

    customer_summary = OutputContent(
        format="json",
        audience="customer",
        content=customer_summary_content,
    )

    # -----------------------------------------------------------------------
    # Executive Brief
    # -----------------------------------------------------------------------
    financial_impact = sum(
        r.get("amount", 0)
        for source in ["ccb"]
        for r in [account]
        for _ in [None]
    )
    # Use brief text for situation
    findings_list = [
        f"{c.id}: {c.invariant} — {c.evidence}" for c in detected
    ]
    next_steps = [rec.action for rec in brief.recommendations]
    if c4_detected:
        next_steps.append("Generate credit note and flag GL entry for reversal [GL]")

    executive_brief_content = {
        "situation": brief.brief_text or f"Billing reconciliation escalation for account {account.get('account_id')}.",
        "financial_impact": (
            f"Potential billing adjustment required. "
            f"{len(detected)} conflict(s) detected across billing systems."
        ),
        "findings": findings_list,
        "next_steps": next_steps,
        "gl_reversal_note": (
            "GL revenue entry flagged for reversal pending regulatory filing."
            if c4_detected
            else None
        ),
        "regulatory_exposure": (
            "Regulatory dispute filed. Tier-2 regulatory review may apply."
            if regulatory
            else "No regulatory exposure identified."
        ),
    }

    executive_brief = OutputContent(
        format="json",
        audience="executive",
        content=executive_brief_content,
    )

    # -----------------------------------------------------------------------
    # Engineering Handoff (Jira story format)
    # -----------------------------------------------------------------------
    linked_systems = list({sys for c in detected for sys in c.systems})
    linked_systems.sort()

    acceptance_criteria = [
        f"AC1: Post-disconnect billing suppression applied for {account.get('account_id')} — verified in CC&B",
        f"AC2: MDM estimated reads zeroed for all post-disconnect days — verified in MDM system",
        "AC3: CRM billing_hold flag propagated to CC&B billing rules — verified in CRM",
        "AC4: GL revenue entry flagged for reversal; credit note generated — verified in GL",
        "AC5: Audit trail complete with ≥1 entry per pipeline step — verified in audit_trail collection",
        "AC6: All 3 output documents dispatched and stored in escalation.pipeline.step_7_outputs",
    ]

    engineering_handoff_content = {
        "priority": "P1",
        "title": (
            f"[{account.get('account_id')}] Billing Reconciliation — "
            f"{len(detected)} conflict(s) detected: {', '.join(c.id for c in detected)}"
        ),
        "linked_systems": linked_systems,
        "description": brief.brief_text or "See escalation for full context.",
        "acceptance_criteria": acceptance_criteria[:6],
        "escalation_id": escalation_id,
        "dri_approved": True,
    }

    engineering_handoff = OutputContent(
        format="jira_story",
        audience="engineering",
        content=engineering_handoff_content,
    )

    drafted_at = datetime.now(timezone.utc)

    # Outputs are generated as DRAFTS (review_status defaults to "pending_review").
    # dispatched_at stays None until a CSR reviews/approves all 3 (see csr review route).
    outputs_step = OutputsStep(
        dispatched_at=None,
        customer_summary=customer_summary,
        executive_brief=executive_brief,
        engineering_handoff=engineering_handoff,
    )

    # Audit
    audit_entry = {
        "escalation_id": escalation_id,
        "pipeline_step": 7,
        "step_name": "output_generation",
        "claim_type": AuditClaimType.output_dispatch.value,
        "source_system": "system",
        "field": "outputs_drafted",
        "value": "3 drafts pending CSR review",
        "extracted_at": None,
        "recorded_at": drafted_at,
        "actor": "analyst_agent",
        "immutable": True,
    }
    await db["audit_trail"].insert_one(audit_entry)

    # Update escalation: step_7_outputs + status=awaiting_output_review.
    # The CSR review gate (per-output approve) advances it to resolved.
    await db["escalations"].update_one(
        {"escalation_id": escalation_id},
        {
            "$set": {
                "pipeline.step_7_outputs": outputs_step.model_dump(),
                "status": "awaiting_output_review",
                "updated_at": drafted_at,
            }
        },
    )

    print(f"[STEP7] 3 output drafts generated for {escalation_id}. Status -> awaiting_output_review.")
    return outputs_step
