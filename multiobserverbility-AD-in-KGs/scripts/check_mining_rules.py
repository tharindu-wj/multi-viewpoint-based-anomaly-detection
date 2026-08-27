"""Print what every mining rule finds, for human eyes. No agent, no API.

    python scripts/check_mining_rules.py

Run before any agent touches them. Whatever a rule surfaces is exactly
what a judge will be handed -- if the candidates here are junk, every verdict
downstream is junk with a rationale.

unlikely_facts is skipped politely until 2_train_scorer.py has run.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from loaders.context import get_context  # noqa: E402
from tools.mining_rules import RULES  # noqa: E402

ctx = get_context()
ALL_RELATIONS = set(ctx.relations)

for name, rule in RULES.items():
    print("\n" + "=" * 72)
    print(f"  {name}  (scope = every relation)")
    print("=" * 72)
    try:
        found = rule.find(ALL_RELATIONS, ctx)
    except RuntimeError as refusal:
        print(f"  refused: {refusal}")
        continue

    again = rule.find(ALL_RELATIONS, ctx)
    print(f"  {len(found)} candidates   deterministic: {found == again}")
    for triple, note in found[:6]:
        print(f"    {ctx.triple_text(triple)}")
        print(f"        {note}")
    if len(found) > 6:
        print(f"    ... and {len(found) - 6} more")

# The scoped probe uses the loaded dataset's rarest relation, so this rig
# works unchanged when loaders/active.py points somewhere else.
import collections  # noqa: E402

counts = collections.Counter(r for _, r, _ in ctx.triples)
probe_id, _ = counts.most_common()[-1]
print(f"\nscoped run -- odd_pairs on '{ctx.relation_label(probe_id)}' only:")
for triple, note in RULES["odd_pairs"].find({probe_id}, ctx)[:8]:
    print(f"    {ctx.triple_text(triple)}   [{note}]")
