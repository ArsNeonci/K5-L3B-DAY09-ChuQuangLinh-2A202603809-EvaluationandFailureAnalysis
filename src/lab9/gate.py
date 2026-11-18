"""CI gate: compare a PR eval report with the main-branch baseline using the metric spec.

    python -m lab9.gate --pr reports/eval_workflow.json --baseline reports/baseline_v1.json

exit 0 = merge, exit 1 = blocked. Safety metrics: max 0, no averaging away.
Capability metrics: meet the floor AND the paired CI of (PR - main) is not entirely below 0.
Thresholds may only get stricter on the same eval-set version (ratchet).
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from lab8.console import utf8_stdio
from lab9 import stats
from lab9.eval import SPEC, load_spec, per_item


def _num(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _bad_number(x) -> bool:
    return _num(x) and (math.isnan(x) or math.isinf(x))


def _recompute(rows: list[dict], metric: str, kind: str | None) -> float | None:
    vals = [r[metric] for r in rows if r.get(metric) is not None]
    if not vals:
        return None
    return float(sum(vals)) if kind == "safety" else round(sum(vals) / len(vals), 4)


def _loosened(name: str, new: dict, old: dict) -> list[str]:
    """Ways `new` (a PR's metric / slice entry) is looser than `old` (main's)."""
    out = []
    nt, ot = new.get("threshold", new) or {}, old.get("threshold", old) or {}
    if "max" in ot and not (_num(nt.get("max")) and nt["max"] <= ot["max"]):
        out.append(f"{name}: max {ot['max']} -> {nt.get('max')}")
    if "min" in ot and not (_num(nt.get("min")) and nt["min"] >= ot["min"]):
        out.append(f"{name}: min {ot['min']} -> {nt.get('min')}")
    if "max_increase" in ot and not (_num(nt.get("max_increase")) and nt["max_increase"] <= ot["max_increase"]):
        out.append(f"{name}: max_increase {ot['max_increase']} -> {nt.get('max_increase')}")
    if ot.get("no_significant_drop") and not nt.get("no_significant_drop"):
        out.append(f"{name}: no_significant_drop dropped")
    if old.get("blocking") and not new.get("blocking"):
        out.append(f"{name}: blocking -> non-blocking")
    return out


def _ratchet(spec: dict, base_spec: dict) -> list[str]:
    """Thresholds may only get stricter on the same eval-set version."""
    if spec.get("eval_set_version") != base_spec.get("eval_set_version"):
        return [f"RATCHET eval_set_version {base_spec.get('eval_set_version')!r} -> {spec.get('eval_set_version')!r} "
                "without a new baseline: relabelling the version does not make looser thresholds legal"]
    out = []
    new_m = {m["id"]: m for m in spec.get("metrics", [])}
    for old in base_spec.get("metrics", []):
        new = new_m.get(old["id"])
        if new is None:
            out.append(f"RATCHET metric {old['id']} removed")
        else:
            out += [f"RATCHET {x}" for x in _loosened(f"metric {old['id']}", new, old)]
    new_s = {(x["name"], x.get("metric")): x for x in spec.get("slices") or []}
    for old in base_spec.get("slices") or []:
        new = new_s.get((old["name"], old.get("metric")))
        if new is None:
            out.append(f"RATCHET slice {old['name']}/{old.get('metric')} removed")
        else:
            out += [f"RATCHET {x}" for x in _loosened(f"slice {old['name']}/{old.get('metric')}", new, old)]
    if (spec.get("bootstrap") or {}) != (base_spec.get("bootstrap") or {}):
        out.append(f"RATCHET bootstrap settings changed: {base_spec.get('bootstrap')} -> {spec.get('bootstrap')}")
    for key in ("seeds", "pass_k"):
        if set(base_spec.get(key) or []) - set(spec.get(key) or []):
            out.append(f"RATCHET spec {key} shrank: {base_spec.get(key)} -> {spec.get(key)}")
    return out


def integrity_check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> list[str]:
    """M7 (Expert): refuse to compare reports that cannot be trusted. Return a list of problems
    (empty = trustworthy). A gate that passes a broken report is worse than no gate.
    Checks: non-finite metrics; row count vs manifest; duplicate or foreign (item, seed) pairs;
    the PR (item, seed) set vs the baseline's; evaluator failures; missing / non-boolean grader values;
    reported metrics that the rows do not reproduce; slice tags changed vs the baseline and the eval set;
    and, with base_spec, any loosened threshold, dropped metric/slice or lost blocking flag."""
    from lab9.graders import GRADERS

    problems: list[str] = []
    rows = pr.get("rows") or []
    metrics = pr.get("metrics") or {}
    man, bman = pr.get("manifest") or {}, base.get("manifest") or {}

    for k, v in metrics.items():
        if _bad_number(v):
            problems.append(f"metric {k} is {v} (NaN/inf)")
    pairs = [(r.get("item_id"), r.get("seed")) for r in rows]
    n_seeds = len(man.get("seeds") or [])
    want_rows = int(man.get("items", -1)) * n_seeds
    if len(rows) != want_rows:
        problems.append(f"{len(rows)} rows, manifest says {man.get('items')} items x {n_seeds} seeds = {want_rows}")
    dups = sorted({str(p) for p in pairs if pairs.count(p) > 1})
    if dups:
        problems.append(f"duplicate (item, seed) rows: {', '.join(dups[:4])}")
    base_pairs = {(r.get("item_id"), r.get("seed")) for r in base.get("rows") or []}
    if base_pairs and set(pairs) != base_pairs:
        miss, extra = sorted(map(str, base_pairs - set(pairs))), sorted(map(str, set(pairs) - base_pairs))
        problems.append(f"(item, seed) set differs from the baseline's: {len(miss)} missing {miss[:3]}, "
                        f"{len(extra)} extra {extra[:3]}")
    if bman.get("seeds") and sorted(man.get("seeds") or []) != sorted(bman["seeds"]):
        problems.append(f"seeds {man.get('seeds')} differ from the baseline's {bman['seeds']}")
    if pr.get("evaluator_failures"):
        problems.append(f"{len(pr['evaluator_failures'])} evaluator failure(s): {pr['evaluator_failures'][0]}")

    for m in (m for m in spec.get("metrics", []) if m["id"] in GRADERS):
        bad = [r for r in rows if not isinstance(r.get(m["id"]), bool)]
        if bad:
            problems.append(f"{len(bad)} row(s) with no valid {m['id']} value (crashed or removed grader), e.g. "
                            f"{bad[0].get('item_id')}@{bad[0].get('seed')}={bad[0].get(m['id'])!r}")
            continue
        got = metrics.get(m["id"])
        want = _recompute(rows, m["id"], m.get("kind"))
        if rows and (not _num(got) or want is None or abs(got - want) > 1e-3):
            problems.append(f"reported {m['id']}={got} but the rows give {want}")
    if rows and all(isinstance(r.get("pass_rate"), bool) for r in rows):
        by_item: dict = {}
        for r in rows:
            by_item.setdefault(r["item_id"], []).append(r["pass_rate"])
        for k in metrics:
            if k.startswith(("pass_at_", "pass_hat_")) and _num(metrics[k]):
                fn = stats.pass_at_k if k.startswith("pass_at_") else stats.pass_hat_k
                kk = int(k.rsplit("_", 1)[1])
                try:
                    want = sum(fn(len(v), sum(v), kk) for v in by_item.values()) / len(by_item)
                except ValueError:
                    continue
                if abs(metrics[k] - want) > 1e-3:
                    problems.append(f"reported {k}={metrics[k]} but the rows give {round(want, 4)}")

    base_tags = {r["item_id"]: sorted(r.get("slices") or []) for r in base.get("rows") or []}
    pr_tags = {r["item_id"]: sorted(r.get("slices") or []) for r in rows}
    moved = sorted(i for i in pr_tags if i in base_tags and pr_tags[i] != base_tags[i])
    if moved:
        problems.append(f"slice tags changed vs the baseline for {', '.join(moved[:5])}: relabelling hides a regression")
    items_file = Path(man.get("eval_set") or "")
    if items_file.is_file():
        from lab9 import evalset
        tags = {it["item_id"]: sorted(it.get("slices") or []) for it in evalset.load_jsonl(items_file)}
        off = sorted(i for i in pr_tags if i in tags and pr_tags[i] != tags[i])
        if off:
            problems.append(f"slice tags of {', '.join(off[:5])} do not match the eval set file")
    if base_spec is not None:
        problems += _ratchet(spec, base_spec)
    return problems


def slice_check(pr: dict, base: dict, spec: dict) -> tuple[list[str], list[str]]:
    """M5 (Advanced): an average can hide a regression on a small, important slice.
    For each entry of spec["slices"] ({"name", "metric", "min"?, "no_significant_drop"?, "blocking"}):
      - value = mean of per_item(pr, metric, slice_name=name)
      - fail if below "min", or if no_significant_drop and the paired CI over the slice's items
        lies entirely below 0
    Return (blocked ids like "slice:money_movement/pass_rate", report lines)."""
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for sl in spec.get("slices") or []:
        name, metric = sl["name"], sl["metric"]
        sid = f"slice:{name}/{metric}"
        a, b = per_item(pr, metric, slice_name=name), per_item(base, metric, slice_name=name)
        verdict, note, val = "ok", "", None
        if not a:
            verdict = "missing"                     # an empty slice proves nothing: never a pass
        else:
            val = round(sum(a.values()) / len(a), 4)
            if "min" in sl and val < sl["min"]:
                verdict = "fail"
            if sl.get("no_significant_drop"):
                keys = sorted(set(a) & set(b))
                if keys:
                    d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                                       n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027))
                    note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
                    if hi < 0:
                        verdict = "fail"
        if verdict != "ok" and sl.get("blocking"):
            blocked.append(sid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if sl.get("blocking") else "warn")
        th = {k: sl[k] for k in ("min", "no_significant_drop") if k in sl}
        lines.append(f"  {sid:<34} {val!s:<8} {json.dumps(th):<40} {note:<28} {label} (n={len(a)} items)")
    return blocked, lines


def check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> tuple[list[str], list[str]]:
    if pr["manifest"]["eval_set_sha"] != base["manifest"]["eval_set_sha"]:
        return ["eval_set_sha"], ["  EVAL SET differs from the baseline's: re-run the baseline on the same eval set"]
    problems = integrity_check(pr, base, spec, base_spec)
    if problems:
        return ["integrity"], [f"  INTEGRITY {p}" for p in problems]
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for m in spec["metrics"]:
        mid, th, val = m["id"], m.get("threshold", {}), pr["metrics"].get(m["id"])
        verdict, note = "ok", ""
        if val is None:
            verdict = "missing"
        elif "max" in th and val > th["max"]:
            verdict = "fail"
        elif "min" in th and val < th["min"]:
            verdict = "fail"
        elif "max_increase" in th and base["metrics"].get(mid):
            if val > base["metrics"][mid] * (1 + th["max_increase"]):
                verdict = "fail"
        if th.get("no_significant_drop") and val is not None:
            a, b = per_item(pr, mid), per_item(base, mid)
            keys = sorted(set(a) & set(b))
            d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                               n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027))
            note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
            if hi < 0:
                verdict = "fail"
        if verdict != "ok" and m.get("blocking"):
            blocked.append(mid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if m.get("blocking") else "warn")
        lines.append(f"  {mid:<22} {val!s:<8} {json.dumps(th):<40} {note:<28} {label}")
    if spec.get("slices"):
        sb, sl = slice_check(pr, base, spec)
        blocked += sb
        lines += sl
    return blocked, lines


def main(argv: list[str] | None = None) -> int:
    utf8_stdio()
    ap = argparse.ArgumentParser(prog="lab9.gate")
    ap.add_argument("--pr", required=True)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--spec", default=str(SPEC))
    ap.add_argument("--base-spec", help="metric spec on main, for the ratchet check (M7)")
    args = ap.parse_args(argv)
    pr = json.loads(Path(args.pr).read_text(encoding="utf-8"))
    base = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    base_spec = load_spec(Path(args.base_spec)) if args.base_spec else None
    blocked, lines = check(pr, base, load_spec(Path(args.spec)), base_spec)
    print(f"gate: PR {pr['run_id']} vs main {base['run_id']} · eval set {pr['manifest']['eval_set_sha']}")
    print("\n".join(lines))
    if blocked:
        print(f"exit 1 — blocked: {', '.join(blocked)}")
        return 1
    print("exit 0 — merge")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
