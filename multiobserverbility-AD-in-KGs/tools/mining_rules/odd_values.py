"""Mining rule: one entity's set of values under one relation looks wrong.

TAXO types this rule mines (Senaratne et al., arXiv:2412.04780, section 5):
    Ambiguity    - predicate ambiguity   the same subject and relation with
                                         values that overlap or nest, so the
                                         relation's range is unclear
    Redundancies - redundant facts       two values that look like the same
                                         thing recorded twice
    Duplicates   - duplicate facts       the very same value twice -- kept
                                         for completeness; the preparation
                                         step dedups the graph, so this
                                         cannot occur here (its GUARDS line
                                         proves duplicates = 0 every run)
    (also, as the extra-values case)     several values where one is the
                                         rule -- the retired too_many_values
                                         rule, absorbed unchanged

WORKED EXAMPLE (invented entities -- no dataset supplies these):

    EXTRA VALUES (on a relation where 96% of entities hold exactly one)
        M1 --serial number-- SN-100
        M1 --serial number-- SN-733     the anomaly is the PAIR; either edge
                                        alone looks perfectly normal

    NESTED VALUES (on a relation where several values are normal)
        P --based in-- Q-Town
        P --based in-- Q-Region         and the graph itself records
        Q-Town --inside-- Q-Region      so one value may contain the other

    LOOKALIKE VALUES
        W --made-- "Object 7"
        W --made-- "Object 7 (2001)"    names differing only by a trailing
                                        qualifier: possibly one thing twice

HOW IT COUNTS:
    1. Group the scope's triples by relation, then by head entity.
    2. EXTRA VALUES: keep relations where at least MOSTLY_SINGLE of heads
       hold exactly one value; emit every edge of every multi-valued head,
       the note listing all values.
    3. On the other relations (several values normal), inspect each head's
       value set (2..MAX_GROUP values):
       NESTED -- two values directly linked, anywhere in the graph, by a
       DIFFERENT relation that is hierarchy-shaped (reciprocity below
       LOW_RECIPROCITY; peer-like mutual relations prove nothing). The
       linking edge is the graph's own evidence the values overlap.
       LOOKALIKE -- two values whose labels are stem-equal: identical after
       lowercasing, dropping a trailing parenthetical and trailing
       digits/qualifiers. String structure only, never meanings.
    4. Both edges of an offending pair are emitted with one shared note
       (verdicts are per triple; the anomaly is the pair). At most one pair
       per head and GROUP_CAP groups per set-shape case; then round-robin
       across every extra-values relation AND the two set-shape queues, so
       neither a bulky relation nor the usually-true set-shape findings can
       bury the measured extra-values detector.

Whether several values are an error, an unclear relation, or honest reality
is the observer's call -- this rule only points at the pair.

Deterministic, no model, no ground truth.
"""
import collections
import itertools
import re

NAME = "odd_values"

#: a relation counts as "typically single-valued" when this share of its
#: heads carry exactly one value
MOSTLY_SINGLE = 0.9
#: a linking relation is hierarchy-shaped below this reciprocity
LOW_RECIPROCITY = 0.2
#: value sets larger than this are skipped -- a 40-value head is a hub,
#: not a pair question
MAX_GROUP = 12
#: at most this many nested / lookalike groups each
GROUP_CAP = 15

_TRAILING = re.compile(r"(\s*\(.*\)\s*$)|([\s\-_,.]*\d+[\s\-_,.]*$)")


def _stem(label):
    """Lowercased label minus trailing parenthetical / digits. '' if that
    would erase everything."""
    stem = label.strip().lower()
    while True:
        shorter = _TRAILING.sub("", stem)
        if shorter == stem:
            return stem
        stem = shorter


def find(scope_ids, ctx):
    """Suspicious value sets, three cases, interleaved."""
    tails_of_head = collections.defaultdict(lambda: collections.defaultdict(list))
    for head, relation, tail in ctx.triples:
        if relation in scope_ids:
            tails_of_head[relation][head].append(tail)

    # Whole-graph context: reciprocity per relation, and which relations
    # directly link any unordered entity pair.
    present = set(ctx.triples)
    edge_count = collections.Counter()
    mutual_count = collections.Counter()
    linked_by = collections.defaultdict(set)
    for head, relation, tail in ctx.triples:
        edge_count[relation] += 1
        if (tail, relation, head) in present:
            mutual_count[relation] += 1
        if head != tail:
            key = (head, tail) if head < tail else (tail, head)
            linked_by[key].add(relation)
    reciprocity = {r: mutual_count[r] / edge_count[r] for r in edge_count}

    extra_by_relation = collections.defaultdict(list)
    extra_share = {}
    nested_queue, lookalike_queue = [], []
    for relation, heads in sorted(tails_of_head.items()):
        single = sum(1 for tails in heads.values() if len(set(tails)) == 1)
        share = single / len(heads)
        extra_share[relation] = share

        if share >= MOSTLY_SINGLE:
            for head, tails in sorted(heads.items()):
                values = sorted(set(tails))
                if len(values) < 2:
                    continue
                listed = ", ".join(ctx.entity_label(t) for t in values)
                note = (f"{len(values)} values on a relation where "
                        f"{share:.0%} of entities have one: {listed}")
                for tail in values:
                    extra_by_relation[relation].append(((head, relation, tail),
                                                        note))
            continue

        # several values are normal here -- what are the values to each other?
        for head, tails in sorted(heads.items()):
            values = sorted(set(tails))
            if not 2 <= len(values) <= MAX_GROUP:
                continue
            pair = _nested_pair(relation, values, linked_by, reciprocity)
            if pair:
                a, b, linker = pair
                note = (f"holds both '{ctx.entity_label(a)}' and "
                        f"'{ctx.entity_label(b)}' here, and the graph itself "
                        f"records '{ctx.entity_label(a)}' "
                        f"--{ctx.relation_label(linker)}-- "
                        f"'{ctx.entity_label(b)}' -- one value may contain "
                        f"the other")
                nested_queue.append(((head, relation, a), note))
                nested_queue.append(((head, relation, b), note))
                continue
            pair = _lookalike_pair(values, ctx)
            if pair:
                a, b = pair
                note = (f"values '{ctx.entity_label(a)}' and "
                        f"'{ctx.entity_label(b)}' differ only by a trailing "
                        f"qualifier -- possibly one thing recorded twice")
                lookalike_queue.append(((head, relation, a), note))
                lookalike_queue.append(((head, relation, b), note))

    nested_queue = nested_queue[:GROUP_CAP * 2]
    lookalike_queue = lookalike_queue[:GROUP_CAP * 2]

    # Round-robin across every extra-values relation AND the two set-shape
    # cases -- a page should be a cross-section, not the front of the
    # biggest queue. One queue per relation (not one pooled queue) keeps the
    # measured detector -- the extra-values case -- from being diluted by
    # the set-shape cases, whose findings are usually true facts.
    # Strongest lead first: a 98%-single relation's extra value is a
    # stronger lead than a 91% one, so its queue leads each round.
    queues = [extra_by_relation[r]
              for r in sorted(extra_by_relation,
                              key=lambda r: (-extra_share[r], r))]
    queues += [nested_queue, lookalike_queue]
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


def _nested_pair(relation, values, linked_by, reciprocity):
    """First value pair directly linked by a hierarchy-shaped OTHER relation."""
    for a, b in itertools.combinations(values, 2):
        key = (a, b) if a < b else (b, a)
        linkers = sorted(r for r in linked_by.get(key, ())
                         if r != relation and reciprocity[r] < LOW_RECIPROCITY)
        if linkers:
            return a, b, linkers[0]
    return None


def _lookalike_pair(values, ctx):
    """First value pair whose labels are stem-equal but not identical."""
    for a, b in itertools.combinations(values, 2):
        label_a, label_b = ctx.entity_label(a), ctx.entity_label(b)
        stem_a = _stem(label_a)
        if stem_a and label_a != label_b and stem_a == _stem(label_b):
            return a, b
    return None
