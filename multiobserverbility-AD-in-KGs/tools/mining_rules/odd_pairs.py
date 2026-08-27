"""Mining rule: the links between two things do not sit right together.

TAXO types this rule mines (Senaratne et al., arXiv:2412.04780, section 5):
    Contradictions - contradicting facts    two records on one pair that can
                                            hardly co-exist
    Incorrectness  - incorrect predicate    TAXO's own example IS the other
                                            half of its contradiction example;
                                            a wrong link shows up through the
                                            clash it makes
    Ambiguity      - entity ambiguity       both paper examples are pair
                                            shapes: an impossible pair of
                                            links, and a thing linked to
                                            itself
    Missingness (graph-level, mirror case)  a mostly-two-way relation
                                            recorded one way only

WORKED EXAMPLE (invented entities -- no dataset supplies these):

    RARE COMBINATION
        A --parent of-- B     and     B --married to-- A
        "parent of" links 900 pairs, "married to" links 400, yet this
        COMBINATION occurs on exactly 1 pair in the whole graph. Two common
        relations that almost never share a pair are worth a judge's look.

    SELF LINK
        C --succeeded by-- C
        one entity on both ends, on a relation where 0.4% of records loop.

    MISSING MIRROR
        A --linked with-- B   recorded, but NOT   B --linked with-- A,
        on a relation that is 90% two-way. A fabricated edge is usually
        one-way too -- nobody plants its reverse.

HOW IT COUNTS:
    1. One pass groups every edge by its unordered entity pair, keeping the
       (relation, direction) signature of each edge; self links are kept
       aside per relation; per-relation symmetry (share of edges whose exact
       reverse exists) and distinct-pair counts come from the same pass.
    2. RARE COMBINATION: for every pair carrying two or more signatures
       (capped at COMBO_EDGE_CAP), count each canonical signature
       combination across ALL pairs in the graph. A pair fires when one of
       its combinations is carried by at most RARE_MAX pairs graph-wide
       while each member relation links at least MIN_PAIRS pairs -- rarity
       of the coincidence, not of the relations. The same relation in both
       directions is exonerated when the relation is at least SYM_EXONERATE
       symmetric: that is ordinary reciprocity, not a clash.
    3. SELF LINK: every h == t edge fires when its relation has at least
       MIN_EDGES records of which fewer than SELF_SHARE self-loop.
    4. MISSING MIRROR: on relations at least MIN_SYMMETRY two-way, every
       edge whose reverse is absent fires (the retired one_way_links rule,
       absorbed here as the absence case of the same pair statistic).
    5. One candidate per pair, and round-robin across the three cases and
       across the mirror case's relations, so no single case or bulky
       relation can bury the others pages deep.

Statistics are whole-graph; only in-scope triples are emitted. Deciding
WHICH record of a clash is the wrong one needs world knowledge -- that is
the observer's half of the work, never this rule's.

Deterministic, no model, no ground truth.
"""
import collections
import itertools

NAME = "odd_pairs"

#: a combination is rare when at most this many pairs carry it graph-wide
RARE_MAX = 2
#: ...and only if each member relation links at least this many pairs
MIN_PAIRS = 20
#: same-relation-both-directions is normal when the relation is this symmetric
SYM_EXONERATE = 0.3
#: the mirror case only speaks about relations at least this two-way
MIN_SYMMETRY = 0.5
#: self links fire on relations with at least this many records...
MIN_EDGES = 20
#: ...of which fewer than this share self-loop
SELF_SHARE = 0.05
#: a pair with more parallel edges than this is odd enough as-is; its
#: combinations are not enumerated quadratically
COMBO_EDGE_CAP = 8


def _edge(pair, sig):
    """Rebuild the (h, r, t) triple from a pair and its signature."""
    (a, b), (relation, a_to_b) = pair, sig
    return (a, relation, b) if a_to_b else (b, relation, a)


def find(scope_ids, ctx):
    """One candidate per suspicious pair, three cases, interleaved."""
    present = set(ctx.triples)

    pair_sigs = collections.defaultdict(set)
    self_loops = collections.defaultdict(list)
    by_relation = collections.defaultdict(list)
    for head, relation, tail in ctx.triples:
        by_relation[relation].append((head, relation, tail))
        if head == tail:
            self_loops[relation].append((head, relation, tail))
            continue
        a, b = (head, tail) if head < tail else (tail, head)
        pair_sigs[(a, b)].add((relation, head == a))

    symmetry = {}
    for relation, triples in by_relation.items():
        mirrored = sum(1 for t in triples if (t[2], t[1], t[0]) in present)
        symmetry[relation] = mirrored / len(triples)

    rel_pairs = collections.Counter()
    for sigs in pair_sigs.values():
        for relation in {relation for relation, _ in sigs}:
            rel_pairs[relation] += 1

    # -- case 1: rare combinations ----------------------------------------
    combo_count = collections.Counter()
    for sigs in pair_sigs.values():
        if len(sigs) < 2:
            continue
        for sig_a, sig_b in itertools.combinations(sorted(sigs)[:COMBO_EDGE_CAP], 2):
            combo_count[_canonical(sig_a, sig_b)] += 1

    combo_queue = []
    for pair, sigs in sorted(pair_sigs.items()):
        if len(sigs) < 2:
            continue
        rare = []
        for sig_a, sig_b in itertools.combinations(sorted(sigs)[:COMBO_EDGE_CAP], 2):
            key = _canonical(sig_a, sig_b)
            r1, r2, direction = key
            if combo_count[key] > RARE_MAX:
                continue
            if rel_pairs[r1] < MIN_PAIRS or rel_pairs[r2] < MIN_PAIRS:
                continue
            if r1 == r2 and symmetry.get(r1, 0) >= SYM_EXONERATE:
                continue                # ordinary reciprocity, not a clash
            rare.append(key)
        if not rare:
            continue
        in_scope = sorted(_edge(pair, sig) for sig in sigs
                          if sig[0] in scope_ids)
        if not in_scope:
            continue
        listed = "; ".join(
            f"'{ctx.entity_label(h)}' --{ctx.relation_label(r)}-- "
            f"'{ctx.entity_label(t)}'"
            for h, r, t in sorted(_edge(pair, sig) for sig in sigs))
        fewest = min(combo_count[key] for key in rare)
        note = (f"these two are linked {len(sigs)} ways: {listed} -- a "
                f"combination carried by only {fewest} pair"
                f"{'' if fewest == 1 else 's'} in the whole graph")
        combo_queue.append((fewest, in_scope[0], note))
    combo_queue = [(triple, note)
                   for _, triple, note in sorted(combo_queue)]

    # -- case 2: self links -------------------------------------------------
    self_queue = []
    for relation in sorted(self_loops):
        if relation not in scope_ids:
            continue
        total = len(by_relation[relation])
        loops = self_loops[relation]
        if total < MIN_EDGES or len(loops) / total >= SELF_SHARE:
            continue
        note = (f"links this entity to itself, on a relation where only "
                f"{len(loops)} of {total} records do")
        self_queue.extend((triple, note) for triple in sorted(loops))

    # -- case 3: missing mirrors (the absorbed one_way_links) ---------------
    mirror_queues = []
    for relation, triples in by_relation.items():
        if relation not in scope_ids or symmetry[relation] < MIN_SYMMETRY:
            continue
        one_way = [t for t in triples
                   if t[0] != t[2] and (t[2], t[1], t[0]) not in present]
        if not one_way:
            continue
        note = (f"recorded one way only, on a relation that is "
                f"{symmetry[relation]:.0%} two-way")
        mirror_queues.append((symmetry[relation],
                              [(t, note) for t in sorted(one_way)]))
    mirror_queues.sort(key=lambda q: -q[0])

    # Round-robin across every queue -- a page should be a cross-section of
    # the cases, not the front of the largest queue (the one_way_links lesson).
    queues = [combo_queue, self_queue] + [q for _, q in mirror_queues]
    candidates, position = [], 0
    while any(position < len(queue) for queue in queues):
        for queue in queues:
            if position < len(queue):
                candidates.append(queue[position])
        position += 1

    # A triple can enter through two cases; the first note it earned wins.
    unique = {}
    for triple, note in candidates:
        unique.setdefault(triple, note)
    return list(unique.items())


def _canonical(sig_a, sig_b):
    """Order-free key for a signature combination on one pair."""
    (r1, d1), (r2, d2) = sorted((sig_a, sig_b))
    return (r1, r2, "same" if d1 == d2 else "opposite")
