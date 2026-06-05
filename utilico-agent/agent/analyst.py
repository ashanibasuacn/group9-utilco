"""
Analyst Agent — powered by pydantic-ai + Anthropic Claude.
"""
from __future__ import annotations

from pydantic import BaseModel
from pydantic_ai import Agent

from config import (
    LLM_PROVIDER, MODEL_NAME,
    BEDROCK_MODEL_ID, AWS_REGION, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY,
)
from models.escalation import Recommendation


class BriefResult(BaseModel):
    """Structured output from the analyst agent."""
    recommendations: list[Recommendation]
    brief_text: str
    confidence_signal: str | None = None
    citation_coverage: float  # must be 1.0


_SYSTEM_PROMPT = """
You are The Analyst — an AI billing reconciliation agent for Utilico Energy.

Your job:
1. Review reconciliation evidence and detected conflicts
2. Generate a specific recommended action for each DETECTED conflict, citing exact source system
3. Write a concise decision-ready context brief — factual, cited, actionable
4. Achieve 100% citation coverage — every claim must cite source system in square brackets

Conflict → Action mapping (apply exactly for detected conflicts):
- C1 (OMS↔CC&B): Suppress post-disconnect portion; issue prorated credit [OMS]
- C2 (MDM↔OMS): Flag phantom consumption; adjust MDM reads to zero for post-disconnect days [MDM]
- C3 (CRM↔CC&B): Link CRM complaint; apply billing-hold flag; trigger review [CRM]
- C4 (GL↔CRM): Generate credit note; flag GL for revenue adjustment and regulatory filing [GL]

Brief format:
"{Account type} customer billed {billing description} [CC&B]. {Disconnect detail} [OMS]. {Read detail} [MDM]. {Complaint detail} [CRM]. {Revenue detail} [GL]. Recommend: {actions}."

Rules:
- citation_coverage must be 1.0 — only set this if every single claim cites a source system
- Only include recommendations for DETECTED conflicts (detected=true)
- Never silently resolve a conflict
- Set confidence_signal if data is incomplete or ambiguous, otherwise leave null
- The brief_text must include square bracket citations for every factual claim
- Return valid JSON matching the BriefResult schema
"""

_agent: Agent | None = None


def _build_model():
    """Build the LLM model for the configured provider (Bedrock or direct Anthropic)."""
    if LLM_PROVIDER == "bedrock":
        from pydantic_ai.models.bedrock import BedrockConverseModel
        from pydantic_ai.providers.bedrock import BedrockProvider
        provider = BedrockProvider(
            region_name=AWS_REGION,
            aws_access_key_id=AWS_ACCESS_KEY_ID or None,
            aws_secret_access_key=AWS_SECRET_ACCESS_KEY or None,
        )
        return BedrockConverseModel(BEDROCK_MODEL_ID, provider=provider)

    from pydantic_ai.models.anthropic import AnthropicModel
    return AnthropicModel(MODEL_NAME)


def get_analyst_agent() -> Agent:
    """Lazy-initialise the agent so import doesn't require credentials at startup."""
    global _agent
    if _agent is None:
        _agent = Agent(
            model=_build_model(),
            output_type=BriefResult,
            system_prompt=_SYSTEM_PROMPT,
        )
    return _agent
