"""The 40-case policy regression set (spec 4.5) and its publish gate.

These run on every commit and need no provider: they exercise the part of
the pipeline the project owns - normalise -> entity protection -> mask ->
render -> restore. The provider-dependent variant lives behind
PYTEST_LIVE_PROVIDER=1.
"""
import os

import pytest

from app.policy.governance import (
    PolicyNotPublishable,
    assert_publishable,
    regression_report,
)
from app.policy.policy import compile_policy
from app.policy.regression_set import (
    DENY_CASES,
    REGRESSION_SET,
    RegressionCase,
    check,
    check_deny,
    evaluate,
    run_live,
)


@pytest.fixture(scope="module")
def policy():
    return compile_policy(1)


# ---------------------------------------------------------------------------
# The 40 cases
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("case", REGRESSION_SET, ids=[c.id for c in REGRESSION_SET])
def test_regression_case(case, policy):
    problems = check(case, policy)
    assert not problems, (
        f"{case.id}: {problems}\n"
        f"  input    = {case.text!r}\n"
        f"  rendered = {evaluate(case, policy)!r}\n"
        f"  note     = {case.note}"
    )


def test_set_is_40_cases():
    # Spec 4.5 fixes the size of the contract: 40 cases, all passing.
    assert len(REGRESSION_SET) == 40


def test_case_ids_are_unique():
    ids = [c.id for c in REGRESSION_SET]
    assert len(ids) == len(set(ids))


def test_coverage_matrix(policy):
    """Every concept and every supported direction must be represented."""
    from app.policy.policy import PLACEHOLDER_RE, mask, normalise, protect_entities

    masked = []
    for case in REGRESSION_SET:
        protected, _ = protect_entities(normalise(case.text))
        masked.append(mask(protected, case.src, policy))
    concepts = {c for text in masked for c in PLACEHOLDER_RE.findall(text)}
    assert concepts == {"user_id", "user_account", "balance", "platform", "member"}

    directions = {(c.src, c.dst) for c in REGRESSION_SET}
    assert directions == {
        ("my", "en"), ("en", "my"), ("en", "en"), ("zh", "en"),
        ("auto", "en"), ("auto", "my"),
    }


def test_no_case_expects_a_stale_term(policy):
    """Guard the drift that made 5 seeded cases fail: the expectations must
    use the CURRENT approved output terms, never the pre-v3.2 ones."""
    stale = {"Balance", "လက်ကျန်"}
    for case in REGRESSION_SET:
        assert case.must_contain not in stale, case.id


# ---------------------------------------------------------------------------
# Layer 3: deny scan and evasion
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("case", DENY_CASES, ids=[c.id for c in DENY_CASES])
def test_deny_case(case, policy):
    assert not check_deny(case, policy)


def test_cross_script_cases_are_deny_clean(policy):
    """my/zh -> en: the residue is in another script, so a deny term in the
    rendered text can only mean masking missed a concept."""
    from app.policy.policy import deny_scan

    checked = [c for c in REGRESSION_SET if c.dst == "en" and c.src != "en"]
    assert len(checked) >= 15
    leaks = {
        c.id: deny_scan(evaluate(c, policy), c.dst, policy) for c in checked
    }
    assert not {k: v for k, v in leaks.items() if v}


# ---------------------------------------------------------------------------
# Publish gate
# ---------------------------------------------------------------------------

def test_report_is_clean_for_policy_v1():
    report = regression_report(1)
    assert report.ok, report.failures
    assert report.total == 40
    assert report.summary() == "40/40 regression cases pass"


def test_publish_gate_blocks_a_failing_case():
    broken = RegressionCase(
        id="broken", src="en", dst="en", text="hello there",
        must_contain="Amount", must_not_contain="hello",
    )
    with pytest.raises(PolicyNotPublishable) as exc_info:
        assert_publishable(1, cases=[broken])
    assert "broken" in exc_info.value.failures
    assert exc_info.value.version == 1


def test_publish_gate_allows_a_clean_case():
    good = RegressionCase(
        id="good", src="en", dst="en", text="my game id is wrong",
        must_contain="User ID", must_not_contain="game id",
    )
    report = assert_publishable(1, cases=[good])
    assert report.ok and report.total == 1


# ---------------------------------------------------------------------------
# Optional live run (spec 4.6: run the set against every provider)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    os.environ.get("PYTEST_LIVE_PROVIDER") != "1",
    reason="set PYTEST_LIVE_PROVIDER=1 to run the 40 cases through a provider",
)
async def test_live_provider_passes_the_set():
    from app import config
    from app.services.provider import Provider, ProviderRouter

    router = ProviderRouter(
        providers=[
            Provider(
                name="live", base_url=config.PROVIDER_BASE_URL,
                api_key=config.PROVIDER_API_KEY, model=config.PROVIDER_MODEL,
            )
        ]
    )
    try:
        results = await run_live(compile_policy(1), router)
    finally:
        await router.close()
    failures = {k: v for k, v in results.items() if v}
    assert not failures


def test_seed_uses_the_same_set():
    """seed.py must write the same 40 rows pytest runs - no second copy."""
    from app.store import seed as seed_mod

    assert seed_mod.REGRESSION_SET is REGRESSION_SET
    assert len(seed_mod.REGRESSION_SET) == 40
