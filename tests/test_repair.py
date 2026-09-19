"""Tests for the repair loop: withhold-on-second-failure is the default."""
import pytest

from app.alerts import AlertManager
from app.pipeline import PolicyRefusal, translate_policied
from app.policy import compile_policy
from app.provider import ProviderRouter


class LeakyRouter(ProviderRouter):
    """Always returns output containing a deny term, ignoring the prompt."""

    def __init__(self):
        super().__init__(providers=[])
        self.calls = 0

    async def translate(self, masked_text, system_prompt, force=None):
        self.calls += 1
        return "send game chips", "stub"


class CleanRouter(ProviderRouter):
    def __init__(self):
        super().__init__(providers=[])
        self.calls = 0

    async def translate(self, masked_text, system_prompt, force=None):
        self.calls += 1
        return "send ⟦T:balance⟧", "stub"


@pytest.fixture(scope="module")
def policy():
    return compile_policy(1)


@pytest.mark.asyncio
async def test_repair_loop_withholds_on_second_hit(policy):
    alerts = AlertManager()  # no tokens -> logs to stdout, never raises
    router = LeakyRouter()
    with pytest.raises(PolicyRefusal) as exc_info:
        await translate_policied("my points", "en", "en", policy, router, alerts)
    assert exc_info.value.leaks  # leaks recorded, nothing shipped
    assert router.calls == 2  # initial + exactly one repair retry
    # A P2 alert was recorded (fingerprint policy_leak) without raising.
    assert any("POLICY_LEAK" in fp for fp in alerts._records)


@pytest.mark.asyncio
async def test_clean_output_passes(policy):
    alerts = AlertManager()
    router = CleanRouter()
    result, provider, meta = await translate_policied(
        "my points", "en", "en", policy, router, alerts
    )
    assert result == "send Amount"
    assert provider == "stub"
    assert meta["deny_hits"] == 0
    assert "balance" in meta["policy_hits"]
    assert router.calls == 1
