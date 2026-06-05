"""
Pipeline Orchestrator
Coordinates all 7 pipeline steps for the billing reconciliation workflow.
"""
from __future__ import annotations

from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorDatabase

from models.audit import AuditClaimType
from pipeline import step1_trigger, step2_ingestion, step3_reconciliation, step4_conflicts, step5_brief, step6_dri, step7_outputs

# NFR targets in milliseconds (None = no target)
NFR_TARGETS: dict[int, int | None] = {
    1: None,
    2: 420_000,
    3: 420_000,
    4: 15_000,
    5: 60_000,
    6: 300_000,
    7: None,
}

STEP_NAMES = {
    1: "trigger",
    2: "ingestion",
    3: "reconciliation",
    4: "conflict_detection",
    5: "brief_generation",
    6: "dri_decision",
    7: "output_dispatch",
}


class PipelineOrchestrator:
    def __init__(
        self,
        db: AsyncIOMotorDatabase,
        account_id: str,
        csr_id: str,
        trigger_type: str,
        notes: str | None = None,
    ) -> None:
        self.db = db
        self.account_id = account_id
        self.csr_id = csr_id
        self.trigger_type = trigger_type
        self.notes = notes

        self._escalation_id: str | None = None
        self._execution_id: str | None = None

    async def run(self) -> str:
        """Run steps 1-5, pause at step 6. Returns escalation_id."""
        db = self.db

        # -----------------------------------------------------------------------
        # Step 1 — Trigger
        # -----------------------------------------------------------------------
        s1_start = datetime.now(timezone.utc)
        escalation_id, execution_id = await step1_trigger.execute(
            db, self.account_id, self.csr_id, self.trigger_type, self.notes
        )
        self._escalation_id = escalation_id
        self._execution_id = execution_id
        s1_end = datetime.now(timezone.utc)
        s1_ms = int((s1_end - s1_start).total_seconds() * 1000)
        await self._record_step_timing(execution_id, 1, STEP_NAMES[1], s1_start, s1_ms, NFR_TARGETS[1])

        # -----------------------------------------------------------------------
        # Step 2 — Ingestion
        # -----------------------------------------------------------------------
        s2_start = datetime.now(timezone.utc)
        ingestion_data = await step2_ingestion.execute(db, escalation_id, self.account_id)
        s2_end = datetime.now(timezone.utc)
        s2_ms = int((s2_end - s2_start).total_seconds() * 1000)
        await self._record_step_timing(execution_id, 2, STEP_NAMES[2], s2_start, s2_ms, NFR_TARGETS[2])

        # -----------------------------------------------------------------------
        # Step 3 — Reconciliation
        # -----------------------------------------------------------------------
        s3_start = datetime.now(timezone.utc)
        reconciliation = await step3_reconciliation.execute(db, escalation_id, ingestion_data)
        s3_end = datetime.now(timezone.utc)
        s3_ms = int((s3_end - s3_start).total_seconds() * 1000)
        await self._record_step_timing(execution_id, 3, STEP_NAMES[3], s3_start, s3_ms, NFR_TARGETS[3])

        # -----------------------------------------------------------------------
        # Step 4 — Conflict Detection
        # -----------------------------------------------------------------------
        s4_start = datetime.now(timezone.utc)
        conflicts = await step4_conflicts.execute(db, escalation_id, ingestion_data, reconciliation)
        s4_end = datetime.now(timezone.utc)
        s4_ms = int((s4_end - s4_start).total_seconds() * 1000)
        await self._record_step_timing(execution_id, 4, STEP_NAMES[4], s4_start, s4_ms, NFR_TARGETS[4])

        # -----------------------------------------------------------------------
        # Step 5 — AI Brief
        # -----------------------------------------------------------------------
        s5_start = datetime.now(timezone.utc)
        brief = await step5_brief.execute(
            db, escalation_id, self.account_id, ingestion_data, reconciliation, conflicts
        )
        s5_end = datetime.now(timezone.utc)
        s5_ms = int((s5_end - s5_start).total_seconds() * 1000)
        await self._record_step_timing(execution_id, 5, STEP_NAMES[5], s5_start, s5_ms, NFR_TARGETS[5])

        # Update execution document with step-5 metrics
        detected_count = sum(1 for c in conflicts if c.detected)
        await db["analyst_executions"].update_one(
            {"execution_id": execution_id},
            {
                "$set": {
                    "conflicts_detected": detected_count,
                    "citation_coverage": brief.citation_coverage,
                    "agent_duration_ms": s5_ms,
                }
            },
        )

        print(f"[ORCHESTRATOR] Steps 1-5 complete for {escalation_id}. Awaiting DRI.")
        return escalation_id

    async def resume_after_dri(
        self,
        escalation_id: str,
        decision: str,
        decided_by: str,
        reason: str | None,
    ) -> None:
        """Run steps 6-7 after DRI decision. Only proceeds to step 7 if approved."""
        db = self.db

        # Fetch execution_id from escalation's corresponding execution
        exec_doc = await db["analyst_executions"].find_one(
            {"escalation_id": escalation_id}, {"execution_id": 1}
        )
        execution_id = exec_doc["execution_id"] if exec_doc else f"EX-{escalation_id[4:]}"

        # -----------------------------------------------------------------------
        # Step 6 — DRI Decision
        # -----------------------------------------------------------------------
        s6_start = datetime.now(timezone.utc)
        dri_result = await step6_dri.execute(
            db, escalation_id, decision, decided_by, reason, s6_start
        )
        s6_end = datetime.now(timezone.utc)
        s6_ms = int((s6_end - s6_start).total_seconds() * 1000)
        await self._record_step_timing(execution_id, 6, STEP_NAMES[6], s6_start, s6_ms, NFR_TARGETS[6])

        if decision != "approved":
            # Mark execution complete
            now = datetime.now(timezone.utc)
            await db["analyst_executions"].update_one(
                {"execution_id": execution_id},
                {"$set": {"overall_status": "complete", "completed_at": now}},
            )
            print(f"[ORCHESTRATOR] Escalation {escalation_id} {decision}. Pipeline terminated.")
            return

        # -----------------------------------------------------------------------
        # Step 7 — Output Dispatch
        # -----------------------------------------------------------------------
        # Fetch needed data from escalation
        esc_doc = await db["escalations"].find_one({"escalation_id": escalation_id})
        account_doc = await db["accounts"].find_one({"account_id": esc_doc["account_id"]}, {"_id": 0}) or {}

        pipeline_data = esc_doc.get("pipeline", {})
        brief_data = pipeline_data.get("step_5_brief", {})
        conflict_data = pipeline_data.get("step_4_conflicts", {}).get("conflicts", [])

        # Reconstruct BriefStep and Conflict objects
        from models.escalation import BriefStep, Conflict, Recommendation

        recommendations = [
            Recommendation(**r) for r in brief_data.get("recommendations", [])
        ]
        brief_obj = BriefStep(
            completed_at=brief_data.get("completed_at"),
            duration_ms=brief_data.get("duration_ms"),
            recommendations=recommendations,
            brief_text=brief_data.get("brief_text"),
            confidence_signal=brief_data.get("confidence_signal"),
            citation_coverage=brief_data.get("citation_coverage", 0.0),
        )

        conflicts_objs = [
            Conflict(
                id=c["id"],
                systems=c["systems"],
                detected=c["detected"],
                invariant=c["invariant"],
                evidence=c.get("evidence"),
            )
            for c in conflict_data
        ]

        s7_start = datetime.now(timezone.utc)
        await step7_outputs.execute(db, escalation_id, brief_obj, account_doc, conflicts_objs)
        s7_end = datetime.now(timezone.utc)
        s7_ms = int((s7_end - s7_start).total_seconds() * 1000)
        await self._record_step_timing(execution_id, 7, STEP_NAMES[7], s7_start, s7_ms, NFR_TARGETS[7])

        # Finalise execution
        now = datetime.now(timezone.utc)
        exec_full = await db["analyst_executions"].find_one({"execution_id": execution_id})
        if exec_full:
            steps = exec_full.get("steps", [])
            total_ms = sum(s.get("duration_ms") or 0 for s in steps)
            breaches = sum(1 for s in steps if s.get("breach", False))
            await db["analyst_executions"].update_one(
                {"execution_id": execution_id},
                {
                    "$set": {
                        "overall_status": "complete",
                        "completed_at": now,
                        "total_duration_ms": total_ms,
                        "nfr_breaches": breaches,
                    }
                },
            )

        print(f"[ORCHESTRATOR] Escalation {escalation_id} fully resolved.")

    async def _write_audit(
        self,
        escalation_id: str,
        step: int,
        step_name: str,
        claim_type: str,
        source_system: str,
        field: str,
        value: str,
        extracted_at: datetime | None = None,
        actor: str = "analyst_agent",
    ) -> None:
        now = datetime.now(timezone.utc)
        await self.db["audit_trail"].insert_one({
            "escalation_id": escalation_id,
            "pipeline_step": step,
            "step_name": step_name,
            "claim_type": claim_type,
            "source_system": source_system,
            "field": field,
            "value": value,
            "extracted_at": extracted_at,
            "recorded_at": now,
            "actor": actor,
            "immutable": True,
        })

    async def _update_escalation(self, escalation_id: str, updates: dict) -> None:
        now = datetime.now(timezone.utc)
        updates["updated_at"] = now
        await self.db["escalations"].update_one(
            {"escalation_id": escalation_id},
            {"$set": updates},
        )

    async def _record_step_timing(
        self,
        execution_id: str,
        step: int,
        name: str,
        started_at: datetime,
        duration_ms: int,
        nfr_target_ms: int | None,
    ) -> None:
        breach = (nfr_target_ms is not None) and (duration_ms > nfr_target_ms)
        step_doc = {
            "step": step,
            "name": name,
            "started_at": started_at,
            "duration_ms": duration_ms,
            "nfr_target_ms": nfr_target_ms,
            "breach": breach,
        }
        await self.db["analyst_executions"].update_one(
            {"execution_id": execution_id},
            {"$push": {"steps": step_doc}},
        )
