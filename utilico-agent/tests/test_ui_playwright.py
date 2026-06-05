"""
Playwright UI tests — Utilico Billing Reconciliation Agent
Spec source: req/utilico_ticket_journey_accenture_v5.html

Test map:
  Group A — Login page (split-panel: role cards → credential auto-fill → Sign in)
  Group B — CSR interface (Raise Ticket + My Tickets)
  Group C — DRI interface (Queue + Brief & Decision)
  Group D — Analyst Manager interface (Health + Audit Trail)
  Group E — End-to-end ticket journey (CSR → pipeline → DRI → resolved)
"""
import re
import time
import pytest
import httpx
from playwright.sync_api import Page, expect

BASE_URL = "http://localhost:8000"
PIPELINE_TIMEOUT = 180_000   # 3 min — step 5 calls Claude API

PIPELINE_SKIP_REASON = (
    "Pipeline did not reach 'awaiting_dri' — ANTHROPIC_API_KEY must be a real key. "
    "Set it in utilico-agent/.env and restart the server."
)


# ── LOGIN HELPER ──────────────────────────────────────────────────────────────
def do_login(page: Page, user_name: str):
    """Select a role card by name, then click Sign in →."""
    page.goto(BASE_URL)
    page.locator(".role-card", has_text=user_name).click()
    page.locator("button.btn-signin").click()


# ─────────────────────────────────────────────────────────────────────────────
# GROUP A — LOGIN PAGE
# ─────────────────────────────────────────────────────────────────────────────

class TestLogin:
    """Split-panel login: role cards on left, credentials on right (req: role-based login)."""

    def test_login_page_loads(self, page: Page):
        page.goto(BASE_URL)
        expect(page.locator("text=UTILICO ENERGY")).to_be_visible()
        expect(page.locator("text=Select your role")).to_be_visible()

    def test_three_role_cards_visible(self, page: Page):
        page.goto(BASE_URL)
        # Verify all 3 role cards are present by name
        expect(page.locator(".role-card", has_text="Sarah Chen")).to_be_visible()
        expect(page.locator(".role-card", has_text="James Okafor")).to_be_visible()
        expect(page.locator(".role-card", has_text="Priya Nair")).to_be_visible()

    def test_role_cards_show_user_names(self, page: Page):
        """Each card must display the named user (persona-level identity)."""
        page.goto(BASE_URL)
        expect(page.locator(".role-card-name", has_text="Sarah Chen")).to_be_visible()
        expect(page.locator(".role-card-name", has_text="James Okafor")).to_be_visible()
        expect(page.locator(".role-card-name", has_text="Priya Nair")).to_be_visible()

    def test_role_tags_visible(self, page: Page):
        """Role tags (CSR, DRI, SUP) must appear on the role cards."""
        page.goto(BASE_URL)
        csr_card  = page.locator(".role-card", has_text="Sarah Chen")
        dri_card  = page.locator(".role-card", has_text="James Okafor")
        sup_card  = page.locator(".role-card", has_text="Priya Nair")
        expect(csr_card.locator(".role-tag")).to_be_visible()
        expect(dri_card.locator(".role-tag")).to_be_visible()
        expect(sup_card.locator(".role-tag")).to_be_visible()

    def test_sign_in_button_disabled_before_role_selected(self, page: Page):
        """Sign in button must be disabled until a role is selected (spec: credentials pre-fill)."""
        page.goto(BASE_URL)
        signin_btn = page.locator("button.btn-signin")
        expect(signin_btn).to_be_disabled()

    def test_selecting_role_enables_sign_in(self, page: Page):
        """Clicking a role card must enable the Sign in button."""
        page.goto(BASE_URL)
        page.locator(".role-card", has_text="Sarah Chen").click()
        signin_btn = page.locator("button.btn-signin")
        expect(signin_btn).to_be_enabled(timeout=3_000)

    def test_selecting_role_autofills_email(self, page: Page):
        """Selecting a role must auto-fill the email (spec: credential pre-fill pattern)."""
        page.goto(BASE_URL)
        page.locator(".role-card", has_text="Sarah Chen").click()
        email_input = page.locator("#login-email")
        expect(email_input).to_have_value(re.compile(r"sarah\.chen@", re.IGNORECASE), timeout=3_000)

    def test_selecting_role_autofills_password(self, page: Page):
        """Selecting a role must auto-fill the password field."""
        page.goto(BASE_URL)
        page.locator(".role-card", has_text="James Okafor").click()
        expect(page.locator("#login-pw")).to_have_value("password123", timeout=3_000)

    def test_selected_role_card_gets_highlight(self, page: Page):
        """Selected role card must get the .selected CSS class."""
        page.goto(BASE_URL)
        card = page.locator(".role-card", has_text="James Okafor")
        card.click()
        expect(card).to_have_class(re.compile(r"selected"), timeout=3_000)

    def test_signing_in_hint_updates(self, page: Page):
        """'Signing in as…' hint on the right panel must update after selecting a role."""
        page.goto(BASE_URL)
        page.locator(".role-card", has_text="Priya Nair").click()
        expect(page.locator(".login-role-hint")).to_contain_text("Priya Nair", timeout=3_000)

    def test_role_access_matrix_visible(self, page: Page):
        """Role Access Matrix section must be visible (spec: three role descriptions)."""
        page.goto(BASE_URL)
        expect(page.locator("text=Role Access Matrix")).to_be_visible()

    def test_csr_login_navigates_to_csr_interface(self, page: Page):
        do_login(page, "Sarah Chen")
        expect(page.locator("button.nav-tab", has_text="Raise Ticket")).to_be_visible(timeout=5_000)
        expect(page.locator("button.nav-tab", has_text="My Tickets")).to_be_visible()

    def test_dri_login_navigates_to_dri_interface(self, page: Page):
        do_login(page, "James Okafor")
        expect(page.locator("button.nav-tab", has_text="Queue")).to_be_visible(timeout=5_000)
        expect(page.locator("button.nav-tab", has_text="Brief & Decision")).to_be_visible()

    def test_analyst_manager_login_navigates_to_am_interface(self, page: Page):
        do_login(page, "Priya Nair")
        expect(page.locator("button.nav-tab", has_text="Health Dashboard")).to_be_visible(timeout=5_000)
        expect(page.locator("button.nav-tab", has_text="Audit Trail")).to_be_visible()

    def test_navbar_shows_user_name_after_login(self, page: Page):
        """Navbar must display the logged-in user's name and role tag."""
        do_login(page, "Sarah Chen")
        nav = page.locator(".navbar")
        expect(nav).to_contain_text("Sarah Chen", timeout=5_000)

    def test_sign_out_returns_to_login(self, page: Page):
        do_login(page, "Sarah Chen")
        expect(page.locator("button.nav-tab", has_text="Raise Ticket")).to_be_visible(timeout=5_000)
        page.locator("button.btn-logout").click()
        expect(page.locator("text=UTILICO ENERGY")).to_be_visible(timeout=5_000)
        expect(page.locator(".role-card", has_text="Sarah Chen")).to_be_visible()


# ─────────────────────────────────────────────────────────────────────────────
# GROUP B — CSR INTERFACE
# Spec: Screen 1 = Raise Ticket, Screen 2 = My Tickets + status badges
# ─────────────────────────────────────────────────────────────────────────────

class TestCSRInterface:
    """CSR must see Raise Ticket form with correct fields and My Tickets with status badges."""

    @pytest.fixture(autouse=True)
    def login_as_csr(self, page: Page):
        do_login(page, "Sarah Chen")
        yield

    # ── Screen 1: Raise New Ticket ──────────────────────────────────────────

    def test_raise_ticket_tab_is_default(self, page: Page):
        # Screen header uses amber label "SCREEN 1 — RAISE NEW TICKET"
        expect(page.locator("text=Screen 1 — Raise New Ticket")).to_be_visible(timeout=5_000)

    def test_raise_ticket_has_account_field(self, page: Page):
        expect(page.locator("select#account_id")).to_be_visible()

    def test_raise_ticket_account_dropdown_contains_test_accounts(self, page: Page):
        options = page.locator("select#account_id option").all_text_contents()
        assert any("UTL-00421937" in o for o in options), "UTL-00421937 not in Account dropdown"

    def test_raise_ticket_has_dispute_type_dropdown(self, page: Page):
        expect(page.locator("select#dispute_type")).to_be_visible()
        options = page.locator("select#dispute_type option").all_text_contents()
        assert any("disconnect" in o.lower() for o in options)

    def test_raise_ticket_has_notes_textarea(self, page: Page):
        expect(page.locator("textarea#notes")).to_be_visible()

    def test_raise_ticket_submit_button_text(self, page: Page):
        """Submit button must say 'Submit — Trigger Analyst' (spec: exact label)."""
        btn = page.locator("button", has_text=re.compile(r"Submit.*Trigger Analyst", re.IGNORECASE))
        expect(btn).to_be_visible()

    def test_raise_ticket_submit_shows_confirmation(self, page: Page):
        page.select_option("select#account_id", "UTL-00421937")
        page.select_option("select#dispute_type", "billing_after_disconnect")
        page.fill("textarea#notes", "Playwright test — raise ticket confirmation")
        page.click("button:has-text('Submit')")
        expect(page.locator("#msg")).to_contain_text("ESC-", timeout=10_000)

    def test_raise_ticket_confirmation_mentions_dri(self, page: Page):
        """Confirmation must mention DRI assigned (FR-10, BR-01)."""
        page.select_option("select#account_id", "UTL-00421937")
        page.select_option("select#dispute_type", "billing_after_disconnect")
        page.click("button:has-text('Submit')")
        expect(page.locator("#msg")).to_contain_text(
            re.compile(r"DRI", re.IGNORECASE), timeout=10_000
        )

    def test_on_submit_note_visible(self, page: Page):
        """Footer note 'On submit: DRI assigned…' must appear below the button (spec)."""
        expect(page.locator("text=On submit")).to_be_visible()

    # ── Screen 2: My Tickets ────────────────────────────────────────────────

    def test_my_tickets_tab_navigates_to_list(self, page: Page):
        page.click("button.nav-tab:has-text('My Tickets')")
        expect(page.locator("#tickets-body")).to_be_visible(timeout=8_000)

    def test_my_tickets_shows_ticket_after_submit(self, page: Page):
        page.select_option("select#account_id", "UTL-00421937")
        page.fill("textarea#notes", "Test — my tickets visibility")
        page.click("button:has-text('Submit')")
        expect(page.locator("#msg")).to_contain_text("ESC-", timeout=10_000)
        page.click("button.nav-tab:has-text('My Tickets')")
        expect(page.locator("#tickets-body")).to_contain_text("UTL-00421937", timeout=10_000)

    def test_my_tickets_shows_status_flow_footer(self, page: Page):
        """Status flow text must appear at the bottom of My Tickets (spec: footer text)."""
        page.click("button.nav-tab:has-text('My Tickets')")
        # Submit a ticket first so the list renders (which shows the footer)
        page.click("button.nav-tab:has-text('Raise Ticket')")
        page.locator("select#account_id").select_option("UTL-00421937")
        page.click("button:has-text('Submit')")
        expect(page.locator("#msg")).to_contain_text("ESC-", timeout=10_000)
        page.click("button.nav-tab:has-text('My Tickets')")
        expect(page.locator("#tickets-body")).to_contain_text(
            re.compile(r"Analysing.*Awaiting DRI.*Approved.*Rejected.*Resolved", re.DOTALL),
            timeout=10_000,
        )

    def test_my_tickets_shows_account_id_in_row(self, page: Page):
        page.select_option("select#account_id", "UTL-00421937")
        page.click("button:has-text('Submit')")
        expect(page.locator("#msg")).to_contain_text("ESC-", timeout=10_000)
        page.click("button.nav-tab:has-text('My Tickets')")
        expect(page.locator("#tickets-body")).to_contain_text("UTL-00421937", timeout=10_000)

    def test_analysing_badge_visible_after_submit(self, page: Page):
        """Right after submit the ticket should show Analysing or Initiated badge."""
        page.select_option("select#account_id", "UTL-00421937")
        page.click("button:has-text('Submit')")
        expect(page.locator("#msg")).to_contain_text("ESC-", timeout=10_000)
        page.click("button.nav-tab:has-text('My Tickets')")
        body = page.locator("#tickets-body")
        expect(body).to_be_visible(timeout=8_000)
        early_badge = body.locator(".badge-analysing, .badge-initiated").first
        expect(early_badge).to_be_visible(timeout=12_000)


# ─────────────────────────────────────────────────────────────────────────────
# GROUP C — DRI INTERFACE
# Spec: Screen 1 = Queue (NEW badge, Review →), Screen 2 = Brief + Approve/Reject
# ─────────────────────────────────────────────────────────────────────────────

class TestDRIInterface:
    """DRI must see their queue, the NEW badge, the brief, and be able to approve or reject."""

    @pytest.fixture(autouse=True)
    def login_as_dri(self, page: Page):
        do_login(page, "James Okafor")
        yield

    @pytest.fixture(autouse=True)
    def require_pipeline(self, escalation_awaiting_dri, request):
        """Skip pipeline-dependent tests when API key is placeholder."""
        pipeline_tests = {
            "test_queue_shows_awaiting_dri_new_badge",
            "test_queue_shows_review_button_for_awaiting_dri",
            "test_review_button_opens_brief_screen",
            "test_brief_screen_shows_escalation_id",
            "test_brief_screen_shows_account_id",
            "test_brief_screen_shows_awaiting_dri_status_badge",
            "test_brief_screen_shows_conflicts_table",
            "test_brief_screen_shows_conflict_system_pairs",
            "test_brief_screen_shows_conflict_badges",
            "test_brief_screen_shows_ai_brief_text",
            "test_brief_shows_citation_coverage",
            "test_brief_screen_shows_recommendations",
            "test_brief_screen_has_approve_button",
            "test_brief_screen_has_reject_button",
            "test_brief_screen_has_exception_button",
            "test_reject_requires_reason_field",
            "test_dri_approve_records_decision",
            "test_approve_dispatches_outputs",
        }
        if request.node.originalname in pipeline_tests and escalation_awaiting_dri is None:
            pytest.skip(PIPELINE_SKIP_REASON)

    def test_queue_tab_is_default(self, page: Page):
        expect(page.locator("button.nav-tab", has_text="Queue")).to_be_visible()
        expect(page.locator("#queue-body")).to_be_visible(timeout=8_000)

    def test_brief_decision_tab_navigates(self, page: Page):
        page.click("button.nav-tab:has-text('Brief & Decision')")
        expect(page.locator("#brief-body")).to_be_visible(timeout=8_000)

    def test_brief_tab_shows_prompt_when_no_escalation_selected(self, page: Page):
        """When no escalation is selected the brief tab should tell the user to use the Queue."""
        page.click("button.nav-tab:has-text('Brief & Decision')")
        expect(page.locator("#brief-body")).to_contain_text(
            re.compile(r"select.*queue|queue.*tab", re.IGNORECASE), timeout=8_000
        )

    def test_queue_shows_awaiting_dri_new_badge(self, page: Page, escalation_awaiting_dri: str):
        """Awaiting-DRI tickets must show a NEW badge in the DRI queue (spec: Screen 1)."""
        page.reload()
        do_login(page, "James Okafor")
        queue_body = page.locator("#queue-body")
        expect(queue_body).to_contain_text(escalation_awaiting_dri, timeout=8_000)
        expect(queue_body.locator(".badge-new", has_text="NEW").first).to_be_visible(timeout=5_000)

    def test_queue_shows_review_button_for_awaiting_dri(self, page: Page, escalation_awaiting_dri: str):
        page.reload()
        do_login(page, "James Okafor")
        queue_body = page.locator("#queue-body")
        expect(queue_body).to_contain_text(escalation_awaiting_dri, timeout=8_000)
        expect(queue_body.locator("button:has-text('Review')").first).to_be_visible()

    def test_review_button_opens_brief_screen(self, page: Page, escalation_awaiting_dri: str):
        page.reload()
        do_login(page, "James Okafor")
        page.locator("#queue-body").locator("button:has-text('Review')").first.click(timeout=8_000)
        expect(page.locator("#brief-body")).to_be_visible(timeout=8_000)

    def test_brief_screen_shows_escalation_id(self, page: Page, escalation_awaiting_dri: str):
        page.reload()
        do_login(page, "James Okafor")
        page.locator("#queue-body").locator("button:has-text('Review')").first.click(timeout=8_000)
        expect(page.locator("#brief-body")).to_contain_text(escalation_awaiting_dri, timeout=8_000)

    def test_brief_screen_shows_account_id(self, page: Page, escalation_awaiting_dri: str):
        page.reload()
        do_login(page, "James Okafor")
        page.locator("#queue-body").locator("button:has-text('Review')").first.click(timeout=8_000)
        expect(page.locator("#brief-body")).to_contain_text("UTL-00421937", timeout=8_000)

    def test_brief_screen_shows_awaiting_dri_status_badge(self, page: Page, escalation_awaiting_dri: str):
        page.reload()
        do_login(page, "James Okafor")
        page.locator("#queue-body").locator("button:has-text('Review')").first.click(timeout=8_000)
        expect(page.locator("#brief-body").locator(".badge-awaiting")).to_be_visible(timeout=8_000)

    def test_brief_screen_shows_conflicts_table(self, page: Page, escalation_awaiting_dri: str):
        """Conflicts table must be visible with C1–C4 (spec: 4 conflicts detected block)."""
        page.reload()
        do_login(page, "James Okafor")
        page.locator("#queue-body").locator("button:has-text('Review')").first.click(timeout=8_000)
        brief = page.locator("#brief-body")
        expect(brief).to_contain_text("Conflict Detection", timeout=8_000)
        for cid in ("C1", "C2", "C3", "C4"):
            expect(brief).to_contain_text(cid, timeout=5_000)

    def test_brief_screen_shows_conflict_system_pairs(self, page: Page, escalation_awaiting_dri: str):
        """Conflicts must name the system pairs (OMS↔CCB, MDM↔OMS, CRM↔CCB, GL↔CRM)."""
        page.reload()
        do_login(page, "James Okafor")
        page.locator("#queue-body").locator("button:has-text('Review')").first.click(timeout=8_000)
        brief = page.locator("#brief-body")
        for sys_name in ("OMS", "CCB", "MDM", "CRM", "GL"):
            expect(brief).to_contain_text(sys_name, timeout=5_000)

    def test_brief_screen_shows_conflict_badges(self, page: Page, escalation_awaiting_dri: str):
        page.reload()
        do_login(page, "James Okafor")
        page.locator("#queue-body").locator("button:has-text('Review')").first.click(timeout=8_000)
        brief = page.locator("#brief-body")
        expect(brief.locator(".badge-conflict").first).to_be_visible(timeout=8_000)

    def test_brief_screen_shows_ai_brief_text(self, page: Page, escalation_awaiting_dri: str):
        """Brief box must contain the AI-generated text (spec: 100% citation coverage)."""
        page.reload()
        do_login(page, "James Okafor")
        page.locator("#queue-body").locator("button:has-text('Review')").first.click(timeout=8_000)
        brief = page.locator("#brief-body")
        expect(brief).to_contain_text("Decision-Ready Brief", timeout=8_000)
        brief_box = brief.locator(".brief-box")
        expect(brief_box).to_be_visible()
        assert len(brief_box.inner_text().strip()) > 50

    def test_brief_shows_citation_coverage(self, page: Page, escalation_awaiting_dri: str):
        """Citation coverage must be shown as 100% (NFR-02)."""
        page.reload()
        do_login(page, "James Okafor")
        page.locator("#queue-body").locator("button:has-text('Review')").first.click(timeout=8_000)
        brief = page.locator("#brief-body")
        expect(brief).to_contain_text(re.compile(r"citation coverage", re.IGNORECASE), timeout=8_000)
        expect(brief).to_contain_text("100%")

    def test_brief_screen_shows_recommendations(self, page: Page, escalation_awaiting_dri: str):
        page.reload()
        do_login(page, "James Okafor")
        page.locator("#queue-body").locator("button:has-text('Review')").first.click(timeout=8_000)
        expect(page.locator("#brief-body")).to_contain_text("Recommendations", timeout=8_000)

    def test_brief_screen_has_approve_button(self, page: Page, escalation_awaiting_dri: str):
        page.reload()
        do_login(page, "James Okafor")
        page.locator("#queue-body").locator("button:has-text('Review')").first.click(timeout=8_000)
        expect(page.locator("#brief-body").locator("button.btn-approve")).to_be_visible(timeout=8_000)

    def test_brief_screen_has_reject_button(self, page: Page, escalation_awaiting_dri: str):
        page.reload()
        do_login(page, "James Okafor")
        page.locator("#queue-body").locator("button:has-text('Review')").first.click(timeout=8_000)
        expect(page.locator("#brief-body").locator("button.btn-reject")).to_be_visible(timeout=8_000)

    def test_brief_screen_has_exception_button(self, page: Page, escalation_awaiting_dri: str):
        page.reload()
        do_login(page, "James Okafor")
        page.locator("#queue-body").locator("button:has-text('Review')").first.click(timeout=8_000)
        expect(page.locator("#brief-body").locator("button.btn-exception")).to_be_visible(timeout=8_000)

    def test_reject_requires_reason_field(self, page: Page, escalation_awaiting_dri: str):
        """Clicking Reject must reveal a reason textarea (spec: rejection reason required)."""
        page.reload()
        do_login(page, "James Okafor")
        page.locator("#queue-body").locator("button:has-text('Review')").first.click(timeout=8_000)
        page.locator("#brief-body").locator("button.btn-reject").click()
        expect(page.locator("#decision-reason")).to_be_visible(timeout=5_000)

    def test_dri_approve_records_decision(self, page: Page, escalation_awaiting_dri: str):
        """Approve must record the decision and show success (FR-09, FR-07)."""
        page.reload()
        do_login(page, "James Okafor")
        page.locator("#queue-body").locator("button:has-text('Review')").first.click(timeout=8_000)
        brief = page.locator("#brief-body")
        expect(brief.locator("button.btn-approve")).to_be_visible(timeout=8_000)
        brief.locator("button.btn-approve").click()
        expect(page.locator("#decision-msg")).to_contain_text(
            re.compile(r"approved|decision recorded", re.IGNORECASE), timeout=30_000
        )

    def test_approve_dispatches_outputs(self, page: Page, escalation_awaiting_dri: str):
        """After approval the 3 outputs must appear (customer, executive, engineering)."""
        r = httpx.get(f"{BASE_URL}/csr/tickets/detail/{escalation_awaiting_dri}", timeout=10)
        if r.status_code == 200:
            pipeline = r.json().get("pipeline", {})
            outputs = pipeline.get("step_7_outputs")
            if outputs and outputs.get("customer_summary"):
                assert outputs["customer_summary"]["content"]
                return

        page.reload()
        do_login(page, "James Okafor")
        queue_body = page.locator("#queue-body")
        review_btns = queue_body.locator("button:has-text('Review')")
        if review_btns.count() == 0:
            pytest.skip("Escalation already approved")

        review_btns.first.click()
        brief = page.locator("#brief-body")
        expect(brief.locator("button.btn-approve")).to_be_visible(timeout=8_000)
        brief.locator("button.btn-approve").click()
        outputs_section = page.locator("#outputs-section")
        expect(outputs_section).to_be_visible(timeout=30_000)
        expect(outputs_section).to_contain_text(
            re.compile(r"Customer Summary", re.IGNORECASE), timeout=20_000
        )
        expect(outputs_section).to_contain_text(
            re.compile(r"Executive Brief", re.IGNORECASE), timeout=10_000
        )
        expect(outputs_section).to_contain_text(
            re.compile(r"Engineering Handoff", re.IGNORECASE), timeout=10_000
        )


# ─────────────────────────────────────────────────────────────────────────────
# GROUP D — ANALYST MANAGER INTERFACE
# Spec: Screen 1 = Health Dashboard (8 KPIs), Screen 2 = Audit Trail (filterable)
# ─────────────────────────────────────────────────────────────────────────────

class TestAnalystManagerInterface:
    """Analyst Manager must see KPI cards, recent executions, and a filterable audit trail."""

    @pytest.fixture(autouse=True)
    def login_as_am(self, page: Page):
        do_login(page, "Priya Nair")
        yield

    @pytest.fixture(autouse=True)
    def require_pipeline(self, escalation_awaiting_dri):
        if escalation_awaiting_dri is None:
            pytest.skip(PIPELINE_SKIP_REASON)

    def test_health_dashboard_tab_is_default(self, page: Page, escalation_awaiting_dri):
        expect(page.locator("button.nav-tab", has_text="Health Dashboard")).to_be_visible()
        expect(page.locator("#health-body")).to_be_visible(timeout=8_000)

    def test_health_dashboard_shows_avg_assembly_time(self, page: Page, escalation_awaiting_dri):
        expect(page.locator("#health-body")).to_contain_text(
            re.compile(r"avg assembly time", re.IGNORECASE), timeout=8_000
        )

    def test_health_dashboard_shows_nfr_compliance(self, page: Page, escalation_awaiting_dri):
        expect(page.locator("#health-body")).to_contain_text(
            re.compile(r"nfr.01 compliance", re.IGNORECASE), timeout=8_000
        )

    def test_health_dashboard_shows_audit_completeness(self, page: Page, escalation_awaiting_dri):
        expect(page.locator("#health-body")).to_contain_text(
            re.compile(r"audit completeness", re.IGNORECASE), timeout=8_000
        )

    def test_health_dashboard_shows_dri_backlog(self, page: Page, escalation_awaiting_dri):
        expect(page.locator("#health-body")).to_contain_text(
            re.compile(r"dri backlog", re.IGNORECASE), timeout=8_000
        )

    def test_health_dashboard_shows_regulatory_consistency(self, page: Page, escalation_awaiting_dri):
        expect(page.locator("#health-body")).to_contain_text(
            re.compile(r"regulatory consistency", re.IGNORECASE), timeout=8_000
        )

    def test_health_dashboard_shows_eight_metric_cards(self, page: Page, escalation_awaiting_dri):
        expect(page.locator(".metric-card")).to_have_count(8, timeout=8_000)

    def test_health_dashboard_shows_recent_executions_section(self, page: Page, escalation_awaiting_dri):
        expect(page.locator("#health-body")).to_contain_text(
            re.compile(r"recent executions", re.IGNORECASE), timeout=8_000
        )

    def test_health_dashboard_execution_row_shows_account(self, page: Page, escalation_awaiting_dri):
        expect(page.locator("#health-body")).to_contain_text("UTL-00421937", timeout=8_000)

    def test_health_dashboard_execution_row_shows_conflicts_count(self, page: Page, escalation_awaiting_dri):
        health = page.locator("#health-body")
        expect(health.locator("td", has_text=re.compile(r"[1-9]")).first).to_be_visible(timeout=8_000)

    def test_audit_trail_tab_loads(self, page: Page, escalation_awaiting_dri):
        page.click("button.nav-tab:has-text('Audit Trail')")
        expect(page.locator("#audit-body")).to_be_visible(timeout=8_000)
        expect(page.locator("select#f-system")).to_be_visible()
        expect(page.locator("select#f-claim")).to_be_visible()

    def test_audit_trail_has_query_button(self, page: Page, escalation_awaiting_dri):
        page.click("button.nav-tab:has-text('Audit Trail')")
        expect(page.locator("button:has-text('Query')")).to_be_visible()

    def test_audit_trail_query_returns_results(self, page: Page, escalation_awaiting_dri):
        page.click("button.nav-tab:has-text('Audit Trail')")
        page.click("button:has-text('Query')")
        audit_body = page.locator("#audit-body")
        expect(audit_body).to_contain_text(escalation_awaiting_dri, timeout=10_000)

    def test_audit_trail_rows_show_source_system(self, page: Page, escalation_awaiting_dri):
        page.click("button.nav-tab:has-text('Audit Trail')")
        page.click("button:has-text('Query')")
        audit_body = page.locator("#audit-body")
        systems_found = False
        for sys in ("OMS", "MDM", "CCB", "CRM", "GL"):
            try:
                if audit_body.locator("td", has_text=sys).first.is_visible(timeout=3_000):
                    systems_found = True
                    break
            except Exception:
                pass
        assert systems_found, "No source system names found in audit trail rows"

    def test_audit_trail_filter_by_system(self, page: Page, escalation_awaiting_dri):
        page.click("button.nav-tab:has-text('Audit Trail')")
        page.select_option("select#f-system", "oms")
        page.click("button:has-text('Query')")
        expect(page.locator("#audit-body")).to_contain_text("OMS", timeout=10_000)

    def test_audit_trail_filter_by_claim_type(self, page: Page, escalation_awaiting_dri):
        page.click("button.nav-tab:has-text('Audit Trail')")
        page.select_option("select#f-claim", "conflict")
        page.click("button:has-text('Query')")
        expect(page.locator("#audit-body")).not_to_contain_text(
            re.compile(r"^error", re.IGNORECASE), timeout=8_000
        )

    def test_audit_trail_actor_column_visible(self, page: Page, escalation_awaiting_dri):
        page.click("button.nav-tab:has-text('Audit Trail')")
        page.click("button:has-text('Query')")
        expect(page.locator("#audit-body")).to_contain_text(
            re.compile(r"analyst_agent|dri|system", re.IGNORECASE), timeout=10_000
        )


# ─────────────────────────────────────────────────────────────────────────────
# GROUP E — END-TO-END TICKET JOURNEY
# Spec: CSR submits → Analysing → Awaiting DRI → Approved → Resolved
# ─────────────────────────────────────────────────────────────────────────────

class TestEndToEndJourney:
    """Full ticket journey — mirrors 'After — Agentic' column in the ticket journey spec."""

    @pytest.fixture(autouse=True)
    def require_pipeline(self, escalation_awaiting_dri):
        if escalation_awaiting_dri is None:
            pytest.skip(PIPELINE_SKIP_REASON)

    def test_full_journey_csr_to_resolved(self, page: Page, escalation_awaiting_dri: str):
        """
        1. CSR sees ticket with Awaiting DRI status.
        2. DRI sees NEW badge and Review button.
        3. DRI approves → escalation becomes resolved.
        4. CSR can see Resolved status.
        Spec: CSR submits → Analysing → Awaiting DRI → Approved → Resolved
        """
        # ─ Step 1: CSR sees awaiting_dri ─────────────────────────────────────
        do_login(page, "Sarah Chen")
        page.click("button.nav-tab:has-text('My Tickets')")
        tickets_body = page.locator("#tickets-body")
        expect(tickets_body).to_contain_text(escalation_awaiting_dri, timeout=10_000)
        expect(tickets_body.locator(".badge-awaiting").first).to_be_visible(timeout=5_000)

        # ─ Step 2: DRI sees NEW badge and Review button ───────────────────────
        page.locator("button.btn-logout").click()
        do_login(page, "James Okafor")
        queue_body = page.locator("#queue-body")
        expect(queue_body).to_contain_text(escalation_awaiting_dri, timeout=8_000)
        expect(queue_body.locator(".badge-new").first).to_be_visible(timeout=5_000)
        review_btn = queue_body.locator("button:has-text('Review')").first
        expect(review_btn).to_be_visible()

        # ─ Step 3: DRI approves ───────────────────────────────────────────────
        review_btn.click()
        brief = page.locator("#brief-body")
        expect(brief.locator("button.btn-approve")).to_be_visible(timeout=8_000)
        brief.locator("button.btn-approve").click()
        expect(page.locator("#decision-msg")).to_contain_text(
            re.compile(r"approved|decision recorded", re.IGNORECASE), timeout=30_000
        )

        # ─ Step 4: CSR sees Resolved ──────────────────────────────────────────
        page.locator("button.btn-logout").click()
        do_login(page, "Sarah Chen")
        page.click("button.nav-tab:has-text('My Tickets')")
        tickets_body = page.locator("#tickets-body")
        expect(tickets_body.locator(".badge-resolved").first).to_be_visible(timeout=20_000)

    def test_rejected_ticket_shows_rejected_badge(self, page: Page):
        """DRI reject → CSR sees Rejected badge. Spec: Rejected → Back to CSR."""
        httpx.get(f"{BASE_URL}/seed", timeout=15)

        do_login(page, "Sarah Chen")
        page.select_option("select#account_id", "UTL-00389204")
        page.select_option("select#dispute_type", "billing_after_disconnect")
        page.fill("textarea#notes", "E2E reject test")
        page.click("button:has-text('Submit')")
        msg = page.locator("#msg")
        expect(msg).to_contain_text("ESC-", timeout=10_000)
        esc_id = re.search(r"ESC-\d+", msg.inner_text()).group()

        deadline = time.time() + 180
        reached = False
        while time.time() < deadline:
            try:
                r2 = httpx.get(f"{BASE_URL}/csr/tickets/detail/{esc_id}", timeout=5)
                if r2.status_code == 200 and r2.json().get("status") == "awaiting_dri":
                    reached = True; break
            except Exception:
                pass
            time.sleep(3)
        if not reached:
            pytest.skip(f"Pipeline did not reach awaiting_dri for {esc_id}")

        page.locator("button.btn-logout").click()
        do_login(page, "James Okafor")
        queue_body = page.locator("#queue-body")
        expect(queue_body).to_contain_text(esc_id, timeout=8_000)
        queue_body.locator("button:has-text('Review')").first.click()

        brief = page.locator("#brief-body")
        expect(brief.locator("button.btn-reject")).to_be_visible(timeout=8_000)
        brief.locator("button.btn-reject").click()
        page.fill("#decision-reason", "Test rejection — insufficient evidence")
        page.locator("#brief-body .confirm-btn").click()
        expect(page.locator("#decision-msg")).to_contain_text(
            re.compile(r"rejected|decision recorded", re.IGNORECASE), timeout=30_000
        )

        page.locator("button.btn-logout").click()
        do_login(page, "Sarah Chen")
        page.click("button.nav-tab:has-text('My Tickets')")
        tickets_body = page.locator("#tickets-body")
        expect(tickets_body).to_contain_text(esc_id, timeout=8_000)
        expect(tickets_body.locator(".badge-rejected").first).to_be_visible(timeout=10_000)

    def test_analyst_manager_sees_execution_after_resolution(self, page: Page, escalation_awaiting_dri: str):
        """AM must see execution record after full pipeline completes."""
        do_login(page, "Priya Nair")
        health = page.locator("#health-body")
        expect(health).to_be_visible(timeout=8_000)
        expect(health).to_contain_text("UTL-00421937", timeout=8_000)


# ─────────────────────────────────────────────────────────────────────────────
# GROUP F — DRI IN-PROGRESS LIVE VIEW
# When a DRI opens a ticket whose pipeline has not yet produced the brief, the
# panel must show the same live progress view as the CSR side (pipeline step
# timeline + "Analyst working" panel + source-system chips), not a bare message.
# Uses seeded ESC-0002 which is permanently 'analysing' — no LLM dependency.
# ─────────────────────────────────────────────────────────────────────────────

class TestDRIInProgressView:

    @pytest.fixture(autouse=True)
    def seed_and_login(self, page: Page):
        httpx.get(f"{BASE_URL}/seed", timeout=15)  # ESC-0002 seeded as 'analysing'
        do_login(page, "James Okafor")
        page.wait_for_selector("#dri-queue-list", timeout=8_000)
        # Open the still-analysing ticket directly
        page.evaluate("selectDRITicket('ESC-0002')")
        yield

    def test_shows_pipeline_progress_timeline(self, page: Page):
        panel = page.locator("#dri-brief-panel")
        expect(panel).to_contain_text("Pipeline Progress", timeout=8_000)
        expect(panel).to_contain_text("AI Decision Brief")

    def test_shows_analyst_working_panel(self, page: Page):
        panel = page.locator("#dri-brief-panel")
        expect(panel).to_contain_text(re.compile("Analyst working", re.IGNORECASE), timeout=8_000)

    def test_shows_all_five_source_system_chips(self, page: Page):
        panel = page.locator("#dri-brief-panel")
        for system in ("CC&B", "MDM", "OMS", "CRM", "GL"):
            expect(panel).to_contain_text(system, timeout=8_000)

    def test_shows_live_auto_update_note(self, page: Page):
        """The panel must reassure the DRI it auto-updates — no manual refresh."""
        panel = page.locator("#dri-brief-panel")
        expect(panel).to_contain_text(
            re.compile(r"auto-updates|no refresh", re.IGNORECASE), timeout=8_000
        )


# ─────────────────────────────────────────────────────────────────────────────
# GROUP H — DRI BRIEF: AI CONFIDENCE SCORE + NO NORTH STAR ON RIBBON
# Uses seeded ESC-0001 (awaiting_dri, brief ready) — no LLM dependency.
# ─────────────────────────────────────────────────────────────────────────────

class TestDRIBriefConfidence:

    @pytest.fixture(autouse=True)
    def seed_and_open_brief(self, page: Page):
        httpx.get(f"{BASE_URL}/seed", timeout=15)  # ESC-0001 = awaiting_dri with brief
        do_login(page, "James Okafor")
        page.wait_for_selector("#dri-queue-list", timeout=8_000)
        page.evaluate("selectDRITicket('ESC-0001')")
        page.wait_for_timeout(800)
        yield

    def test_brief_shows_ai_confidence_score(self, page: Page):
        panel = page.locator("#dri-brief-panel")
        expect(panel).to_contain_text(re.compile(r"AI Confidence", re.IGNORECASE), timeout=8_000)
        # A percentage score must be rendered alongside the label
        expect(panel).to_contain_text(re.compile(r"\d{2,3}%"))

    def test_ribbon_no_longer_shows_north_star(self, page: Page):
        panel = page.locator("#dri-brief-panel")
        expect(panel).to_contain_text("Resolution time", timeout=8_000)  # ribbon present
        expect(panel).not_to_contain_text(re.compile(r"North Star", re.IGNORECASE))


# ─────────────────────────────────────────────────────────────────────────────
# GROUP G — CSR OUTPUT REVIEW GATE
# After DRI approval the 3 outputs are drafts the CSR must review/edit/approve
# individually before dispatch. Uses seeded ESC-0004 (awaiting_output_review,
# 3 pending_review drafts) — no LLM dependency. Each test reseeds for isolation.
# ─────────────────────────────────────────────────────────────────────────────

SEEDED_REVIEW_ESC = "ESC-0004"


class TestCSROutputReview:

    @pytest.fixture(autouse=True)
    def reseed_login_and_open(self, page: Page):
        httpx.get(f"{BASE_URL}/seed", timeout=15)  # ESC-0004 = awaiting_output_review
        do_login(page, "Sarah Chen")
        page.wait_for_timeout(500)
        page.evaluate(f"showTicketDetail('{SEEDED_REVIEW_ESC}')")
        page.wait_for_selector("#detail-body", timeout=8_000)
        yield

    def test_review_panel_shows_pending_outputs(self, page: Page):
        body = page.locator("#detail-body")
        expect(body).to_contain_text(re.compile(r"CSR Output Review", re.IGNORECASE), timeout=8_000)
        expect(body).to_contain_text("0/3 approved")
        expect(body.get_by_text("Pending review").first).to_be_visible()
        # Three reviewable outputs are offered
        expect(page.get_by_text("Review & Approve")).to_have_count(3)

    def test_editing_a_draft_persists_and_flags_edited(self, page: Page):
        """Editing the customer email before approval persists new content + edited=True."""
        page.get_by_text("Review & Approve").first.click()
        page.wait_for_selector("#rv-customer-what_we_found", timeout=5_000)
        page.fill("#rv-customer-what_we_found", "Edited by CSR in review.")
        page.get_by_role("button", name=re.compile("APPROVE CUSTOMER EMAIL", re.IGNORECASE)).click()
        page.wait_for_timeout(1200)
        cs = httpx.get(f"{BASE_URL}/csr/tickets/detail/{SEEDED_REVIEW_ESC}", timeout=5).json()
        o = cs["pipeline"]["step_7_outputs"]["customer_summary"]
        assert o["review_status"] == "approved"
        assert o["edited"] is True
        assert o["content"]["what_we_found"] == "Edited by CSR in review."

    def test_review_each_output_advances_to_resolved(self, page: Page):
        body = page.locator("#detail-body")
        for approve_label in ("APPROVE CUSTOMER EMAIL", "APPROVE EXECUTIVE BRIEF", "APPROVE ENGINEER TICKET"):
            page.get_by_text("Review & Approve").first.click()
            page.get_by_role("button", name=re.compile(approve_label, re.IGNORECASE)).click()
            page.wait_for_timeout(1200)
        # All approved → resolved + dispatched
        expect(body).to_contain_text(re.compile(r"all approved", re.IGNORECASE), timeout=8_000)
        d = httpx.get(f"{BASE_URL}/csr/tickets/detail/{SEEDED_REVIEW_ESC}", timeout=5).json()
        assert d["status"] == "resolved"
        assert d["pipeline"]["step_7_outputs"]["dispatched_at"] is not None
        for field in ("customer_summary", "executive_brief", "engineering_handoff"):
            o = d["pipeline"]["step_7_outputs"][field]
            assert o["review_status"] == "approved"
            assert o["reviewed_by"] == "USR-CSR-112"
