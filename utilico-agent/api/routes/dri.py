"""
DRI API Routes
GET  /dri/queue/{dri_id}          — DRI's escalation queue
GET  /dri/brief/{escalation_id}   — Step 5 brief + Step 4 conflicts
POST /dri/decision                — Record DRI decision, trigger steps 6-7
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from api.schemas import DRIDecisionRequest, DRIDecisionResponse, EscalationSummary
from database.connection import get_database
from pipeline.orchestrator import PipelineOrchestrator

router = APIRouter(prefix="/dri", tags=["DRI"])


@router.get("/queue/{dri_id}", response_model=list[EscalationSummary])
async def get_dri_queue(dri_id: str) -> list[EscalationSummary]:
    """
    Return escalations assigned to this DRI.
    awaiting_dri items first, then all others descending by opened_at.
    """
    db = get_database()

    # Verify DRI exists
    dri_doc = await db["users"].find_one({"user_id": dri_id, "role": "dri"})
    if not dri_doc:
        raise HTTPException(status_code=404, detail=f"DRI user {dri_id} not found")

    cursor = db["escalations"].find(
        {"dri_id": dri_id},
        {"_id": 0},
    ).sort("opened_at", -1)

    awaiting = []
    others = []

    async for doc in cursor:
        conflict_step = doc.get("pipeline", {}).get("step_4_conflicts")
        conflicts_detected = None
        if conflict_step and conflict_step.get("conflicts"):
            conflicts_detected = sum(1 for c in conflict_step["conflicts"] if c.get("detected"))

        dispute_type = (
            doc.get("pipeline", {}).get("step_1_trigger") or {}
        ).get("dispute_type")

        item = EscalationSummary(
            escalation_id=doc["escalation_id"],
            account_id=doc["account_id"],
            status=doc["status"],
            opened_at=doc["opened_at"],
            dri_id=doc.get("dri_id"),
            conflicts_detected=conflicts_detected,
            dispute_type=dispute_type,
        )
        if doc["status"] == "awaiting_dri":
            awaiting.append(item)
        else:
            others.append(item)

    return awaiting + others


@router.get("/brief/{escalation_id}")
async def get_dri_brief(escalation_id: str) -> dict:
    """Return step_5_brief and step_4_conflicts for the DRI to review."""
    db = get_database()
    doc = await db["escalations"].find_one(
        {"escalation_id": escalation_id},
        {
            "_id": 0,
            "escalation_id": 1,
            "account_id": 1,
            "status": 1,
            "dri_id": 1,
            "pipeline.step_4_conflicts": 1,
            "pipeline.step_5_brief": 1,
        },
    )
    if not doc:
        raise HTTPException(status_code=404, detail=f"Escalation {escalation_id} not found")

    pipeline = doc.get("pipeline", {})
    return {
        "escalation_id": doc["escalation_id"],
        "account_id": doc["account_id"],
        "status": doc["status"],
        "dri_id": doc.get("dri_id"),
        "conflicts": pipeline.get("step_4_conflicts"),
        "brief": pipeline.get("step_5_brief"),
    }


@router.post("/decision", response_model=DRIDecisionResponse)
async def record_dri_decision(body: DRIDecisionRequest) -> DRIDecisionResponse:
    """
    Record DRI decision. If approved, triggers steps 6-7 in background.
    """
    db = get_database()

    # Verify escalation exists and is in awaiting_dri status
    esc_doc = await db["escalations"].find_one({"escalation_id": body.escalation_id})
    if not esc_doc:
        raise HTTPException(status_code=404, detail=f"Escalation {body.escalation_id} not found")

    if esc_doc["status"] != "awaiting_dri":
        raise HTTPException(
            status_code=400,
            detail=f"Escalation {body.escalation_id} is in status '{esc_doc['status']}', not 'awaiting_dri'",
        )

    # Validate reason on rejection/exception
    if body.decision in ("rejected", "exception") and not body.reason:
        raise HTTPException(
            status_code=422,
            detail=f"A reason is required for decision '{body.decision}'",
        )

    # Run steps 6 and 7 directly (DRI endpoint waits for completion)
    orchestrator = PipelineOrchestrator(
        db=db,
        account_id=esc_doc["account_id"],
        csr_id=esc_doc["csr_id"],
        trigger_type=esc_doc.get("pipeline", {}).get("step_1_trigger", {}).get("trigger_type", "manual_csr"),
        notes=None,
    )

    try:
        await orchestrator.resume_after_dri(
            escalation_id=body.escalation_id,
            decision=body.decision,
            decided_by=body.decided_by,
            reason=body.reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    approved = body.decision == "approved"

    return DRIDecisionResponse(
        escalation_id=body.escalation_id,
        decision=body.decision,
        outputs_dispatched=False,  # drafts now go to CSR review before dispatch
        message=(
            f"Decision '{body.decision}' recorded for escalation {body.escalation_id}. "
            + (
                "3 output drafts generated — awaiting CSR review before dispatch."
                if approved
                else "Escalation closed."
            )
        ),
    )
