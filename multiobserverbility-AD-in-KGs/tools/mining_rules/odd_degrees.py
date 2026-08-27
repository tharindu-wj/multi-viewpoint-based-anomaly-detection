"""Mining rule: an entity with far fewer or far more records than its kind.

TAXO types this rule mines (Senaratne et al., arXiv:2412.04780, section 5):
    Unusual - rare entity        an entity with strikingly few facts next to
                                 entities of its kind
    Unusual - prolific entity    an entity holding strikingly many records
                                 in one seat of one relation

One statistic, two tails. TAXO itself says unusual entities need no
correction -- most findings here are TRUE facts, and their value is what the
note can say about what is missing or excessive, not a falsehood lead. That
is why both tails carry hard caps: a handful of well-chosen findings, never
a page-flood of celebrities.

WORKED EXAMPLE (invented entities -- no dataset supplies these):

    THINLY RECORDED
        F has 2 facts in the whole graph; the typical entity of F's most
        specific kind has 40. Nothing false -- but a judge may want to know
        the record barely exists.

    UNUSUALLY MANY
        G holds 11 --made by-- records as tail, where the typical maker
        holds 2 (99th percentile 6). Eleven of anything usually single is
        either a hub, a merge error, or fame -- the observer decides which.

HOW IT COUNTS:
    1. One pass counts every entity's facts (both endpoints, whole graph).
    2. THIN TAIL: an entity's peer group is its most specific kind with at
       least MIN_PEERS members; fire when the entity's count is at most a
       third of the peer median (and the median is at least SOLID_MEDIAN,
       so a third of it means something). Rank by count/median, keep the
       LOW_CAP thinnest, emit ONE in-scope representative edge per entity.
    3. HEAVY TAIL: per in-scope (relation, slot), count each occupant's
       edges in that seat and compare against occupants sharing a kind
       (at least SLOT_MIN_PEERS of them). Fire on the extreme tail only:
       count >= HIGH_MIN, at least HIGH_RATIO times the peer median, AND
       above the peer 99th percentile. Keep the HIGH_CAP most extreme, one
       representative edge per (entity, relation, slot).
    4. The two tails are interleaved so neither buries the other.

Degree statistics are whole-graph (within a small scope every entity looks
thin); the heavy tail's per-slot statistics are exact for the scope because
a relation is wholly in or out of it.

Deterministic, no model, no ground truth.
"""
import collections
import statistics

NAME = "odd_degrees"

#: a kind qualifies as a peer group from this many members
MIN_PEERS = 8
#: the thin tail fires at one third of the peer median...
LOW_RATIO = 3
#: ...when the median itself is at least this (a third of 3 says nothing)
SOLID_MEDIAN = 6
#: at most this many thinly-recorded entities are emitted
LOW_CAP = 5
#: heavy tail: a slot needs this many same-kind occupants to define "usual"
SLOT_MIN_PEERS = 10
#: heavy tail fires at >= this many edges...
HIGH_MIN = 4
#: ...and >= this multiple of the peer median, above the 99th percentile
HIGH_RATIO = 5
#: at most this many prolific findings are emitted
HIGH_CAP = 10


def find(scope_ids, ctx):
    """Thin and heavy degree outliers vs same-kind peers, interleaved."""
    degree = collections.Counter()
    for head, relation, tail in ctx.triples:
        degree[head] += 1
        degree[tail] += 1

    members = collections.defaultdict(list)
    for entity in degree:
        for kind in ctx.entity_types.get(entity) or []:
            members[kind].append(entity)
    peer_groups = {kind: group for kind, group in members.items()
                   if len(group) >= MIN_PEERS}
    median_of = {kind: statistics.median(degree[e] for e in group)
                 for kind, group in peer_groups.items()}

    representative = {}
    for triple in sorted(ctx.triples):
        head, relation, tail = triple
        if relation not in scope_ids:
            continue
        representative.setdefault(head, triple)
        representative.setdefault(tail, triple)

    # -- thin tail ----------------------------------------------------------
    thin = []
    for entity, count in degree.items():
        kinds = [k for k in ctx.entity_types.get(entity) or []
                 if k in peer_groups]
        if not kinds or entity not in representative:
            continue
        kind = min(kinds, key=lambda k: len(peer_groups[k]))
        median = median_of[kind]
        if median >= SOLID_MEDIAN and count * LOW_RATIO <= median:
            thin.append((count / median, entity, count, median, kind))
    thin_queue = []
    for _, entity, count, median, kind in sorted(thin)[:LOW_CAP]:
        note = (f"'{ctx.entity_label(entity)}' has only {count} facts in "
                f"the whole graph, where the typical {kind} has "
                f"{median:.0f} -- thinly recorded, not necessarily wrong")
        thin_queue.append((representative[entity], note))

    # -- heavy tail ---------------------------------------------------------
    slot_degree = collections.defaultdict(collections.Counter)
    slot_edges = collections.defaultdict(list)
    for triple in ctx.triples:
        head, relation, tail = triple
        if relation not in scope_ids:
            continue
        slot_degree[(relation, "head")][head] += 1
        slot_degree[(relation, "tail")][tail] += 1
        slot_edges[(relation, "head", head)].append(triple)
        slot_edges[(relation, "tail", tail)].append(triple)

    heavy = {}
    for (relation, slot), counts in slot_degree.items():
        by_kind = collections.defaultdict(list)
        for entity, count in counts.items():
            for kind in ctx.entity_types.get(entity) or []:
                by_kind[kind].append((entity, count))
        for kind, occupants in by_kind.items():
            if len(occupants) < SLOT_MIN_PEERS:
                continue
            spread = sorted(count for _, count in occupants)
            median = spread[len(spread) // 2]
            p99 = spread[int(0.99 * (len(spread) - 1))]
            for entity, count in occupants:
                if (count >= HIGH_MIN and count >= HIGH_RATIO * median
                        and count > p99):
                    key = (relation, slot, entity)
                    ratio = count / max(median, 1)
                    prior = heavy.get(key)
                    # an entity can fire under several kinds; keep the one
                    # with the most peers -- the strongest norm
                    if prior is None or len(occupants) > prior[1]:
                        heavy[key] = (ratio, len(occupants), count, median,
                                      p99, kind)
    heavy_queue = []
    ranked = sorted(heavy.items(),
                    key=lambda item: (-item[1][0], item[0]))[:HIGH_CAP]
    for (relation, slot, entity), (_, peers, count, median, p99, kind) in ranked:
        note = (f"the {slot}, '{ctx.entity_label(entity)}', holds {count} "
                f"records in this seat, where the typical {kind} holds "
                f"{median} (99th percentile {p99}, {peers} peers) -- "
                f"unusually many, not necessarily wrong")
        heavy_queue.append((min(slot_edges[(relation, slot, entity)]), note))

    queues = [thin_queue, heavy_queue]
    candidates, position = [], 0
    while any(position < len(queue) for queue in queues):
        for queue in queues:
            if position < len(queue):
                candidates.append(queue[position])
        position += 1

    unique = {}
    for triple, note in candidates:
        unique.setdefault(triple, note)
    return list(unique.items())
