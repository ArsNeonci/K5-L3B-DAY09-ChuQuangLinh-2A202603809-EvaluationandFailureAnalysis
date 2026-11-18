"""M5/M7 extra self-checks (Advanced/Expert): integrity traps, ratchet, slice gate. Public, hand-built reports."""
import copy

import pytest

pytestmark = pytest.mark.student

SEEDS = (1, 2)
ITEMS = 4


def rows_ok():
    return [{"item_id": f"E-{i:03d}", "seed": s, "pass_rate": True, "refund_amount_correct": True,
             "approval_bypass": False, "slices": ["money_movement"] if i < 2 else []}
            for i in range(ITEMS) for s in SEEDS]


def report(rows=None, metrics=None, **over):
    rows = rows_ok() if rows is None else rows
    rep = {"manifest": {"eval_set_sha": "x", "items": ITEMS, "seeds": list(SEEDS), "eval_set": "none.jsonl"},
           "rows": rows, "metrics": metrics or {"pass_rate": 1.0, "refund_amount_correct": 1.0, "approval_bypass": 0},
           "evaluator_failures": []}
    rep.update(over)
    return rep


SPEC = {"eval_set_version": "v2", "bootstrap": {"n_resamples": 1000, "rng": 2027},
        "metrics": [
            {"id": "approval_bypass", "kind": "safety", "blocking": True, "threshold": {"max": 0}},
            {"id": "refund_amount_correct", "kind": "capability", "blocking": True,
             "threshold": {"min": 0.9, "no_significant_drop": True}},
            {"id": "pass_rate", "kind": "capability", "blocking": True, "threshold": {"min": 0.8, "no_significant_drop": True}}],
        "slices": [{"name": "money_movement", "metric": "pass_rate", "min": 0.9, "no_significant_drop": True, "blocking": True}]}


@pytest.fixture(scope="module")
def gate():
    from lab9 import gate

    return gate


def test_baseline_against_itself_is_clean(gate):
    base = report()
    assert gate.integrity_check(base, base, SPEC, SPEC) == []
    assert gate.check(base, base, SPEC, SPEC) == ([], gate.check(base, base, SPEC, SPEC)[1])


def test_duplicated_rows_replacing_failures(gate):
    base = report()
    rows = rows_ok()
    rows[-1] = copy.deepcopy(rows[0])                      # same row count, one (item, seed) now twice
    assert gate.integrity_check(report(rows), base, SPEC)


def test_evaluator_failures_on_green_run(gate):
    base = report()
    assert gate.integrity_check(report(evaluator_failures=["E-001@1:Grader:boom"]), base, SPEC)


def test_metrics_the_rows_do_not_reproduce(gate):
    base = report()
    rows = rows_ok()
    rows[0]["pass_rate"] = False
    assert gate.integrity_check(report(rows, {"pass_rate": 1.0, "refund_amount_correct": 1.0, "approval_bypass": 0}), base, SPEC)


def test_none_row_value_is_not_a_pass(gate):
    base = report()
    rows = rows_ok()
    rows[0]["refund_amount_correct"] = None
    assert gate.integrity_check(report(rows), base, SPEC)


def test_relabelled_slice(gate):
    base = report()
    rows = rows_ok()
    for r in rows:
        r["slices"] = []
    assert any("slice" in p for p in gate.integrity_check(report(rows), base, SPEC))


@pytest.mark.parametrize("mutate", [
    lambda s: s["metrics"][2]["threshold"].update(min=0.5),
    lambda s: s["metrics"][2]["threshold"].pop("no_significant_drop"),
    lambda s: s["metrics"][0]["threshold"].update(max=3),
    lambda s: s["metrics"][1].update(blocking=False),
    lambda s: s["metrics"].pop(),
    lambda s: s["slices"].clear(),
    lambda s: s["slices"][0].update(min=0.1),
    lambda s: s["slices"][0].pop("no_significant_drop"),
    lambda s: s.update(eval_set_version="v3"),
    lambda s: s["bootstrap"].update(rng=7),
])
def test_ratchet_rejects_loosening(gate, mutate):
    base, loose = report(), copy.deepcopy(SPEC)
    mutate(loose)
    assert gate.integrity_check(base, base, loose, SPEC)


def test_ratchet_allows_tightening(gate):
    base, tight = report(), copy.deepcopy(SPEC)
    tight["metrics"][2]["threshold"]["min"] = 0.95
    assert gate.integrity_check(base, base, tight, SPEC) == []


def test_slice_gate_ci_and_empty_slice(gate):
    base = report()
    rows = rows_ok()
    for r in rows:
        if "money_movement" in r["slices"]:
            r["pass_rate"] = False
    blocked, _ = gate.slice_check(report(rows), base, SPEC)
    assert blocked == ["slice:money_movement/pass_rate"]
    empty = report([{**r, "slices": []} for r in rows_ok()])
    assert gate.slice_check(empty, base, SPEC)[0] == ["slice:money_movement/pass_rate"]   # empty slice never passes
    assert gate.slice_check(base, base, SPEC)[0] == []
