"""The pool: every mining rule's findings in one scope, merged and ranked.

Before the pool, an observer chose ONE rule at a time from a menu, and which
rule it happened to trust decided the run (measured: the rule an observer
picked first explained every planted catch and every zero run). The pool
removes that choice. All rules sweep the observer's scope at once; their
findings are merged into one ranked list, and the observer's viewpoint acts
where it should -- on WHICH leads it shortlists, not on which rule it reads.

HOW THE POOL IS ORDERED (deterministic, no model, no ground truth):
    1. CORROBORATED leads first: a fact that two independent rules surfaced
       is a stronger lead than one either found alone -- two unrelated
       counting arguments agree that it is odd. Ordered by how many rules
       agree, then by the best rank any of them gave it.
    2. Then a ROUND-ROBIN across the rules, each rule's own strongest-first
       order: the front of the pool is a cross-section of every kind of
       suspicious, never the front of the biggest rule (odd_values alone
       finds ~270 candidates graph-wide; concatenation would be two rules'
       front pages and nothing else).
    3. Cut at POOL_CAP. Deep pages of every rule are weak by the rule's own
       ranking, and a bounded pool is one an observer can actually survey
       within its tool budget.

Every entry keeps EVERY rule's note, so the observer reads each rule's
argument in plain words and the dashboard can draw whichever one it likes.

Entry shape (JSON-safe, stored in session state as the observer saw it):
    {"triple": [h, r, t], "text": "...", "rules": ["odd_pairs", ...],
     "notes": {"odd_pairs": "...", ...}}
"""
from tools.mining_rules import RULES

#: the pool served to an observer is at most this long
POOL_CAP = 120


def build_pool(scope_ids, ctx, cap=POOL_CAP):
    """Merged, ranked findings of every rule on this scope."""
    rank = {}                # rule -> {triple: position in that rule's list}
    notes = {}               # triple -> {rule: note}
    for name, rule in RULES.items():
        try:
            found = rule.find(scope_ids, ctx)
        except RuntimeError:
            continue         # a rule that refuses (missing scores) just sits out
        rank[name] = {}
        for position, (triple, note) in enumerate(found):
            rank[name].setdefault(triple, position)
            notes.setdefault(triple, {})[name] = note

    def entry(triple):
        rules = [name for name in RULES if name in notes[triple]]
        return {"triple": list(triple), "text": ctx.triple_text(triple),
                "rules": rules,
                "notes": {name: notes[triple][name] for name in rules}}

    pool, taken = [], set()

    corroborated = [t for t, by in notes.items() if len(by) > 1]
    corroborated.sort(key=lambda t: (-len(notes[t]),
                                     min(rank[r][t] for r in notes[t]), t))
    for triple in corroborated:
        pool.append(entry(triple))
        taken.add(triple)

    queues = [[t for t, _ in sorted(rank[name].items(), key=lambda kv: kv[1])]
              for name in RULES if name in rank]
    position = 0
    while len(pool) < cap and any(position < len(q) for q in queues):
        for queue in queues:
            if position < len(queue) and queue[position] not in taken:
                pool.append(entry(queue[position]))
                taken.add(queue[position])
        position += 1

    return pool[:cap]


def interleave(pools, k):
    """The rules-only shortlist at budget k: the observers' pools zipped,
    strongest first, duplicates dropped. What the union would be if nobody
    judged -- the equal-K baseline every live run must beat."""
    out, seen = [], set()
    for position in range(max((len(p) for p in pools), default=0)):
        for pool in pools:
            if position < len(pool):
                triple = tuple(pool[position]["triple"])
                if triple not in seen:
                    seen.add(triple)
                    out.append(triple)
            if len(out) >= k:
                return out
    return out
