"""The mining rules -- deterministic sweeps of the graph, one kind of
suspicious each. NOT TOOLS: an agent reaches these only through
find_suspects, which serves the POOL of everything they found in the
observer's scope, merged and ranked (tools/mining_rules/pool.py).

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
arXiv:2412.04780, section 5) onto four counting rules -- each module's
docstring names the types it mines:

    odd_pairs       contradicting facts, incorrect predicate,
                    entity ambiguity, one-way records of two-way relations
    odd_types       invalid predicate (inconsistency)
    odd_values      predicate ambiguity, redundant facts, duplicate facts
    odd_degrees     rare entity, prolific entity (unusual)

RETIRED (2 Sep 2026): unlikely_facts, the model-based plausibility channel.
Measured over eight live runs it was the most-read rule (160 of ~330
candidate reads) and surfaced zero planted facts -- the scorer had trained
on the contaminated graph and memorised the fakes as plausible. The module
stays on disk, dormant, for the day a held-out or external scorer earns its
place back; it is simply not in the roster below.

Missingness types stay where TAXO itself puts them: at the storage layer,
i.e. the ingest guards of scripts/1_prepare_graph.py, because a malformed
row is a certainty, not a lead for a judge.
"""
from tools.mining_rules import odd_degrees, odd_pairs, odd_types, odd_values

#: the roster the pool is built from. Each rule knows ONE kind of suspicious;
#: the ORDER here is the round-robin order of the pool.
RULES = {module.NAME: module for module in (
    odd_pairs, odd_types, odd_values, odd_degrees)}
