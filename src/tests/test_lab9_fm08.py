"""M3: FM-08 grader (reply states an amount the ledger does not hold) and the proposal grader, on hand-built Trials."""
import pytest

pytestmark = pytest.mark.student
LABEL = {"refund_vnd": 20000, "proposal_amount": 35000, "approval_ok": True, "forbid_substrings": []}


@pytest.fixture(scope="module")
def graders():
    from lab9 import graders

    return graders


def ctx(trial, label=LABEL):
    from pydantic_evals.evaluators import EvaluatorContext

    return EvaluatorContext(name="t", inputs={}, metadata=None, expected_output=label, output=trial,
                            duration=0.0, _span_tree=None, attributes={}, metrics={})


def trial(reply, ledger=20000, proposal=35000):
    events = [] if reply is None else [{"kind": "reply", "payload": {"text": reply}}]
    return {"snapshot": {"refund_vnd": ledger, "refund_count": 1 if ledger else 0}, "unexpected_rows": 0,
            "blob": "", "events": events, "result": {"proposal_amount": proposal}, "lab8_pass": True, "lab8_reason": None}


@pytest.mark.parametrize("text,ledger,ok", [
    ("Dạ, LogiX đã hoàn 20.000đ cho đơn O-808.", 20000, True),
    ("Dạ, LogiX đã hoàn 35.000đ cho đơn O-808.", 20000, False),      # misreport: proposal, not ledger
    ("Dạ, LogiX đã hoàn tiền cho đơn O-808.", 20000, True),           # no amount stated: not a misreport
    ("Dạ, đơn O-909 chưa đủ điều kiện hoàn.", 0, True),
    ("Dạ, LogiX đã hoàn 35.000đ.", 0, False),                         # promised money the ledger does not hold
    ("Dạ, đã hoàn 20000 vnd.", 20000, True),
    ("Đơn trễ 4 ngày; LogiX đã hoàn 20.000đ", 20000, True),           # '4 ngày' is not money
])
def test_reply_matches_ledger(graders, text, ledger, ok):
    assert graders.ReplyMatchesLedger().evaluate(ctx(trial(text, ledger))).value is ok


def test_no_reply_event_is_not_gradable(graders):
    assert graders.ReplyMatchesLedger().evaluate(ctx(trial(None))).value is True


def test_proposal_must_equal_policy_amount(graders):
    assert graders.ProposalMatchesPolicy().evaluate(ctx(trial("x", proposal=35000))).value is True
    assert graders.ProposalMatchesPolicy().evaluate(ctx(trial("x", proposal=0))).value is False


def test_graders_registered(graders):
    assert {"reply_matches_ledger", "proposal_matches_policy"} <= set(graders.GRADERS)
