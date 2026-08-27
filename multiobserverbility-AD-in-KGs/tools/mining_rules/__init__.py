"""The mining rules -- deterministic sweeps of the graph, one kind of
suspicious each. NOT TOOLS: an agent reaches these only through
find_suspects, which serves what they found a page at a time.

Contract every rule honours:

    find(scope_ids, ctx) -> [(triple, note)]

  - scope_ids: the relation ids of the calling observer's viewpoint.
    STATISTICS ARE WHOLE-GRAPH, EMISSION IS IN-SCOPE: the viewpoint chooses
    what is judged, the whole graph decides what is normal. An observer's
    slice is too thin for stable thresholds, the partner evidence of a clash
    is usually outside the scope, and a note like "only 2 pairs in the whole
    graph" must mean the same thing whatever the scope is.
  - Deterministic: same graph in, same candidates out, every time.
  - Never a verdict: a rule surfaces a statistical oddity with a note that
    explains it in plain words; whether odd is WRONG is the observer's call.
  - No ground truth: no rule reads the answer key, ever.

The roster maps the TAXO anomaly taxonomy (Senaratne et al.,
arXiv:2412.04780, section 5) onto five rules -- each module's docstring
names the types it mines:

    odd_pairs       contradicting facts, incorrect predicate,
                    entity ambiguity, one-way records of two-way relations
    odd_types       invalid predicate (inconsistency)
    odd_values      predicate ambiguity, redundant facts, duplicate facts
    odd_degrees     rare entity, prolific entity (unusual)
    unlikely_facts  incorrectness at large -- the model-based plausibility
                    channel kept alongside the four counting rules

Missingness types stay where TAXO itself puts them: at the storage layer,
i.e. the ingest guards of scripts/1_prepare_graph.py, because a malformed
row is a certainty, not a lead for a judge.
"""
from tools.mining_rules import (odd_degrees, odd_pairs, odd_types,
                                odd_values, unlikely_facts)

#: the menu find_suspects serves. Each rule knows ONE kind of suspicious.
RULES = {module.NAME: module for module in (
    odd_pairs, odd_types, odd_values, odd_degrees, unlikely_facts)}
