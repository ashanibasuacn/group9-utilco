"""
CSR API Routes
POST /csr/tickets        — Raise a billing escalation ticket
GET  /csr/tickets/{csr_id}                    — List CSR's tickets
GET  /csr/tickets/detail/{escalation_id}      — Full escalation document
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, HTTPException

from api.schemas import (
    EscalationSummary,
    OutputReviewRequest,
    OutputReviewResponse,
    RaiseTicketRequest,
    RaiseTicketResponse,
)
from database.connection import get_database
from pipeline.orchestrator import PipelineOrchestrator

router = APIRouter(prefix="/csr", tags=["CSR"])

# Maps the request output_type to the step_7_outputs field key.
OUTPUT_FIELDS = {
    "customer": "customer_summary",
    "executive": "executive_brief",
    "engineering": "engineering_handoff",
}


async def _run_pipeline(account_id: str, csr_id: str, trigger_type: str, notes: str | None) -> None:
    """Background task: runs steps 1-5 of the pipeline."""
    db = get_database()
    orchestrator = PipelineOrchestrator(
        db=db,
        account_id=account_id,
        csr_id=csr_id,
        trigger_type=trigger_type,
        notes=notes,
    )
    try:
        await orchestrator.run()
    except Exception as exc:
        print(f"[CSR BACKGROUND] Pipeline error for account {account_id}: {exc}")


@router.post("/tickets", response_model=RaiseTicketResponse, status_code=202)
async def raise_ticket(
    body: RaiseTicketRequest,
    background_tasks: BackgroundTasks,
) -> RaiseTicketResponse:
    """
    Raise a billing escalation ticket for CSR.
    Pipeline steps 1-5 run in the background; returns immediately.
    """
    db = get_database()

    # Validate account exists
    account_doc = await db["accounts"].find_one({"account_id": body.account_id})
    if not account_doc:
        raise HTTPException(status_code=404, detail=f"Account {body.account_id} not found")

    # Validate CSR exists
    csr_doc = await db["users"].find_one({"user_id": body.csr_id, "role": "csr"})
    if not csr_doc:
        raise HTTPException(status_code=404, detail=f"CSR user {body.csr_id} not found")

    # Resolve DRI from pool
    dri_id: str | None = None
    for candidate in account_doc.get("dri_pool", []):
        user_doc = await db["users"].find_one({"user_id": candidate, "active": True, "role": "dri"})
        if user_doc:
            dri_id = candidate
            break

    # Peek at next sequence to include in response (step 1 will create it properly)
    seq = await db["escalations"].count_documents({}) + 1
    seq_str = str(seq).zfill(4)
    escalation_id_preview = f"ESC-{seq_str}"
    execution_id_preview = f"EX-{seq_str}"

    # Launch background pipeline
    background_tasks.add_task(
        _run_pipeline,
        body.account_id,
        body.csr_id,
        "manual_csr",
        body.notes,
    )

    return RaiseTicketResponse(
        escalation_id=escalation_id_preview,
        execution_id=execution_id_preview,
        status="initiated",
        dri_assigned=dri_id,
        message=(
            f"Escalation initiated for account {body.account_id}. "
            f"Pipeline is running in background. Check status at "
            f"/csr/tickets/detail/{escalation_id_preview}"
        ),
    )


@router.get("/tickets/{csr_id}", response_model=list[EscalationSummary])
async def list_csr_tickets(csr_id: str) -> list[EscalationSummary]:
    """List all escalations raised by a CSR."""
    db = get_database()

    cursor = db["escalations"].find(
        {"csr_id": csr_id},
        {"_id": 0, "escalation_id": 1, "account_id": 1, "status": 1, "opened_at": 1, "dri_id": 1},
    ).sort("opened_at", -1)

    results = []
    async for doc in cursor:
        # Count detected conflicts from step_4
        conflict_step = None
        esc_full = await db["escalations"].find_one(
            {"escalation_id": doc["escalation_id"]}, {"pipeline.step_4_conflicts": 1}
        )
        if esc_full:
            conflict_step = esc_full.get("pipeline", {}).get("step_4_conflicts")

        conflicts_detected = None
        if conflict_step and conflict_step.get("conflicts"):
            conflicts_detected = sum(1 for c in conflict_step["conflicts"] if c.get("detected"))

        results.append(
            EscalationSummary(
                escalation_id=doc["escalation_id"],
                account_id=doc["account_id"],
                status=doc["status"],
                opened_at=doc["opened_at"],
                dri_id=doc.get("dri_id"),
                conflicts_detected=conflicts_detected,
            )
        )
    return results


@router.get("/tickets/detail/{escalation_id}")
async def get_ticket_detail(escalation_id: str) -> dict:
    """Return the full escalation document."""
    db = get_database()
    doc = await db["escalations"].find_one({"escalation_id": escalation_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail=f"Escalation {escalation_id} not found")
    return doc


@router.post("/outputs/review", response_model=OutputReviewResponse)
async def review_output(body: OutputReviewRequest) -> OutputReviewResponse:
    """
    CSR reviews (optionally edits) and approves one of the 3 output drafts.
    When all 3 are approved the escalation is sent and marked resolved.
    """
    db = get_database()

    esc = await db["escalations"].find_one({"escalation_id": body.escalation_id})
    if not esc:
        raise HTTPException(status_code=404, detail=f"Escalation {body.escalation_id} not found")

    if esc["status"] != "awaiting_output_review":
        raise HTTPException(
            status_code=400,
            detail=f"Escalation {body.escalation_id} is '{esc['status']}', not 'awaiting_output_review'",
        )

    outputs = esc.get("pipeline", {}).get("step_7_outputs") or {}
    field = OUTPUT_FIELDS[body.output_type]
    output = outputs.get(field)
    if not output:
        raise HTTPException(status_code=404, detail=f"Output '{body.output_type}' not found")

    now = datetime.now(timezone.utc)
    edited = body.edited_content is not None
    if edited:
        output["content"] = body.edited_content
    output["review_status"] = "approved"
    output["reviewed_by"] = body.reviewed_by
    output["reviewed_at"] = now
    output["edited"] = edited

    # Audit: one immutable entry per output approval
    await db["audit_trail"].insert_one({
        "escalation_id": body.escalation_id,
        "pipeline_step": 7,
        "step_name": "output_review",
        "claim_type": "output_review",
        "source_system": "csr",
        "field": f"{body.output_type}_output_approved",
        "value": f"approved by {body.reviewed_by}" + (" (edited)" if edited else ""),
        "extracted_at": None,
        "recorded_at": now,
        "actor": body.reviewed_by,
        "immutable": True,
    })

    # All 3 approved? -> send + resolve
    all_approved = all(
        (outputs.get(f) or {}).get("review_status") == "approved"
        for f in OUTPUT_FIELDS.values()
    )

    new_status = esc["status"]
    if all_approved:
        new_status = "resolved"
        outputs["dispatched_at"] = now
        await db["audit_trail"].insert_one({
            "escalation_id": body.escalation_id,
            "pipeline_step": 7,
            "step_name": "output_dispatch",
            "claim_type": "output_dispatch",
            "source_system": "csr",
            "field": "outputs_dispatched",
            "value": f"3 outputs approved and dispatched by {body.reviewed_by}",
            "extracted_at": None,
            "recorded_at": now,
            "actor": body.reviewed_by,
            "immutable": True,
        })

    update: dict = {"pipeline.step_7_outputs": outputs, "updated_at": now}
    if all_approved:
        update["status"] = "resolved"
        update["resolved_at"] = now
    await db["escalations"].update_one({"escalation_id": body.escalation_id}, {"$set": update})

    return OutputReviewResponse(
        escalation_id=body.escalation_id,
        output_type=body.output_type,
        review_status="approved",
        edited=edited,
        all_approved=all_approved,
        status=new_status,
        message=(
            f"{body.output_type.title()} output approved"
            + (" and edited" if edited else "")
            + (". All 3 outputs approved — dispatched. Ticket resolved." if all_approved else ".")
        ),
    )
