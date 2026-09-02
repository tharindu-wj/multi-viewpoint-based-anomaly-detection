"""Score a recorded observation run against the answer key. Nothing is judged here.

    python scripts/4_evaluate_verdicts.py                    the newest run
    python scripts/4_evaluate_verdicts.py --run runs/run_...json

THE ONLY READER OF ground_truth.tsv. The agents never saw it; this script
checks what they decided, after every decision is frozen in the run file.

Two halves, kept strictly apart:

  OBJECTIVE   anomaly-verdicts vs the planted falsehoods. A planted triple
              is false by human verification, so calling it an anomaly is
              measurably right, whatever the caller's norms.

  VIEWPOINT   the composed picture: what each observer flagged, where they
              agree, and where the SAME fact got DIFFERENT verdicts. A norm
              disagreement on a true fact has no answer key by construction
              -- it is reported with both reasons, never scored.

A caution baked into the numbers: kind=real means the preparation did not plant the
triple, not that it is true -- the graph carries its source's own mistakes.
A "false positive" here may be a discovery.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import argparse  # noqa: E402
import collections  # noqa: E402

from loaders import graph  # noqa: E402
from loaders.active import DATASET  # noqa: E402
from loaders.context import get_context  # noqa: E402
from tools._observers import OBSERVER_NAMES  # noqa: E402
from tools.mining_rules.pool import interleave  # noqa: E402

parser = argparse.ArgumentParser()
parser.add_argument("--run", default=None, help="run file; default is newest")
args = parser.parse_args()

path = Path(args.run) if args.run else None
if path and not path.is_absolute():
    path = ROOT / path
if path is None:
    found = sorted(DATASET.RUNS.glob("run_*_observers.json"))
    if not found:
        raise SystemExit("no observation runs yet. Run scripts/3_run_observers.py first.")
    path = found[-1]

run = json.loads(path.read_text(encoding="utf-8"))

if run["status"] == "invalid":
    raise SystemExit(f"{path.name} is INVALID -- its blindness proof failed. "
                     "Nothing in it is evidence.")
if run["status"] == "truncated":
    print(f"WARNING: {path.name} was TRUNCATED by the API, not by the agents.")
    print("  Missing verdicts below are a rate limit, not a decision.\n")

# ---- the answer key -------------------------------------------------------
truth = {}
for head, relation, tail, label, kind in (
        line.split("\t") for line in
        DATASET.TRUTH.read_text(encoding="utf-8").splitlines()):
    truth[(head, relation, tail)] = int(label)
planted_total = sum(truth.values())

ctx = get_context()
print(f"run: {path.name}")
print(f"{DATASET.NAME}: {len(truth)} triples, {planted_total} planted "
      f"verified-false")

# ---- OBJECTIVE: each observer vs the planted falsehoods --------------------
verdicts_by_agent = dict(zip(OBSERVER_NAMES, run["verdicts"]))

for name in OBSERVER_NAMES:
    judged = verdicts_by_agent[name]
    print("\n" + "=" * 70)
    print(f"  {name} -- OBJECTIVE")
    print("=" * 70)
    if not judged:
        print("  judged nothing.")
        continue

    by_verdict = collections.Counter(v["verdict"] for v in judged.values())
    print(f"  {len(judged)} judged: "
          + "  ".join(f"{k} {n}" for k, n in sorted(by_verdict.items())))

    flagged = {cid: v for cid, v in judged.items() if v["verdict"] == "anomaly"}
    hits = {cid: v for cid, v in flagged.items()
            if truth.get(tuple(v["triple"])) == 1}
    if flagged:
        print(f"  anomaly precision vs planted: {len(hits)}/{len(flagged)} "
              f"({len(hits) / len(flagged):.0%})  -- a flag on an unplanted triple may "
              f"still be a real error inherited from the source data")
    missed = [v for v in judged.values()
              if truth.get(tuple(v["triple"])) == 1 and v["verdict"] != "anomaly"]
    print(f"  planted seen but not flagged: {len(missed)}")
    for v in missed[:3]:
        print(f"    [{v['verdict']:>8}] {ctx.triple_text(tuple(v['triple']))[:56]}"
              f" -- {v['why'][:60]}")
    per_rule = collections.Counter(v["rule"] for v in judged.values())
    print(f"  candidates by rule: {dict(per_rule)}")

# ---- VIEWPOINT: composition and disagreement ------------------------------
verdict_of = {}
for name in OBSERVER_NAMES:
    for v in verdicts_by_agent[name].values():
        verdict_of.setdefault(tuple(v["triple"]), {})[name] = v

flags = {name: {t for t, by in verdict_of.items()
                if by.get(name, {}).get("verdict") == "anomaly"}
         for name in OBSERVER_NAMES}
agent_1, agent_2 = OBSERVER_NAMES
both_judged = [t for t, by in verdict_of.items() if len(by) == 2]

print("\n" + "=" * 70)
print("  UNION -- the system's detection output")
print("=" * 70)
# The research question is what DIFFERENT perspectives find, so detection
# is "flagged by at least one observer" -- agreement is the high-confidence
# tier inside it, never the definition. The union is stable under the
# review phase (a reviewer only re-judges facts already flagged), so it is
# measured over all flags; COMPLEMENTARITY is measured over PRIMARY flags
# (c-ids, an observer's own hunt) because the review phase deliberately
# converges the two sets afterwards.
union_flags = flags[agent_1] | flags[agent_2]
union_hits = sum(1 for t in union_flags if truth.get(t) == 1)
if union_flags:
    K = len(union_flags)
    print(f"  union flags K = {K} ({K / len(truth):.2%} of the graph)")
    print(f"  precision@K: {union_hits}/{K} ({union_hits / K:.0%})")
    print(f"  recall@K:    {union_hits}/{planted_total} "
          f"({union_hits / planted_total:.1%})  -- ceiling at this K is "
          f"{min(K, planted_total) / planted_total:.1%}: recall is "
          f"budget-bound, so read it beside its ceiling")
else:
    print("  union flags 0")
primary = {name: {tuple(v["triple"])
                  for cid, v in verdicts_by_agent[name].items()
                  if v["verdict"] == "anomaly" and cid.startswith("c")}
           for name in OBSERVER_NAMES}
only_1 = primary[agent_1] - primary[agent_2]
only_2 = primary[agent_2] - primary[agent_1]
shared = primary[agent_1] & primary[agent_2]
print(f"  complementarity of the two hunts (primary flags only):")
print(f"    {agent_1} alone {len(only_1)} "
      f"(planted {sum(1 for t in only_1 if truth.get(t) == 1)})   "
      f"{agent_2} alone {len(only_2)} "
      f"(planted {sum(1 for t in only_2 if truth.get(t) == 1)})   "
      f"both {len(shared)}")
print(f"  equal-K scorer comparison uses K = {len(union_flags)}")

# The rules-only baseline: the same pools the observers surveyed, zipped
# strongest-first and cut at the same K -- what the system would output if
# nobody selected or judged. Selection earns its place only above this line.
pools = [p.get("entries", []) for p in run.get("pools", [])]
if union_flags and any(pools):
    K = len(union_flags)
    rules_only = interleave(pools, K)
    rules_hits = sum(1 for t in rules_only if truth.get(t) == 1)
    print(f"  rules-only top-{K} (pools zipped, no LLM): {rules_hits}/{K} "
          f"({rules_hits / K:.0%}) -- the observers' selection "
          f"{'beats' if union_hits > rules_hits else 'does not beat'} it "
          f"({union_hits} vs {rules_hits})")
    for name, pool in zip(OBSERVER_NAMES, pools):
        in_pool = sum(1 for e in pool if truth.get(tuple(e["triple"])) == 1)
        print(f"    {name}: pool {len(pool)} leads, {in_pool} planted "
              f"({in_pool / len(pool):.0%} density)" if pool
              else f"    {name}: empty pool")

print("\n" + "=" * 70)
print("  COMPOSED -- the two viewpoints together")
print("=" * 70)
print(f"  flagged: {agent_1} {len(flags[agent_1])}, "
      f"{agent_2} {len(flags[agent_2])}, "
      f"union {len(union_flags)}, "
      f"agreement {len(flags[agent_1] & flags[agent_2])}")
print(f"  union catches {union_hits} planted -- vs "
      f"{sum(1 for t in flags[agent_1] if truth.get(t)==1)} and "
      f"{sum(1 for t in flags[agent_2] if truth.get(t)==1)} alone")
print(f"  judged by BOTH: {len(both_judged)}")

disagreements = [(t, verdict_of[t]) for t in both_judged
                 if verdict_of[t][agent_1]["verdict"]
                 != verdict_of[t][agent_2]["verdict"]]
print(f"\n  THE DISAGREEMENT SET -- same fact, different verdicts: "
      f"{len(disagreements)}")
print("  (no answer key can settle a norm disagreement on a true fact --")
print("   reported, never scored)")
for triple, by in disagreements:
    planted = "planted-false" if truth.get(triple) == 1 else "unplanted"
    print(f"\n    {ctx.triple_text(triple)}   [{planted}]")
    for name in OBSERVER_NAMES:
        v = by[name]
        print(f"      {name}: [{v['verdict']:>12}] {v['why'][:76]}")
