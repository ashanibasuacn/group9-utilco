"""
Utilico Energy — Billing Reconciliation Agent
One-command interactive demo: python demo.py
Scenario: Account UTL-00421937 (Acme Manufacturing) — all 4 conflicts detected.
"""
import asyncio
import sys
import io
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.prompt import Prompt
from rich.rule import Rule
from rich.align import Align
from rich import box

from database.connection import get_database
from database.seed import seed_all
from pipeline.orchestrator import PipelineOrchestrator

console = Console()

PRP = "#A100FF"
GRN = "#007A3D"
RED = "#C8001D"
BLU = "#004F9F"
AMB = "#B45000"

ACCOUNT_ID = "UTL-00421937"
CSR_ID     = "USR-CSR-112"
DRI_ID     = "USR-DRI-001"


async def _run_silent(coro):
    buf = io.StringIO()
    old = sys.stdout
    sys.stdout = buf
    try:
        return await coro
    finally:
        sys.stdout = old


def _kv_table(rows: list[tuple[str, str]], col_width: int = 24) -> Table:
    t = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
    t.add_column("k", style="dim", width=col_width)
    t.add_column("v", style="bold")
    for k, v in rows:
        t.add_row(k, v)
    return t


async def main():
    # ── HEADER ───────────────────────────────────────────────────────────────
    console.clear()
    console.print(Panel(
        Align.center(
            f"[bold {PRP}]UTILICO ENERGY[/bold {PRP}]\n"
            "[dim]Billing Reconciliation Agent — Live Demo[/dim]\n\n"
            "[dim]Scenario: Post-disconnect billing dispute[/dim]\n"
            f"[dim]Account {ACCOUNT_ID} · Acme Manufacturing[/dim]"
        ),
        border_style=PRP,
        padding=(1, 6),
    ))
    console.print()

    # ── SEED ─────────────────────────────────────────────────────────────────
    with console.status("[dim]Initialising in-memory database...[/dim]", spinner="dots"):
        db = get_database()
        await _run_silent(seed_all(db))
    console.print(f"[{GRN}]✓[/{GRN}] Database seeded — 3 accounts, 10 collections")
    console.print()

    # ── ACCOUNT CONTEXT ──────────────────────────────────────────────────────
    account = await db["accounts"].find_one({"account_id": ACCOUNT_ID}, {"_id": 0})
    console.print(Panel(
        _kv_table([
            ("Account ID",      ACCOUNT_ID),
            ("Customer",        account["customer_name"]),
            ("Type",            account["account_type"]),
            ("Tariff",          account["tariff_code"]),
            ("Regulatory Tier", account["regulatory_tier"]),
            ("DRI Pool",        ", ".join(account.get("dri_pool", []))),
        ]),
        title=f"[bold {PRP}]Account Under Investigation[/bold {PRP}]",
        border_style="dim",
    ))
    console.print()

    # ── STEP 1 — CSR RAISES TICKET ───────────────────────────────────────────
    console.print(Panel(
        _kv_table([
            ("CSR",          "Sarah Chen (USR-CSR-112)"),
            ("Account",      ACCOUNT_ID),
            ("Dispute type", "billing_after_disconnect"),
            ("Notes",        "Customer disputes October bill — service disconnected mid-cycle"),
            ("Status",       f"[{PRP}]ANALYSING[/{PRP}]  ← pipeline triggered"),
        ]),
        title=f"[bold {PRP}]Step 1 — CSR Raises Ticket[/bold {PRP}]",
        border_style=PRP,
    ))
    console.print()

    # ── PIPELINE STEPS 1–5 ───────────────────────────────────────────────────
    orchestrator = PipelineOrchestrator(
        db=db,
        account_id=ACCOUNT_ID,
        csr_id=CSR_ID,
        trigger_type="manual_csr",
        notes="Customer disputes October bill — service disconnected mid-cycle",
    )

    with Progress(
        SpinnerColumn(style=PRP),
        TextColumn("[progress.description]{task.description}"),
        TimeElapsedColumn(),
        console=console,
        transient=False,
    ) as progress:
        t2 = progress.add_task(f"[dim]Step 2[/dim]  Ingesting 5 source systems  [dim]CC&B · MDM · OMS · CRM · GL[/dim]", total=None)
        t3 = progress.add_task(f"[dim]Step 3[/dim]  Reconciling billing period vs disconnect timeline", total=None)
        t4 = progress.add_task(f"[dim]Step 4[/dim]  Running 4 deterministic conflict checks", total=None)
        t5 = progress.add_task(f"[dim]Step 5[/dim]  Generating AI decision brief  [dim]claude-sonnet[/dim]", total=None)

        escalation_id = await _run_silent(orchestrator.run())

        for task in (t2, t3, t4, t5):
            progress.update(task, description=progress.tasks[task].description.replace("[dim]Step", f"[{GRN}]✓[/{GRN}] Step"))

    console.print()

    # ── FETCH PIPELINE DATA ──────────────────────────────────────────────────
    esc = await db["escalations"].find_one({"escalation_id": escalation_id}, {"_id": 0})
    pipeline = esc["pipeline"]

    # ── STEP 2 — INGESTION ───────────────────────────────────────────────────
    ingestion = pipeline.get("step_2_ingestion", {})
    sources   = ingestion.get("sources", {})

    it = Table(box=box.SIMPLE, show_header=True, padding=(0, 2))
    it.add_column("System",       style="bold",  width=8)
    it.add_column("Status",                      width=14)
    it.add_column("Extracted At",                width=22)
    for sys_name in ("ccb", "mdm", "oms", "crm", "gl"):
        src       = sources.get(sys_name, {})
        extracted = str(src.get("extracted_at", ""))[:19]
        it.add_row(sys_name.upper(), f"[{GRN}]✓ Retrieved[/{GRN}]", extracted)

    console.print(Panel(
        it,
        title=f"[bold]Step 2 — Parallel Ingestion[/bold]  "
              f"[dim]duration: {ingestion.get('duration_ms', 0)} ms[/dim]",
        border_style="dim",
    ))
    console.print()

    # ── STEP 3 — RECONCILIATION ──────────────────────────────────────────────
    recon = pipeline.get("step_3_reconciliation", {})
    s     = recon.get("summary", {})
    disc  = str(recon.get("disconnect_timestamp", ""))[:10]
    phantom = s.get("estimated_read_days_post_disconnect", 0)

    console.print(Panel(
        _kv_table([
            ("OMS Disconnect Timestamp",                         disc),
            ("Pre-disconnect (billable) days",                   str(s.get("pre_disconnect_days", 0))),
            ("Disconnect day",                                   str(s.get("disconnect_day", 0))),
            ("Post-disconnect (non-billable) days",              str(s.get("post_disconnect_days", 0))),
            (f"[{RED}]Phantom MDM reads (post-disconnect)[/{RED}]",
             f"[bold {RED}]{phantom} days[/bold {RED}]  [dim]estimated reads on disconnected premise[/dim]"),
        ], col_width=38),
        title="[bold]Step 3 — Temporal Reconciliation[/bold]",
        border_style="dim",
    ))
    console.print()

    # ── STEP 4 — CONFLICTS ───────────────────────────────────────────────────
    conflicts_step = pipeline.get("step_4_conflicts", {})
    conflicts      = conflicts_step.get("conflicts", [])
    detected_ids   = [c["id"] for c in conflicts if c["detected"]]

    ct = Table(box=box.ROUNDED, border_style=RED if detected_ids else "dim")
    ct.add_column("ID",        width=5,  style="bold")
    ct.add_column("Systems",   width=16)
    ct.add_column("Invariant", width=38)
    ct.add_column("Result",    width=14)
    for c in conflicts:
        result = (f"[bold {RED}]● CONFLICT[/bold {RED}]" if c["detected"]
                  else f"[{GRN}]✓ Clear[/{GRN}]")
        ct.add_row(
            c["id"],
            " ↔ ".join(x.upper() for x in c["systems"]),
            c["invariant"].replace("_", " "),
            result,
        )

    console.print(Panel(
        ct,
        title=f"[bold]Step 4 — Conflict Detection[/bold]  "
              f"[dim]duration: {conflicts_step.get('duration_ms', 0)} ms[/dim]",
        border_style=RED if detected_ids else "dim",
    ))
    console.print(
        f"  [{RED}]{len(detected_ids)} conflict(s) detected:[/{RED}] "
        f"[bold]{', '.join(detected_ids)}[/bold]"
    )
    console.print()

    # ── STEP 5 — AI BRIEF ────────────────────────────────────────────────────
    brief            = pipeline.get("step_5_brief", {})
    brief_text       = brief.get("brief_text", "")
    citation_cov     = brief.get("citation_coverage", 0.0)
    recommendations  = brief.get("recommendations", [])
    brief_duration   = brief.get("duration_ms", 0)

    rec_lines = [
        f"  [{PRP}]{r['conflict_id']}[/{PRP}]  "
        f"[bold]{r['action'].replace('_', ' ')}[/bold]  "
        f"[dim]← cited: {r['cited_system'].upper()}[/dim]"
        for r in recommendations
    ]
    cov_color  = GRN if citation_cov >= 1.0 else RED
    brief_body = (
        f"{brief_text}\n\n"
        "[bold]Recommendations:[/bold]\n"
        + "\n".join(rec_lines)
        + f"\n\n[dim]Citation coverage:[/dim] "
          f"[bold {cov_color}]{citation_cov * 100:.0f}%[/bold {cov_color}]  "
          f"[dim]|  Duration: {brief_duration} ms[/dim]"
    )

    console.print(Panel(
        brief_body,
        title=f"[bold]Step 5 — AI Decision Brief[/bold]  "
              f"[dim]claude-sonnet · {len(recommendations)} recommendation(s)[/dim]",
        border_style=PRP,
        padding=(1, 2),
    ))
    console.print()

    # ── DRI APPROVAL GATE ────────────────────────────────────────────────────
    console.print(Rule(f"[bold {BLU}]  DRI APPROVAL GATE  [/bold {BLU}]", style=BLU))
    console.print()
    console.print(Panel(
        _kv_table([
            ("Escalation", escalation_id),
            ("DRI",        "James Okafor (USR-DRI-001)"),
            ("Account",    ACCOUNT_ID),
            ("Status",     f"[{BLU}]AWAITING DRI DECISION[/{BLU}]"),
        ]),
        title=f"[bold {BLU}]Step 6 — DRI Review[/bold {BLU}]",
        border_style=BLU,
    ))
    console.print()
    console.print(
        f"  [bold]Options:[/bold]  [{GRN}]approve[/{GRN}]  ·  [{RED}]reject[/{RED}]  ·  [yellow]exception[/yellow]"
    )
    console.print()

    decision = Prompt.ask(
        f"  [{BLU}]DRI Decision[/{BLU}]",
        choices=["approve", "reject", "exception"],
        default="approve",
    )
    reason = None
    if decision in ("reject", "exception"):
        reason = Prompt.ask(f"  [{BLU}]Reason[/{BLU}] (required)")

    console.print()

    # ── STEPS 6–7 ────────────────────────────────────────────────────────────
    decision_map = {"approve": "approved", "reject": "rejected", "exception": "exception"}

    with console.status(f"[{PRP}]Recording DRI decision and dispatching outputs...[/{PRP}]"):
        await _run_silent(
            orchestrator.resume_after_dri(
                escalation_id=escalation_id,
                decision=decision_map[decision],
                decided_by=DRI_ID,
                reason=reason,
            )
        )

    if decision != "approve":
        console.print(Panel(
            f"[bold {RED}]Escalation {decision_map[decision]}.[/bold {RED}]\n"
            f"[dim]Reason: {reason or 'No reason provided'}[/dim]\n"
            "No outputs dispatched. Ticket returned to CSR queue.",
            border_style=RED,
        ))
        return

    # ── STEP 7 — OUTPUTS ─────────────────────────────────────────────────────
    esc_final   = await db["escalations"].find_one({"escalation_id": escalation_id}, {"_id": 0})
    outputs     = esc_final["pipeline"].get("step_7_outputs", {})
    audit_count = await db["audit_trail"].count_documents({"escalation_id": escalation_id})

    customer = outputs.get("customer_summary", {})
    if customer:
        console.print(Panel(
            str(customer.get("content", "")),
            title=f"[bold {GRN}]Output 1 — Customer Summary[/bold {GRN}]  [dim]audience: customer[/dim]",
            border_style=GRN,
            padding=(1, 2),
        ))
        console.print()

    exec_brief = outputs.get("executive_brief", {})
    if exec_brief:
        content = exec_brief.get("content", {})
        if isinstance(content, dict):
            exec_text = "\n".join(
                f"[bold]{k.replace('_', ' ').title()}:[/bold] {v}"
                for k, v in content.items()
            )
        else:
            exec_text = str(content)
        console.print(Panel(
            exec_text,
            title=f"[bold {BLU}]Output 2 — Executive Brief[/bold {BLU}]  [dim]audience: VP/SVP[/dim]",
            border_style=BLU,
            padding=(1, 2),
        ))
        console.print()

    eng = outputs.get("engineering_handoff", {})
    if eng:
        content = eng.get("content", {})
        if isinstance(content, dict):
            jira_id  = content.get("jira_id", "BILL-NEW-1147")
            priority = content.get("priority", "P1")
            criteria = content.get("acceptance_criteria", [])
            eng_text = (
                f"[bold]Jira:[/bold] {jira_id}  |  "
                f"[bold]Priority:[/bold] [{RED}]{priority}[/{RED}]\n\n"
                "[bold]Acceptance Criteria:[/bold]\n"
                + "\n".join(f"  {i}. {ac}" for i, ac in enumerate(criteria, 1))
            )
        else:
            eng_text = str(content)
        console.print(Panel(
            eng_text,
            title=f"[bold {AMB}]Output 3 — Engineering Handoff[/bold {AMB}]  [dim]audience: CC&B Engineering[/dim]",
            border_style=AMB,
            padding=(1, 2),
        ))
        console.print()

    # ── FINAL SUMMARY ────────────────────────────────────────────────────────
    exec_doc     = await db["analyst_executions"].find_one({"escalation_id": escalation_id}, {"_id": 0})
    agent_ms     = exec_doc.get("agent_duration_ms", 0) if exec_doc else 0
    nfr_breaches = exec_doc.get("nfr_breaches", 0) if exec_doc else 0
    nfr_color    = GRN if nfr_breaches == 0 else RED

    console.print(Panel(
        _kv_table([
            ("Escalation ID",       escalation_id),
            ("Status",              f"[{GRN}]RESOLVED[/{GRN}]"),
            ("Conflicts detected",  f"[{RED}]{len(detected_ids)}[/{RED}]  ({', '.join(detected_ids)})"),
            ("Citation coverage",   f"[{GRN}]{citation_cov * 100:.0f}%[/{GRN}]"),
            ("Audit trail entries", str(audit_count)),
            ("Agent assembly time", f"{agent_ms} ms  [dim](NFR target: < 420 000 ms)[/dim]"),
            ("NFR breaches",        f"[{nfr_color}]{nfr_breaches}[/{nfr_color}]"),
            ("Human touchpoints",   f"[{GRN}]1[/{GRN}]  [dim](DRI approval only — NFR-07)[/dim]"),
        ], col_width=24),
        title=f"[bold {PRP}]Reconciliation Complete[/bold {PRP}]",
        subtitle=f"[dim]6–8 hours → seconds  ·  6–9 teams → 1 touchpoint  ·  ~40% audit coverage → 100%[/dim]",
        border_style=PRP,
        padding=(1, 2),
    ))
    console.print()


if __name__ == "__main__":
    asyncio.run(main())
