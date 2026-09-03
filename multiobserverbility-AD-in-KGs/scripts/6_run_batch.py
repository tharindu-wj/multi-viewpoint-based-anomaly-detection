"""Run N fresh observation rounds and report the metric distribution.

    python scripts/6_run_batch.py --n 3 --label stage1

Stage 0 of IMPROVEMENT_PLAN.md: the minimal measurement protocol. Every
gate in that plan is judged against a mean +/- sd, never a single run --
measured single-run swing on identical code is 25% -> 0%.

Runs 3_run_observers.py N times (fresh API runs; existing run files are
never reused as batch members), then scores each against the answer key
the same way 4_evaluate_verdicts.py does: K, P@K, R@K, and primary-flag
complementarity, with mean +/- sd over the runs that completed validly.
"""
import json
import statistics
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import argparse  # noqa: E402

import eval_lib  # noqa: E402  (lives beside this script)
from loaders.active import DATASET  # noqa: E402
from loaders.context import get_context  # noqa: E402
from tools._observers import OBSERVER_NAMES  # noqa: E402
from tools.mining_rules.pool import interleave  # noqa: E402

#: the fixed rungs this batch reports per run (500 is P=R, already covered)
RUNGS = (50, 100, 150, 200)

parser = argparse.ArgumentParser()
parser.add_argument("--n", type=int, default=3, help="fresh runs to make")
parser.add_argument("--label", default="batch", help="name for this batch")
parser.add_argument("--pause", type=int, default=30,
                    help="seconds between runs (quota cooldown)")
args = parser.parse_args()

truth = {}
for head, relation, tail, label, kind in (
        line.split("\t") for line in
        DATASET.TRUTH.read_text(encoding="utf-8").splitlines()):
    truth[(head, relation, tail)] = int(label)
planted_total = sum(truth.values())

# the definitions context parses megabytes of JSON; the ladder rebuilds a
# pool per observer per run on top of it -- build the context ONCE here,
# never inside score()
CTX = get_context()

before = set(DATASET.RUNS.glob("run_*_observers.json"))
made = []
for i in range(args.n):
    print(f"\n=== {args.label}: run {i + 1} of {args.n} " + "=" * 40)
    result = subprocess.run(
        [sys.executable, "-X", "utf8", str(ROOT / "scripts" / "3_run_observers.py"),
         "--quiet"], cwd=ROOT)
    if result.returncode != 0:
        print(f"  run {i + 1} exited {result.returncode}; continuing")
    fresh = sorted(set(DATASET.RUNS.glob("run_*_observers.json")) - before)
    before.update(fresh)
    made.extend(fresh)
    if i + 1 < args.n:
        time.sleep(args.pause)


def score(path):
    run = json.loads(path.read_text(encoding="utf-8"))
    verdicts = dict(zip(OBSERVER_NAMES, run["verdicts"]))
    flags = {n: {tuple(v["triple"]) for v in verdicts[n].values()
                 if v["verdict"] == "anomaly"} for n in OBSERVER_NAMES}
    primary = {n: {tuple(v["triple"]) for cid, v in verdicts[n].items()
                   if v["verdict"] == "anomaly" and cid.startswith("c")}
               for n in OBSERVER_NAMES}
    a, b = OBSERVER_NAMES
    union = flags[a] | flags[b]
    hits = sum(1 for t in union if truth.get(t) == 1)
    # rules-only baseline at the same K: the surveyed pools zipped, no LLM
    pools = [p.get("entries", []) for p in run.get("pools", [])]
    base = sum(1 for t in interleave(pools, len(union)) if truth.get(t) == 1)
    # fixed-K ladder over the confidence-tier ranking; None marks a run that
    # predates recorded scopes/pools -- it sits out of the ladder means
    rungs = {f"P{k}": None for k in RUNGS}
    rules_ladder = None
    built = eval_lib.build_ranking(run, CTX)
    if built:
        ranked, meta = built
        by_k = {row["k"]: row for row in eval_lib.ladder(ranked, meta, truth)}
        for k in RUNGS:
            rungs[f"P{k}"] = by_k[k]["hits"] / k
        rules_ladder = {k: by_k[k]["rules_hits"] / k for k in RUNGS}
    return {
        "run": path.stem, "status": run["status"], "K": len(union),
        "P": hits / len(union) if union else 0.0,
        "R": hits / planted_total, "hits": hits,
        "base": base / len(union) if union else 0.0,
        "only_a": len(primary[a] - primary[b]),
        "only_b": len(primary[b] - primary[a]),
        "shared": len(primary[a] & primary[b]),
        "rules_ladder": rules_ladder,
        **rungs,
    }


rows = [score(p) for p in made]
print(f"\n{'run':<34}{'status':<11}{'K':>4}{'P@K':>7}{'R@K':>7}"
      f"{'hits':>5}{'rules':>7}  complementarity")
for r in rows:
    print(f"{r['run']:<34}{r['status']:<11}{r['K']:>4}{r['P']:>7.0%}"
          f"{r['R']:>7.1%}{r['hits']:>5}{r['base']:>7.0%}  "
          f"{r['only_a']}+{r['only_b']} unique / {r['shared']} shared")
print("  ('rules' = rules-only top-K of the same pools, no LLM -- the "
      "equal-K baseline)")

# the ladder as its own table: four extra percent columns would crowd the
# one above, and a rung is a different question anyway (fixed K, whole
# ranking) than the union columns (the observers' own K)
print(f"\n{'run':<34}{'P@50':>7}{'P@100':>7}{'P@150':>7}{'P@200':>7}"
      "   fixed-K ladder, confidence-tier ranking")
for r in rows:
    if r["P50"] is None:
        print(f"{r['run']:<34}" + f"{'--':>7}" * len(RUNGS)
              + "   no recorded scopes/pools -- excluded from means")
    else:
        print(f"{r['run']:<34}{r['P50']:>7.0%}{r['P100']:>7.0%}"
              f"{r['P150']:>7.0%}{r['P200']:>7.0%}")

valid = [r for r in rows if r["status"] == "completed"]
if len(valid) >= 2:
    for metric in ("K", "P", "R", "base", "P50", "P100", "P150", "P200"):
        values = [r[metric] for r in valid if r[metric] is not None]
        if len(values) < 2:
            continue     # a rung fewer than two runs carry has no spread
        print(f"  {metric}: mean {statistics.mean(values):.3f} "
              f"+/- {statistics.stdev(values):.3f}  (n={len(values)})")
elif valid:
    print("  only one valid run -- no spread to report")
else:
    print("  NO valid runs in this batch; nothing to aggregate")

# the ladder's own no-LLM floor: the same uncapped pools zipped, cut at
# each rung -- what the ranking must beat before selection means anything
pooled = [r for r in valid if r["rules_ladder"]]
if pooled:
    print(f"  rules-only ladder mean (n={len(pooled)}): " + "  ".join(
        f"P@{k} {statistics.mean([r['rules_ladder'][k] for r in pooled]):.1%}"
        for k in RUNGS))
