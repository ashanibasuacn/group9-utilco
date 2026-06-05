from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class StepExecution(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    step: int
    name: str
    started_at: datetime | None = None
    duration_ms: int | None = None
    nfr_target_ms: int | None = None
    breach: bool = False


class AnalystExecution(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    execution_id: str
    escalation_id: str
    account_id: str
    trigger_type: str
    overall_status: Literal["running", "complete", "failed", "timeout"]
    steps: list[StepExecution]
    total_duration_ms: int | None = None
    agent_duration_ms: int | None = None
    conflicts_detected: int = 0
    citation_coverage: float = 0.0
    nfr_breaches: int = 0
    created_at: datetime
    completed_at: datetime | None = None
