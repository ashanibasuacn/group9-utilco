"""
Async pipeline tests using pytest-asyncio.
Requires a live MongoDB connection (MONGODB_URI in .env).
"""
from __future__ import annotations

import asyncio
import pytest
import pytest_asyncio

from database.connection import get_database, ping_database
from database.seed import seed_all
from pipeline import step2_ingestion, step3_reconciliation, step4_conflicts
from pipeline.orchestrator import PipelineOrchestrator

# ---------------------------------------------------------------------------
# pytest-asyncio configuration
# ---------------------------------------------------------------------------
pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture(scope="session")
def event_loop():
    """Create an event loop for the entire test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session", autouse=True)
async def seed_database():
    """Seed the database once for the entire test session."""
    await ping_database()
    db = get_database()
    await seed_all(db)
    yield


# ---------------------------------------------------------------------------
# Test 1 — Seed Verification
# ---------------------------------------------------------------------------

async def test_seed_database():
    """All 10 collections should be populated after seeding."""
    db = get_database()

    collection_checks = {
        "accounts": 3,
        "ccb_stubs": 3,
        "mdm_stubs": 3,
        "oms_stubs": 3,
        "crm_stubs": 3,
        "gl_stubs": 3,
        "users": 3,
        "escalations": 0,       # seeded empty
        "audit_trail": 0,        # seeded empty
        "analyst_executions": 0, # seeded empty
    }

    for collection_name, min_count in collection_checks.items():
        count = await db[collection_name].count_documents({})
        assert count >= min_count, (
            f"Collection '{collection_name}' has {count} documents, expected >= {min_count}"
        )

    # Verify specific accounts
    acme = await db["accounts"].find_one({"account_id": "UTL-00421937"})
    assert acme is not None
    assert acme["customer_name"] == "Acme Manufacturing"

    riverside = await db["accounts"].find_one({"account_id": "UTL-00389204"})
    assert riverside is not None

    metro = await db["accounts"].find_one({"account_id": "UTL-00371055"})
    assert metro is not None

    # Verify users
    csr = await db["users"].find_one({"user_id": "USR-CSR-112"})
    assert csr is not None
    assert csr["role"] == "csr"

    dri = await db["users"].find_one({"user_id": "USR-DRI-001"})
    assert dri is not None
    assert dri["role"] == "dri"


# ---------------------------------------------------------------------------
# Test 2 — Step 2: Parallel Ingestion
# ---------------------------------------------------------------------------

async def test_step2_ingestion_parallel():
    """Step 2 should return all 5 source snapshots for UTL-00421937."""
    db = get_database()

    # Create a minimal escalation for testing
    from pipeline.step1_trigger import execute as step1
    escalation_id, execution_id = await step1(db, "UTL-00421937", "USR-CSR-112", "manual_csr", None)

    ingestion_data = await step2_ingestion.execute(db, escalation_id, "UTL-00421937")

    assert set(ingestion_data.keys()) == {"ccb", "mdm", "oms", "crm", "gl"}

    for source_name, source_data in ingestion_data.items():
        assert "extracted_at" in source_data, f"Missing extracted_at for {source_name}"
        assert "snapshot" in source_data, f"Missing snapshot for {source_name}"
        assert source_data["snapshot"], f"Empty snapshot for {source_name}"

    # Verify CC&B has correct billing period
    ccb = ingestion_data["ccb"]["snapshot"]
    assert ccb["billing_period"]["start"] == "2024-10-01"
    assert ccb["billing_period"]["end"] == "2024-10-31"
    assert ccb["bill"]["total_kwh"] == 4200.0

    # Verify MDM has 13 estimated days
    mdm = ingestion_data["mdm"]["snapshot"]
    assert mdm["period_summary"]["estimated_days"] == 13

    # Verify OMS has disconnect work order
    oms = ingestion_data["oms"]["snapshot"]
    disconnect_wos = [wo for wo in oms["work_orders"] if wo["type"] == "disconnect"]
    assert len(disconnect_wos) == 1
    assert disconnect_wos[0]["work_order_id"] == "WO-88441"


# ---------------------------------------------------------------------------
# Test 3 — Step 3: Reconciliation for full-conflict account
# ---------------------------------------------------------------------------

async def test_step3_reconciliation_full_conflict():
    """UTL-00421937 disconnected Oct 18 → 13 post-disconnect days (Oct 19-31)."""
    db = get_database()

    from pipeline.step1_trigger import execute as step1
    escalation_id, _ = await step1(db, "UTL-00421937", "USR-CSR-112", "manual_csr", None)
    ingestion_data = await step2_ingestion.execute(db, escalation_id, "UTL-00421937")
    reconciliation = await step3_reconciliation.execute(db, escalation_id, ingestion_data)

    summary = reconciliation.summary
    assert summary is not None

    # Disconnect on Oct 18: pre = Oct 1-17 (17 days), disconnect = Oct 18 (1), post = Oct 19-31 (13 days)
    assert summary.post_disconnect_days == 13, (
        f"Expected 13 post-disconnect days, got {summary.post_disconnect_days}"
    )
    assert summary.pre_disconnect_days == 17
    assert summary.disconnect_day == 1

    # Reconciliation stored in DB
    esc_doc = await db["escalations"].find_one({"escalation_id": escalation_id})
    assert esc_doc["pipeline"]["step_3_reconciliation"] is not None
    assert esc_doc["pipeline"]["step_3_reconciliation"]["summary"]["post_disconnect_days"] == 13


# ---------------------------------------------------------------------------
# Test 4 — Step 4: All 4 conflicts for UTL-00421937
# ---------------------------------------------------------------------------

async def test_step4_all_4_conflicts():
    """UTL-00421937 should trigger all 4 conflicts (C1, C2, C3, C4)."""
    db = get_database()

    from pipeline.step1_trigger import execute as step1
    escalation_id, _ = await step1(db, "UTL-00421937", "USR-CSR-112", "manual_csr", None)
    ingestion_data = await step2_ingestion.execute(db, escalation_id, "UTL-00421937")
    reconciliation = await step3_reconciliation.execute(db, escalation_id, ingestion_data)
    conflicts = await step4_conflicts.execute(db, escalation_id, ingestion_data, reconciliation)

    assert len(conflicts) == 4

    conflict_map = {c.id: c for c in conflicts}

    assert conflict_map["C1"].detected is True, f"C1 not detected: {conflict_map['C1'].evidence}"
    assert conflict_map["C2"].detected is True, f"C2 not detected: {conflict_map['C2'].evidence}"
    assert conflict_map["C3"].detected is True, f"C3 not detected: {conflict_map['C3'].evidence}"
    assert conflict_map["C4"].detected is True, f"C4 not detected: {conflict_map['C4'].evidence}"

    # Verify invariant names
    assert conflict_map["C1"].invariant == "full_cycle_post_disconnect"
    assert conflict_map["C2"].invariant == "phantom_consumption"
    assert conflict_map["C3"].invariant == "billing_hold_not_propagated"
    assert conflict_map["C4"].invariant == "revenue_posted_under_dispute"


# ---------------------------------------------------------------------------
# Test 5 — Step 4: Only C1 and C2 for UTL-00389204
# ---------------------------------------------------------------------------

async def test_step4_2_conflicts():
    """UTL-00389204 should only detect C1 and C2 (no CRM complaints, GL pending)."""
    db = get_database()

    from pipeline.step1_trigger import execute as step1
    escalation_id, _ = await step1(db, "UTL-00389204", "USR-CSR-112", "manual_csr", None)
    ingestion_data = await step2_ingestion.execute(db, escalation_id, "UTL-00389204")
    reconciliation = await step3_reconciliation.execute(db, escalation_id, ingestion_data)
    conflicts = await step4_conflicts.execute(db, escalation_id, ingestion_data, reconciliation)

    conflict_map = {c.id: c for c in conflicts}

    assert conflict_map["C1"].detected is True, "C1 should be detected for UTL-00389204"
    assert conflict_map["C2"].detected is True, "C2 should be detected for UTL-00389204"
    assert conflict_map["C3"].detected is False, "C3 should NOT be detected (no complaints)"
    assert conflict_map["C4"].detected is False, "C4 should NOT be detected (GL not posted)"


# ---------------------------------------------------------------------------
# Test 6 — Step 4: No conflicts for UTL-00371055
# ---------------------------------------------------------------------------

async def test_step4_no_conflicts():
    """UTL-00371055 (Metro Offices) should have no conflicts detected."""
    db = get_database()

    from pipeline.step1_trigger import execute as step1
    escalation_id, _ = await step1(db, "UTL-00371055", "USR-CSR-112", "manual_csr", None)
    ingestion_data = await step2_ingestion.execute(db, escalation_id, "UTL-00371055")
    reconciliation = await step3_reconciliation.execute(db, escalation_id, ingestion_data)
    conflicts = await step4_conflicts.execute(db, escalation_id, ingestion_data, reconciliation)

    detected = [c for c in conflicts if c.detected]
    assert len(detected) == 0, (
        f"Expected 0 conflicts for UTL-00371055, got {len(detected)}: "
        f"{[(c.id, c.evidence) for c in detected]}"
    )


# ---------------------------------------------------------------------------
# Test 7 — Step 5: Citation coverage == 1.0
# ---------------------------------------------------------------------------

async def test_step5_citation_coverage():
    """Agent must return citation_coverage == 1.0 for UTL-00421937."""
    db = get_database()
    from pipeline import step5_brief as _step5

    from pipeline.step1_trigger import execute as step1
    escalation_id, _ = await step1(db, "UTL-00421937", "USR-CSR-112", "manual_csr", None)
    ingestion_data = await step2_ingestion.execute(db, escalation_id, "UTL-00421937")
    reconciliation = await step3_reconciliation.execute(db, escalation_id, ingestion_data)
    conflicts = await step4_conflicts.execute(db, escalation_id, ingestion_data, reconciliation)

    brief = await _step5.execute(db, escalation_id, "UTL-00421937", ingestion_data, reconciliation, conflicts)

    assert brief.citation_coverage == 1.0, (
        f"citation_coverage must be 1.0, got {brief.citation_coverage}"
    )
    assert len(brief.recommendations) >= 4, (
        f"Expected 4 recommendations for 4 detected conflicts, got {len(brief.recommendations)}"
    )


# ---------------------------------------------------------------------------
# Test 8 — Full Pipeline: Approved
# ---------------------------------------------------------------------------

async def test_full_pipeline_approved():
    """End-to-end test: UTL-00421937 pipeline through DRI approve → awaiting_output_review.

    DRI approval now produces 3 output DRAFTS pending CSR review (it no longer
    resolves the ticket directly). Final dispatch/resolution is covered by
    test_output_review_flow.
    """
    db = get_database()

    orchestrator = PipelineOrchestrator(
        db=db,
        account_id="UTL-00421937",
        csr_id="USR-CSR-112",
        trigger_type="manual_csr",
        notes="Integration test — full pipeline approved",
    )

    escalation_id = await orchestrator.run()
    assert escalation_id.startswith("ESC-")

    # Verify status is awaiting_dri after steps 1-5
    esc_doc = await db["escalations"].find_one({"escalation_id": escalation_id})
    assert esc_doc["status"] == "awaiting_dri"

    # DRI approves
    await orchestrator.resume_after_dri(
        escalation_id=escalation_id,
        decision="approved",
        decided_by="USR-DRI-001",
        reason=None,
    )

    # DRI approval generates output drafts and hands off to CSR review
    esc_doc = await db["escalations"].find_one({"escalation_id": escalation_id})
    assert esc_doc["status"] == "awaiting_output_review", f"Got {esc_doc['status']}"
    assert esc_doc.get("resolved_at") is None  # not resolved until CSR approves all 3

    # Verify all 7 steps populated
    pipeline = esc_doc["pipeline"]
    for step_key in [
        "step_1_trigger", "step_2_ingestion", "step_3_reconciliation",
        "step_4_conflicts", "step_5_brief", "step_6_dri", "step_7_outputs",
    ]:
        assert pipeline.get(step_key) is not None, f"Pipeline step '{step_key}' is None"

    # Verify 3 output drafts exist and are pending CSR review
    outputs = pipeline["step_7_outputs"]
    assert outputs["dispatched_at"] is None  # not dispatched until reviewed
    for field in ("customer_summary", "executive_brief", "engineering_handoff"):
        assert outputs[field] is not None
        assert outputs[field]["review_status"] == "pending_review"


# ---------------------------------------------------------------------------
# Test 8b — CSR Output Review Gate
# ---------------------------------------------------------------------------

async def test_output_review_flow():
    """CSR reviews/edits/approves each of the 3 outputs → ticket dispatched & resolved."""
    from api.routes.csr import review_output
    from api.schemas import OutputReviewRequest

    db = get_database()
    orchestrator = PipelineOrchestrator(
        db=db, account_id="UTL-00421937", csr_id="USR-CSR-112",
        trigger_type="manual_csr", notes="Output review test",
    )
    escalation_id = await orchestrator.run()
    await orchestrator.resume_after_dri(
        escalation_id=escalation_id, decision="approved",
        decided_by="USR-DRI-001", reason=None,
    )

    # Approve customer (with an edit), then executive, then engineering
    res = await review_output(OutputReviewRequest(
        escalation_id=escalation_id, output_type="customer", reviewed_by="USR-CSR-112",
        edited_content={"what_we_found": "Edited summary."},
    ))
    assert res.review_status == "approved" and res.edited is True
    assert res.all_approved is False

    await review_output(OutputReviewRequest(
        escalation_id=escalation_id, output_type="executive", reviewed_by="USR-CSR-112",
    ))
    res = await review_output(OutputReviewRequest(
        escalation_id=escalation_id, output_type="engineering", reviewed_by="USR-CSR-112",
    ))
    assert res.all_approved is True and res.status == "resolved"

    esc_doc = await db["escalations"].find_one({"escalation_id": escalation_id})
    assert esc_doc["status"] == "resolved"
    assert esc_doc["resolved_at"] is not None
    outputs = esc_doc["pipeline"]["step_7_outputs"]
    assert outputs["dispatched_at"] is not None
    assert outputs["customer_summary"]["edited"] is True
    assert outputs["customer_summary"]["content"]["what_we_found"] == "Edited summary."
    for field in ("customer_summary", "executive_brief", "engineering_handoff"):
        assert outputs[field]["review_status"] == "approved"
        assert outputs[field]["reviewed_by"] == "USR-CSR-112"

    # Audit: 3 output_review entries + at least 1 output_dispatch
    entries = await db["audit_trail"].find({"escalation_id": escalation_id}, {"_id": 0}).to_list(length=500)
    review_entries = [e for e in entries if e.get("claim_type") == "output_review"]
    assert len(review_entries) == 3, f"Expected 3 output_review entries, got {len(review_entries)}"


# ---------------------------------------------------------------------------
# Test 9 — Full Pipeline: Rejected
# ---------------------------------------------------------------------------

async def test_full_pipeline_rejected():
    """End-to-end test: DRI rejects with reason → status=rejected."""
    db = get_database()

    orchestrator = PipelineOrchestrator(
        db=db,
        account_id="UTL-00389204",
        csr_id="USR-CSR-112",
        trigger_type="manual_csr",
        notes="Integration test — rejection scenario",
    )

    escalation_id = await orchestrator.run()

    # DRI rejects
    await orchestrator.resume_after_dri(
        escalation_id=escalation_id,
        decision="rejected",
        decided_by="USR-DRI-001",
        reason="Insufficient evidence for credit issuance at this time.",
    )

    esc_doc = await db["escalations"].find_one({"escalation_id": escalation_id})
    assert esc_doc["status"] == "rejected", f"Expected rejected, got {esc_doc['status']}"

    # DRI step should record reason
    dri_step = esc_doc["pipeline"]["step_6_dri"]
    assert dri_step["decision"] == "rejected"
    assert dri_step["reason"] == "Insufficient evidence for credit issuance at this time."

    # Step 7 should NOT be populated
    assert esc_doc["pipeline"]["step_7_outputs"] is None


# ---------------------------------------------------------------------------
# Test 10 — Audit Trail Completeness
# ---------------------------------------------------------------------------

async def test_audit_trail_completeness():
    """After a full approved pipeline run, audit trail must have entries for all steps."""
    db = get_database()

    orchestrator = PipelineOrchestrator(
        db=db,
        account_id="UTL-00421937",
        csr_id="USR-CSR-112",
        trigger_type="manual_csr",
        notes="Audit completeness test",
    )

    escalation_id = await orchestrator.run()
    await orchestrator.resume_after_dri(
        escalation_id=escalation_id,
        decision="approved",
        decided_by="USR-DRI-001",
        reason=None,
    )

    # Fetch all audit entries for this escalation
    cursor = db["audit_trail"].find({"escalation_id": escalation_id}, {"_id": 0})
    entries = []
    async for entry in cursor:
        entries.append(entry)

    assert len(entries) > 0, "No audit trail entries found"

    # Verify entries exist for each pipeline step
    steps_with_audit = {entry["pipeline_step"] for entry in entries}

    for expected_step in [1, 2, 3, 4, 5, 6, 7]:
        assert expected_step in steps_with_audit, (
            f"No audit entries for pipeline step {expected_step}. "
            f"Steps with entries: {sorted(steps_with_audit)}"
        )

    # Verify all entries are immutable
    for entry in entries:
        assert entry.get("immutable") is True, f"Non-immutable audit entry found: {entry}"

    # Verify there is at least one conflict audit entry (step 4)
    conflict_entries = [e for e in entries if e.get("claim_type") == "conflict"]
    assert len(conflict_entries) >= 1, "Expected at least 1 conflict audit entry"

    # Verify there is at least one recommendation entry (step 5)
    rec_entries = [e for e in entries if e.get("claim_type") == "recommendation"]
    assert len(rec_entries) >= 1, "Expected at least 1 recommendation audit entry"

    # Verify DRI decision entry (step 6)
    dri_entries = [e for e in entries if e.get("claim_type") == "dri_decision"]
    assert len(dri_entries) >= 1, "Expected at least 1 dri_decision audit entry"

    # Verify output dispatch entry (step 7)
    output_entries = [e for e in entries if e.get("claim_type") == "output_dispatch"]
    assert len(output_entries) >= 1, "Expected at least 1 output_dispatch audit entry"
