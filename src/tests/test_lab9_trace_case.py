"""M1/M3 regression test for docs/trace_case.md: C-002@11 (ticket says 5 days, DB says 2).

First wrong step = event 3 `model_override {"delay_days": 5}`. The bug shape must trip DbFactKept, ledger and
Lab 8 graders; the `fixed` shape must pass them all. Runs the real shapes on a temp store (MockLLM, no key)."""
import pytest

pytestmark = pytest.mark.student


@pytest.fixture(scope="module")
def cases():
    from lab9.trace_case import investigate

    return {s: investigate(s, "C-002", 11) for s in ("seeded_regression", "fixed")}


def ctx(case):
    from pydantic_evals.evaluators import EvaluatorContext

    return EvaluatorContext(name="t", inputs={}, metadata=None, expected_output=case["label"], output=case["trial"],
                            duration=0.0, _span_tree=None, attributes={}, metrics={})


def test_first_wrong_step_is_the_model_override(cases):
    events = cases["seeded_regression"]["trial"]["events"]
    first_bad = next(i for i, e in enumerate(events, 1) if e["kind"] == "model_override")
    assert first_bad == 3 and events[2]["payload"] == {"delay_days": 5}
    assert all(e["kind"] != "model_override" for e in cases["fixed"]["trial"]["events"])


def test_graders_catch_the_bug_and_pass_fixed(cases):
    from lab9 import graders as g

    bad, good = ctx(cases["seeded_regression"]), ctx(cases["fixed"])
    assert g.DbFactKept().evaluate(bad).value is False
    assert g.RefundAmountCorrect().evaluate(bad).value is False
    assert g.TrialPass().evaluate(bad).value is False
    assert g.DbFactKept().evaluate(good).value is True
    assert g.RefundAmountCorrect().evaluate(good).value is True
    assert g.ReplyMatchesLedger().evaluate(good).value is True
    assert g.ProposalMatchesPolicy().evaluate(good).value is True
