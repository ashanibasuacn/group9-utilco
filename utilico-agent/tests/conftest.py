"""
Shared fixtures for Playwright UI tests.

Usage:
    pip install playwright pytest-playwright
    playwright install chromium
    cd utilico-agent && uvicorn main:app --reload   # keep this running
    pytest tests/test_ui_playwright.py -v
"""
import time
import pytest
import httpx

BASE_URL = "http://localhost:8000"


def server_is_up() -> bool:
    try:
        return httpx.get(f"{BASE_URL}/health", timeout=3).status_code == 200
    except Exception:
        return False


def wait_for_escalation_status(escalation_id: str, target: str, timeout_s: int = 180) -> bool:
    """Poll the API until the escalation reaches `target` status or timeout."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            r = httpx.get(f"{BASE_URL}/csr/tickets/detail/{escalation_id}", timeout=5)
            if r.status_code == 200 and r.json().get("status") == target:
                return True
        except Exception:
            pass
        time.sleep(3)
    return False


@pytest.fixture(scope="session", autouse=True)
def require_server():
    """Skip all UI tests if the server is not running."""
    if not server_is_up():
        pytest.skip(
            "Utilico server not running at localhost:8000. "
            "Start with: cd utilico-agent && uvicorn main:app --reload"
        )


@pytest.fixture(scope="session")
def base_url():
    return BASE_URL


PIPELINE_SKIP_REASON = (
    "Pipeline did not reach 'awaiting_dri' — ANTHROPIC_API_KEY must be a real key. "
    "Set it in utilico-agent/.env and restart the server."
)


@pytest.fixture(scope="session")
def escalation_awaiting_dri() -> str | None:
    """
    Session-scoped fixture: reseed the DB, raise a ticket, wait for the pipeline
    to complete steps 1-5 (which calls the Claude API).

    Returns the escalation_id string, or None if the pipeline did not complete
    (e.g. placeholder API key). Tests must check for None and skip individually —
    calling pytest.skip() here would cascade and skip the entire session.
    """
    try:
        httpx.get(f"{BASE_URL}/seed", timeout=15)
    except Exception:
        return None

    try:
        r = httpx.post(
            f"{BASE_URL}/csr/tickets",
            json={
                "account_id": "UTL-00421937",
                "csr_id": "USR-CSR-112",
                "dispute_type": "billing_after_disconnect",
                "notes": "Playwright test — post-disconnect billing dispute",
            },
            timeout=10,
        )
    except Exception:
        return None

    if r.status_code != 202:
        return None

    escalation_id = r.json()["escalation_id"]
    reached = wait_for_escalation_status(escalation_id, "awaiting_dri", timeout_s=180)
    return escalation_id if reached else None
