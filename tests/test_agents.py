import pytest

from app.agents.lead import LeadAgent
from app.schemas import LeadDialogState


@pytest.mark.asyncio
async def test_lead_agent_converges():
    agent = LeadAgent(tenant_id=1)
    state = None
    prompts = [
        "I need a deck",
        "Around 200 sqft",
        "Reach me demo@example.com"
    ]
    quote = None
    for text in prompts:
        state, followup, quote = await agent.handle_turn(text, state)
    assert quote is not None
    assert quote["total_low"] < quote["total_high"]


@pytest.mark.asyncio
async def test_lead_agent_followup():
    agent = LeadAgent(tenant_id=1)
    state, followup, quote = await agent.handle_turn("Need something", None)
    assert followup is not None
    assert quote is None
