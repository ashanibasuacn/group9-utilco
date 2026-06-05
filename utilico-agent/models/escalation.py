from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict


# ---------------------------------------------------------------------------
# Step 1 — Trigger
# ---------------------------------------------------------------------------

class TriggerStep(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    trigger_type: Literal["oms_auto", "manual_csr", "manual_dri"]
    dispute_type: str
    notes: str | None = None
    triggered_at: datetime


# ---------------------------------------------------------------------------
# Step 2 — Ingestion
# ---------------------------------------------------------------------------

class IngestionSource(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    extracted_at: datetime
    snapshot: dict


class IngestionStep(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    completed_at: datetime | None = None
    duration_ms: int | None = None
    sources: dict[str, IngestionSource]  # keys: ccb, mdm, oms, crm, gl


# ---------------------------------------------------------------------------
# Step 3 — Reconciliation
# ---------------------------------------------------------------------------

class DayClassification(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    date: str
    classification: Literal["pre_disconnect", "disconnect_day", "post_disconnect"]
    mdm_read_type: Literal["actual", "estimated"] | None = None


class ReconciliationSummary(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    pre_disconnect_days: int
    post_disconnect_days: int
    disconnect_day: int
    estimated_read_days_post_disconnect: int


class ReconciliationStep(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    completed_at: datetime | None = None
    disconnect_timestamp: datetime | None = None
    billing_period: dict
    period_map: list[DayClassification]
    summary: ReconciliationSummary | None = None


# ---------------------------------------------------------------------------
# Step 4 — Conflicts
# ---------------------------------------------------------------------------

class Conflict(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str  # C1, C2, C3, C4
    systems: list[str]
    detected: bool
    invariant: str
    evidence: str | None = None


class ConflictStep(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    completed_at: datetime | None = None
    duration_ms: int | None = None
    conflicts: list[Conflict]


# ---------------------------------------------------------------------------
# Step 5 — Brief
# ---------------------------------------------------------------------------

class Recommendation(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    conflict_id: str
    action: str
    cited_system: str
    rationale: str


class BriefStep(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    completed_at: datetime | None = None
    duration_ms: int | None = None
    recommendations: list[Recommendation]
    brief_text: str | None = None
    confidence_signal: str | None = None
    citation_coverage: float = 0.0


# ---------------------------------------------------------------------------
# Step 6 — DRI Decision
# ---------------------------------------------------------------------------

class DRIStep(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    decision: Literal["approved", "rejected", "exception"] | None = None
    decided_at: datetime | None = None
    decided_by: str | None = None
    reason: str | None = None
    decision_latency_ms: int | None = None


# ---------------------------------------------------------------------------
# Step 7 — Outputs
# ---------------------------------------------------------------------------

class OutputContent(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    format: str
    audience: str
    content: dict | str
    # CSR review gate — each output is a draft until a CSR reviews/edits/approves it
    review_status: Literal["pending_review", "approved"] = "pending_review"
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    edited: bool = False


class OutputsStep(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    dispatched_at: datetime | None = None
    customer_summary: OutputContent | None = None
    executive_brief: OutputContent | None = None
    engineering_handoff: OutputContent | None = None


# ---------------------------------------------------------------------------
# Pipeline container
# ---------------------------------------------------------------------------

class Pipeline(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    step_1_trigger: TriggerStep | None = None
    step_2_ingestion: IngestionStep | None = None
    step_3_reconciliation: ReconciliationStep | None = None
    step_4_conflicts: ConflictStep | None = None
    step_5_brief: BriefStep | None = None
    step_6_dri: DRIStep | None = None
    step_7_outputs: OutputsStep | None = None


# ---------------------------------------------------------------------------
# Escalation status
# ---------------------------------------------------------------------------

class EscalationStatus(str, Enum):
    initiated = "initiated"
    analysing = "analysing"
    awaiting_dri = "awaiting_dri"
    approved = "approved"
    rejected = "rejected"
    awaiting_output_review = "awaiting_output_review"
    resolved = "resolved"


# ---------------------------------------------------------------------------
# Root Escalation document
# ---------------------------------------------------------------------------

class Escalation(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    escalation_id: str
    account_id: str
    status: EscalationStatus
    dri_id: str | None = None
    csr_id: str
    opened_at: datetime
    resolved_at: datetime | None = None
    pipeline: Pipeline
    created_at: datetime
    updated_at: datetime
