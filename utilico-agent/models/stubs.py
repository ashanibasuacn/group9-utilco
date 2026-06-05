from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


# ---------------------------------------------------------------------------
# CC&B
# ---------------------------------------------------------------------------

class BillingPeriod(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    start: str
    end: str
    cycle_days: int


class BillingRules(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    tariff: str
    proration_enabled: bool
    disconnect_suppression: bool


class Bill(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    generated_at: datetime
    total_kwh: float
    total_amount: float
    currency: str
    status: str


class CCBStub(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    account_id: str
    account_status: str
    billing_period: BillingPeriod
    billing_rules: BillingRules
    bill: Bill
    stub_version: str
    seeded_at: datetime


# ---------------------------------------------------------------------------
# MDM
# ---------------------------------------------------------------------------

class MDMRead(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    date: str
    kwh: float
    read_type: Literal["actual", "estimated"]
    estimation_basis: str | None = None


class PeriodSummary(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    total_actual_kwh: float
    total_estimated_kwh: float
    estimated_days: int


class MDMStub(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    account_id: str
    meter_id: str
    reads: list[MDMRead]
    period_summary: PeriodSummary
    stub_version: str
    seeded_at: datetime


# ---------------------------------------------------------------------------
# OMS
# ---------------------------------------------------------------------------

class Technician(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    name: str
    confirmed: bool


class WorkOrder(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    work_order_id: str
    type: str
    status: str
    scheduled_at: datetime
    completed_at: datetime | None = None
    technician: Technician
    notes: str


class OMSStub(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    account_id: str
    work_orders: list[WorkOrder]
    current_service_status: str
    stub_version: str
    seeded_at: datetime


# ---------------------------------------------------------------------------
# CRM
# ---------------------------------------------------------------------------

class Complaint(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    complaint_id: str
    type: str
    status: str
    filed_at: datetime
    channel: str
    description: str
    regulatory_dispute: bool


class CRMNote(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    added_at: datetime
    author: str
    text: str


class CRMStub(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    account_id: str
    billing_hold: bool
    complaints: list[Complaint]
    notes: list[CRMNote]
    stub_version: str
    seeded_at: datetime


# ---------------------------------------------------------------------------
# GL
# ---------------------------------------------------------------------------

class RevenueEntry(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    entry_id: str
    period: str
    amount: float
    currency: str
    status: str
    posted_at: datetime | None = None
    source_bill_id: str
    reversal_required: bool
    reversal_amount: float | None = None


class GLStub(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    account_id: str
    revenue_entries: list[RevenueEntry]
    stub_version: str
    seeded_at: datetime
