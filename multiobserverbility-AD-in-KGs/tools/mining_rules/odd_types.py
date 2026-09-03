"""Mining rule: an entity of a kind this slot has never held before.

TAXO type this rule mines (Senaratne et al., arXiv:2412.04780, section 5):
    Inconsistency - invalid predicate    a predicate used with a subject or
                                         object of a kind it is never used
                                         with -- a drama in a location-
                                         holder's seat

This rule never reads meanings -- it only counts TYPE LABELS. The question
it asks of every in-scope triple is leave-one-out support: "setting this
entity itself aside, has ANY other entity of ANY of its kinds ever occupied
this slot of this relation?" Zero is the fire condition.

WORKED EXAMPLE (invented entities -- no dataset supplies these):

    tails of "stored at":  120 warehouses, 40 depots, 15 workshops
    X --stored at-- Y      where Y's only kind is "disease"

    No other disease has ever been a "stored at" tail, so the edge fires --
    even though no single kind dominates the slot, which is exactly where a
    dominance test goes blind. A warehouse at 12% of the slot never fires:
    its kind is attested, merely a minority.

HOW IT COUNTS:
    1. One pass collects the DISTINCT occupants of each (relation, slot),
       heads and tails separately; each occupant set expands through the
       entities' type labels into a support table: how many distinct
       occupants of this slot carry each kind.
    2. For every in-scope triple and each of its two slots: skip slots with
       fewer than MIN_OCCUPANTS distinct occupants (too thin to say what
       "never" means) and entities with no type labels; otherwise take the
       occupant's best kind -- the one with the most OTHER occupants
       carrying it. Fire when even the best kind has zero others.
    3. One candidate per (relation, slot, entity), however many edges the
       entity sits in -- the note carries the edge count, so one repeat
       offender cannot flood a reading budget with copies of one question.

Support is measured from the data (no schema file exists), so this is
"unprecedented for this graph", not "invalid by decree" -- whether
unprecedented is wrong stays the observer's call.

Deterministic, no model, no ground truth.
"""
import collections

NAME = "odd_types"

#: a slot must have at least this many distinct occupants before "no other
#: entity of this kind" means anything
MIN_OCCUPANTS = 5


def find(scope_ids, ctx):
    """Edges whose head or tail is of a kind its slot has never held."""
    occupants = collections.defaultdict(set)
    for head, relation, tail in ctx.triples:
        occupants[(relation, "head")].add(head)
        occupants[(relation, "tail")].add(tail)

    support = {}
    for key, entities in occupants.items():
        counts = collections.Counter()
        # sorted: Counter.most_common breaks count ties by insertion order,
        # and set iteration order varies with the process hash seed -- the
        # note text must be identical on every rebuild (determinism claim)
        for entity in sorted(entities):
            for kind in ctx.entity_types.get(entity) or []:
                counts[kind] += 1
        support[key] = counts

    edges_of = collections.defaultdict(list)
    for triple in ctx.triples:
        head, relation, tail = triple
        if relation not in scope_ids:
            continue
        for slot, entity in (("head", head), ("tail", tail)):
            key = (relation, slot)
            if len(occupants[key]) < MIN_OCCUPANTS:
                continue
            kinds = ctx.entity_types.get(entity) or []
            if not kinds:
                continue
            others = max(support[key][kind] - 1 for kind in kinds)
            if others == 0:
                edges_of[(relation, slot, entity)].append(triple)

    candidates = []
    # Strongest lead first: "no other entity of this kind" carries more
    # weight in a 90-occupant slot than a 6-occupant one.
    for (relation, slot, entity), edges in sorted(
            edges_of.items(),
            key=lambda item: (-len(occupants[(item[0][0], item[0][1])]),
                              item[0])):
        key = (relation, slot)
        kinds = ", ".join(ctx.entity_types.get(entity) or [])
        usual = ", ".join(f"{kind} x{count}" for kind, count
                          in support[key].most_common(2))
        note = (f"{slot} is {kinds}; no other entity of any of these kinds "
                f"appears as {slot} here "
                f"({len(occupants[key])} distinct {slot}s; "
                f"usual kinds: {usual})")
        if len(edges) > 1:
            note += (f" -- this entity sits in {len(edges)} such edges; "
                     f"judging one judges the pattern")
        candidates.append((min(edges), note))

    # A triple can fire in both slots; keep the first note it earned. The
    # insertion order IS the ranking -- do not re-sort it away.
    unique = {}
    for triple, note in candidates:
        unique.setdefault(triple, note)
    return list(unique.items())
