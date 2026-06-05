from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict


class AuditClaimType(str, Enum):
    system_fact = "system_fact"
    conflict = "conflict"
    recommendation = "recommendation"
    dri_decision = "dri_decision"
    output_dispatch = "output_dispatch"
    output_review = "output_review"


class AuditEntry(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    escalation_id: str
    pipeline_step: int
    step_name: str
    claim_type: AuditClaimType
    source_system: str
    field: str
    value: str
    extracted_at: datetime | None = None
    recorded_at: datetime
    actor: str
    immutable: bool = True
