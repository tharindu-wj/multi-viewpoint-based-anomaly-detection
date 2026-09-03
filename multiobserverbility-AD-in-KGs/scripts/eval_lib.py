"""One ranked list per run: every verdict and every pool lead, by confidence.

The union metric lets the OBSERVERS choose K, so K moves run to run and no
two runs are scored at the same depth. This module rebuilds a run's UNCAPPED
pools from its recorded scopes (the observers only ever saw the capped
front) and folds the frozen verdicts on top, producing one deterministic
ranking that a fixed-K ladder can be read off.

Tiers, strongest signal across both observers first -- a verdict is a
categorical act, not a score, so agreement is the only thing that outranks
a single flag:

    1  judged anomaly by BOTH observers
    2  judged anomaly by exactly one
    3  judged unsure by at least one (and anomaly by none)
    4  unexamined pool lead, or judged only out_of_scope -- "my norms are
       silent" carries no information about truth, so it ranks with the
       unexamined, in pool order
    5  judged ok -- an informative negative: examined and explicitly
       passed, so it ranks BELOW leads nobody looked at

Within a tier: the best (minimum) position the triple holds in either
observer's uncapped pool. A judged triple in NEITHER rebuilt pool is
expected, not an error -- a reviewer judges leads from the OTHER observer's
pool, so with disjoint scopes its own pools may never rank the triple; it
still belongs to its tier, after every in-pool lead. The triple itself
breaks the final tie, so the ranking is reproducible byte for byte.

NEVER reads ground_truth.tsv. The callers own the answer key and count the
planted hits; this module only decides the ORDER -- ladder() takes the
callers' truth dict as an argument for exactly that reason.
"""
from tools.mining_rules.pool import build_pool, interleave

#: fixed in advance, so no run can move its own goalposts. 500 is the
#: conventional rung: 500 planted makes P@500 = R@500 by construction.
LADDER = (50, 100, 150, 200, 500)

#: rank for a judged triple that no rebuilt pool contains -- large enough
#: that it sorts after every real pool position, inside its tier
NO_POOL_RANK = 10 ** 9

#: the one-line story of the ordering, for the reports that print it
TIER_ORDER = ("flagged-by-both > flagged-by-one > unsure > "
              "unexamined-pool-order (out_of_scope ranks here) > "
              "judged-ok > nothing")


def build_ranking(run, ctx):
    """(ranked, meta) for one frozen run; None when it cannot be rebuilt.

    None means the run predates recorded scopes/pools -- without the scopes
    there is nothing to rebuild, and without recorded pools there is no
    evidence the observers surveyed one, so the ladder is not comparable.
    """
    scopes = run.get("scopes") or []
    recorded = run.get("pools") or []
    if (not scopes or not all(scopes)
            or not any((p or {}).get("entries") for p in recorded)):
        return None

    # the observers saw pools cut at POOL_CAP; the ranking wants the WHOLE
    # ordering, so it is rebuilt uncapped from the same recorded scopes --
    # deterministic, so this is a reconstruction, not a re-roll
    uncapped = [build_pool({e["id"] for e in s["scope"]}, ctx, cap=None)
                for s in scopes]
    position = [{tuple(e["triple"]): i for i, e in enumerate(pool)}
                for pool in uncapped]

    # verdict signals, merged over both observers and both phases (c-ids,
    # an observer's own hunt; r-ids, its second-opinion reviews)
    said = {}            # triple -> every verdict word it received
    flagged_by = {}      # triple -> how many OBSERVERS called it anomaly
    for observer_verdicts in run.get("verdicts") or []:
        anomalies = set()
        for v in (observer_verdicts or {}).values():
            triple = tuple(v["triple"])
            said.setdefault(triple, set()).add(v["verdict"])
            if v["verdict"] == "anomaly":
                anomalies.add(triple)
        for triple in anomalies:
            flagged_by[triple] = flagged_by.get(triple, 0) + 1

    universe = set(said)
    for pos in position:
        universe.update(pos)

    def tier_of(triple):
        if flagged_by.get(triple, 0) >= 2:
            return 1
        if flagged_by.get(triple, 0) == 1:
            return 2
        verdicts = said.get(triple, ())
        if "unsure" in verdicts:
            return 3
        if "ok" in verdicts:
            return 5
        return 4     # unexamined pool lead, or out_of_scope: silence

    def best_rank(triple):
        return min((pos[triple] for pos in position if triple in pos),
                   default=NO_POOL_RANK)

    tiers = {triple: tier_of(triple) for triple in universe}
    ranked = sorted(universe,
                    key=lambda triple: (tiers[triple], best_rank(triple),
                                        triple))
    meta = {"tiers": tiers,
            "judged": set(said),
            "uncapped_pools": uncapped}
    return ranked, meta


def ladder(ranked, meta, truth, ks=LADDER):
    """One row per rung: hits, judged share, and the rules-only hits.

    truth is the CALLER'S answer key (triple -> 1 if planted) -- passed in
    so this module never opens the file the agents were blinded to. hits
    are counted over ranked[:k] but the caller divides by k, so a ranking
    shorter than k pays for its missing slots as misses by construction.
    The rules-only column is the same uncapped pools zipped strongest-first
    with no verdict on top -- what each rung would hold if nobody judged.
    """
    rows = []
    for k in ks:
        top = ranked[:k]
        rows.append({
            "k": k,
            "hits": sum(1 for t in top if truth.get(t) == 1),
            "judged": sum(1 for t in top if t in meta["judged"]),
            "rules_hits": sum(1 for t in interleave(meta["uncapped_pools"], k)
                              if truth.get(t) == 1),
        })
    return rows
