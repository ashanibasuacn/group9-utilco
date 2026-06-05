from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class RaiseTicketRequest(BaseModel):
    account_id: str
    csr_id: str
    dispute_type: str
    notes: str | None = None


class RaiseTicketResponse(BaseModel):
    escalation_id: str
    execution_id: str
    status: str
    dri_assigned: str | None
    message: str


class DRIDecisionRequest(BaseModel):
    escalation_id: str
    decision: Literal["approved", "rejected", "exception"]
    decided_by: str
    reason: str | None = None


class DRIDecisionResponse(BaseModel):
    escalation_id: str
    decision: str
    outputs_dispatched: bool
    message: str


class OutputReviewRequest(BaseModel):
    escalation_id: str
    output_type: Literal["customer", "executive", "engineering"]
    reviewed_by: str
    edited_content: dict | None = None  # if provided, replaces the draft content


class OutputReviewResponse(BaseModel):
    escalation_id: str
    output_type: str
    review_status: str
    edited: bool
    all_approved: bool
    status: str
    message: str


class EscalationSummary(BaseModel):
    escalation_id: str
    account_id: str
    status: str
    opened_at: datetime
    dri_id: str | None
    conflicts_detected: int | None
    dispute_type: str | None = None


class ExecutionHealthItem(BaseModel):
    execution_id: str
    escalation_id: str
    account_id: str
    overall_status: str
    agent_duration_ms: int | None
    conflicts_detected: int
    nfr_breaches: int
    created_at: datetime
