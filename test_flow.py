import sys, asyncio
sys.path.insert(0, 'C:/GIT/group9-utilco/utilico-agent')

from database.connection import get_database
from database.seed import seed_all
from pipeline import step1_trigger, step2_ingestion, step3_reconciliation, step4_conflicts


async def run():
    db = get_database()

    print("=== Seeding in-memory database ===")
    await seed_all(db)

    accounts = await db["accounts"].count_documents({})
    print(f"Accounts seeded: {accounts}")

    print("\n=== Pipeline steps 1-4 — UTL-00421937 (all 4 conflicts) ===")

    # Step 1 — Trigger
    esc_id, exec_id = await step1_trigger.execute(db, "UTL-00421937", "USR-CSR-112", "manual_csr", "Test run")
    print(f"Step 1  escalation={esc_id}  execution={exec_id}")

    # Step 2 — Ingestion
    ingestion = await step2_ingestion.execute(db, esc_id, "UTL-00421937")
    print(f"Step 2  sources={list(ingestion.keys())}")

    # Step 3 — Reconciliation
    recon = await step3_reconciliation.execute(db, esc_id, ingestion)
    s = recon.summary
    print(f"Step 3  pre={s.pre_disconnect_days}  disconnect_day={s.disconnect_day}  post={s.post_disconnect_days}  est_post={s.estimated_read_days_post_disconnect}")

    # Step 4 — Conflict detection
    conflicts = await step4_conflicts.execute(db, esc_id, ingestion, recon)
    print("Step 4  conflicts:")
    for c in conflicts:
        status = "DETECTED" if c.detected else "clean"
        print(f"  {c.id} [{status}]  {c.invariant}")
        if c.evidence:
            print(f"    {c.evidence}")

    detected = sum(1 for c in conflicts if c.detected)
    print(f"\nDetected: {detected}/4")

    # Audit trail
    audit_count = await db["audit_trail"].count_documents({"escalation_id": esc_id})
    print(f"Audit entries written: {audit_count}")

    print("\n=== Clean scenario — UTL-00371055 (no conflicts) ===")
    esc2, _ = await step1_trigger.execute(db, "UTL-00371055", "USR-CSR-112", "manual_csr", None)
    ing2 = await step2_ingestion.execute(db, esc2, "UTL-00371055")
    rec2 = await step3_reconciliation.execute(db, esc2, ing2)
    con2 = await step4_conflicts.execute(db, esc2, ing2, rec2)
    detected2 = sum(1 for c in con2 if c.detected)
    print(f"Conflicts detected: {detected2}/4 (expected 0)")

    print("\nAll steps OK — mongomock in-memory flow working")


asyncio.run(run())
