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
from lab9.eval import SPEC, aggregate, load_spec, per_item
from lab9.graders import GRADERS


def integrity_check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> list[str]:
    """M7 (Expert): refuse to compare reports that cannot be trusted. Return a list of problems
    (empty = trustworthy). A gate that passes a broken report is worse than no gate.
    Must catch at least:
      - any metric value in pr["metrics"] that is NaN or inf
      - len(pr["rows"]) != manifest items x len(manifest seeds)   (dropped / duplicated rows)
      - the (item_id, seed) set of PR differs from the baseline's (cherry-picked seeds/items)
      - pr["evaluator_failures"] non-empty, or a row whose value for a graded spec metric is
        None (a crashed grader silently scores as "missing" and drops out of the mean)
      - base_spec given and a threshold in spec is LOOSER than in base_spec for the same
        eval-set version (ratchet: max may not rise, min may not fall, a blocking metric may
        not become non-blocking, a metric may not disappear; the same for spec["slices"],
        including dropping no_significant_drop)
      - an item's slice tags in PR rows differ from the baseline's (relabelling an item out of a
        slice hides its regression from the slice gate)"""
    problems: list[str] = []
    pm, bm = pr.get("manifest") or {}, base.get("manifest") or {}
    rows, brows = pr.get("rows") or [], base.get("rows") or []

    # 1. Metric values must be real numbers: NaN/inf compare False against every threshold.
    for k, v in (pr.get("metrics") or {}).items():
        if isinstance(v, float) and not math.isfinite(v):
            problems.append(f"metric {k} is {v} (NaN/inf hides a crashed grader)")

    # 2. Row coverage: exactly one row per (item, seed), the same set as the baseline's, and a manifest
    #    that was not rewritten to match a trimmed report.
    keys = [(r.get("item_id"), r.get("seed")) for r in rows]
    dup = sorted({k for k in keys if keys.count(k) > 1}, key=str)
    if dup:
        problems.append(f"{len(dup)} duplicated (item, seed) row(s), e.g. {dup[0]}")
    try:
        want = int(pm["items"]) * len(pm["seeds"])
    except (KeyError, TypeError, ValueError):
        want = None
        problems.append("manifest lacks items/seeds: cannot verify row coverage")
    if want is not None and len(rows) != want:
        problems.append(f"{len(rows)} rows != manifest {pm['items']} items x {len(pm['seeds'])} seeds = {want}")
    if pm.get("items") != bm.get("items") or list(pm.get("seeds") or []) != list(bm.get("seeds") or []):
        problems.append(f"manifest items/seeds {pm.get('items')}/{pm.get('seeds')} differ from the baseline's "
                        f"{bm.get('items')}/{bm.get('seeds')} (cherry-picked seeds or items)")
    bkeys = {(r.get("item_id"), r.get("seed")) for r in brows}
    if set(keys) != bkeys:
        missing, extra = bkeys - set(keys), set(keys) - bkeys
        problems.append(f"(item, seed) set differs from the baseline's: {len(missing)} missing, {len(extra)} extra"
                        + (f", e.g. missing {sorted(missing, key=str)[0]}" if missing else ""))

    # 3. Graders must have run on every row. A crashed grader becomes None and silently leaves the mean.
    if pr.get("evaluator_failures"):
        problems.append(f"{len(pr['evaluator_failures'])} evaluator failure(s), first: {pr['evaluator_failures'][0]}")
    graded = [m["id"] for m in spec.get("metrics", []) if m["id"] in GRADERS]
    for mid in graded:
        if not any(mid in r for r in rows) and not any(mid in r for r in brows):
            continue                                 # neither run graded it (not an eval of this spec)
        none = [f"{r.get('item_id')}@{r.get('seed')}" for r in rows if not isinstance(r.get(mid), bool)]
        if none:
            problems.append(f"{len(none)} row(s) without a {mid} value (grader crashed?), e.g. {none[0]}")

    # 4. Reported metrics must be the ones the rows produce (a hand-edited number is not evidence).
    ids = [m for m in graded if rows and all(isinstance(r.get(m), bool) for r in rows)]
    try:
        again = aggregate(rows, ids, k_values=spec.get("pass_k", [])) if ids else {}
    except (KeyError, TypeError, ValueError):
        again = {}
    for k, v in again.items():
        got = (pr.get("metrics") or {}).get(k)
        if isinstance(v, (int, float)) and isinstance(got, (int, float)) and math.isfinite(got) \
                and abs(float(v) - float(got)) > 1e-3:
            problems.append(f"metric {k} reported {got} but the rows give {v} (edited report)")

    # 5. Slice tags are derived from labels and may not move between PR and baseline.
    btags = {r.get("item_id"): sorted(r.get("slices") or []) for r in brows}
    moved = sorted({r.get("item_id") for r in rows
                    if r.get("item_id") in btags and sorted(r.get("slices") or []) != btags[r.get("item_id")]}, key=str)
    if moved:
        problems.append(f"slice tags of {len(moved)} item(s) differ from the baseline's, e.g. {moved[0]}")

    # 6. Ratchet: on the same eval-set version a spec may only get stricter.
    if base_spec is not None:
        problems += _ratchet(spec, base_spec)
    return problems


def _loosened(name: str, new: dict | None, old: dict) -> list[str]:
    """Compare one metric/slice entry with its baseline version; return the ways it got laxer."""
    if new is None:
        return [f"{name} was removed"]
    out = []
    if old.get("blocking") and not new.get("blocking"):
        out.append(f"{name} is no longer blocking")
    # Metrics keep bounds under "threshold"; slices keep them at the top level.
    oth = old.get("threshold") or {} if "threshold" in old else old
    nth = new.get("threshold") or {} if "threshold" in old else new
    for key, upper in (("max", True), ("max_increase", True), ("min", False)):
        if key not in oth:
            continue
        o, n = oth[key], nth.get(key)
        if not isinstance(n, (int, float)) or isinstance(n, bool) or not math.isfinite(float(n)):
            out.append(f"{name}.{key} was dropped ({o} -> {n})")
        elif (upper and n > o) or (not upper and n < o):
            out.append(f"{name}.{key} loosened {o} -> {n}")
    if oth.get("no_significant_drop") and not nth.get("no_significant_drop"):
        out.append(f"{name}.no_significant_drop was dropped")
    if new.get("metric", old.get("metric")) != old.get("metric"):
        out.append(f"{name} now measures {new.get('metric')} instead of {old.get('metric')}")
    return out


def _ratchet(spec: dict, base_spec: dict) -> list[str]:
    if spec.get("eval_set_version") != base_spec.get("eval_set_version"):
        return []        # a new eval-set version restarts the thresholds (and needs a new baseline)
    out: list[str] = []
    new_m = {m["id"]: m for m in spec.get("metrics") or []}
    for m in base_spec.get("metrics") or []:
        out += _loosened(f"metric {m['id']}", new_m.get(m["id"]), m)
    new_s = {(s.get("name"), s.get("metric")): s for s in spec.get("slices") or []}
    for s in base_spec.get("slices") or []:
        out += _loosened(f"slice {s.get('name')}/{s.get('metric')}", new_s.get((s.get("name"), s.get("metric"))), s)
    for key in ("seeds", "eval_set", "labels", "adversarial_pack"):
        if key in base_spec and spec.get(key) != base_spec.get(key):
            out.append(f"spec {key} changed on the same eval-set version")
    return [f"RATCHET {p}" for p in out]


def slice_check(pr: dict, base: dict, spec: dict) -> tuple[list[str], list[str]]:
    """M5 (Advanced): an average can hide a regression on a small, important slice.
    For each entry of spec["slices"] ({"name", "metric", "min"?, "no_significant_drop"?, "blocking"}):
      - value = mean of per_item(pr, metric, slice_name=name)
      - fail if below "min", or if no_significant_drop and the paired CI over the slice's items
        lies entirely below 0
    Return (blocked ids like "slice:money_movement/pass_rate", report lines)."""
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for s in spec.get("slices") or []:
        name, mid = s["name"], s["metric"]
        sid = f"slice:{name}/{mid}"
        a, b = per_item(pr, mid, slice_name=name), per_item(base, mid, slice_name=name)
        verdict, note, val = "ok", "", None
        if not a:
            verdict = "missing"                     # a slice that vanished from the PR is not a pass
        else:
            val = round(sum(a.values()) / len(a), 4)
            if "min" in s and val < s["min"]:
                verdict = "fail"
            keys = sorted(set(a) & set(b))
            if s.get("no_significant_drop") and keys:
                d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                                   n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027))
                note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
                if hi < 0:
                    verdict = "fail"
        if verdict != "ok" and s.get("blocking"):
            blocked.append(sid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if s.get("blocking") else "warn")
        th = {k: s[k] for k in ("min", "no_significant_drop") if k in s}
        lines.append(f"  {sid:<34} {val!s:<8} n={len(a):<3} {json.dumps(th):<34} {note:<28} {label}")
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
