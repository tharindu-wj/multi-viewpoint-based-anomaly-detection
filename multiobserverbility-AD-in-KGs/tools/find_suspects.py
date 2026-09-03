"""Tool: read the pool -- every mining rule's findings in the caller's
scope, merged and ranked, served a page at a time as candidates.

THE ONLY WAY AN OBSERVER REACHES THE GRAPH'S CONTENTS AT SCALE. The mining
rules sweep the whole graph deterministically; the pool
(tools/mining_rules/pool.py) merges what they found in the caller's scope;
this tool serves it, resolved to labels, in pages sized for judging.

Every lead served IS a candidate (c1, c2, ...) and every candidate must be
judged through submit_verdicts -- there is no free look. The survey-then-
shortlist design this replaces let the observer stop after the leads that
leapt out (measured: 4-21 chosen of a 30 budget, recall capped by the
observer's own reticence, DESIGN.md section 20). Page-by-page judging keeps
the viewpoint where it belongs -- in the VERDICTS, where norms can flag,
pass, or declare themselves silent -- while coverage comes from the budget,
not from nerve. Leads beyond the budget are "not examined", never an
implicit ok.

The pool is built once per observer and kept in state exactly as served --
the run file records what was on offer, not just what was judged, so a
rules-only cut at the same K can be scored beside the observer's (the
equal-K baseline).
"""
import json

from loaders.context import get_context
from tools._observers import OBSERVER_NAMES, state_key
from tools.mining_rules.pool import POOL_CAP, build_pool

#: pool lines per page -- one page is one judging round
POOL_PAGE = 40

#: an observer's reading budget: how many candidates it can be served in all
READING_BUDGET = 160


def find_suspects(page: int = 1, tool_context=None) -> str:
    """Fetch a page of the pool of leads the mining rules found in your scope.

    Four deterministic rules have swept the whole graph; this serves what
    they found INSIDE YOUR SCOPE, merged and ranked -- strongest leads
    first, a cross-section of every rule on every page. Each line reads
    "c7. <head> --<relation>-- <tail>  [rule: why the rule flagged it]".
    A lead two rules agree on is marked and listed first.

    What each rule looks for:
      odd_pairs    two things linked in a combination the graph almost never
                   records, a thing linked to itself, or a mostly-mutual
                   link recorded one way only
      odd_types    an entity of a kind this slot of this relation has never
                   held
      odd_values   one entity's values under one relation: extra values
                   where one is the norm, values that contain each other,
                   or two names for what may be one thing
      odd_degrees  an entity with far fewer or far more records than its
                   kind usually has

    Every lead served here is a candidate: give each one a verdict through
    submit_verdicts, then fetch the next page, until your reading budget is
    spent or the pool is exhausted. Nothing in the pool is a verdict; a
    rule finds, only you judge.

    Args:
        page: 1 for the first forty leads, 2 for the next forty, and so on.
    """
    ctx = get_context()
    agent = tool_context.agent_name
    if agent not in OBSERVER_NAMES:
        return f"ERROR: only an observer reads the pool; '{agent}' is not one."

    scope_raw = tool_context.state.get(state_key("scope", agent))
    if not scope_raw:
        return ("ERROR: select your scope first. The pool is drawn from the "
                "relations your norms apply to.")

    pool_key = state_key("pool", agent)
    stored = tool_context.state.get(pool_key)
    if stored:
        pool = json.loads(stored)
    else:
        scope_ids = {entry["id"] for entry in json.loads(scope_raw)["scope"]}
        pool = {"cap": POOL_CAP, "pages_seen": [],
                "entries": build_pool(scope_ids, ctx)}
    entries = pool["entries"]
    if not entries:
        tool_context.state[pool_key] = json.dumps(pool)
        return ("The rules found nothing in your scope. There is nothing to "
                "judge -- you are done, stop here.")

    page = max(1, int(page))
    pages = (len(entries) + POOL_PAGE - 1) // POOL_PAGE
    rows = entries[(page - 1) * POOL_PAGE: page * POOL_PAGE]
    if not rows:
        # Persist the pool even on a bad page number -- a first call with one
        # must not force the whole 4-rule sweep to run again (review finding).
        tool_context.state[pool_key] = json.dumps(pool)
        return (f"The pool has no page {page} -- it holds {len(entries)} "
                f"leads on {pages} page(s).")

    if page not in pool["pages_seen"]:
        pool["pages_seen"].append(page)
    tool_context.state[pool_key] = json.dumps(pool)

    # Serve the page: each lead becomes a candidate, up to the budget.
    # Re-fetching a page re-shows the same candidate ids, charging nothing.
    served_key = state_key("served", agent)
    served = json.loads(tool_context.state.get(served_key) or "{}")
    id_of_triple = {tuple(e["triple"]): cid for cid, e in served.items()}
    primary = sum(1 for cid in served if cid.startswith("c"))

    lines = [f"Pool page {page} of {pages} ({len(entries)} leads in your "
             f"scope; your reading budget is {READING_BUDGET} candidates "
             f"in all)."]
    unserved = 0
    for offset, entry in enumerate(rows):
        triple = tuple(entry["triple"])
        notes = " | ".join(f"{rule}: {entry['notes'][rule]}"
                           for rule in entry["rules"])
        tag = "TWO RULES AGREE -- " if len(entry["rules"]) > 1 else ""
        if triple in id_of_triple:
            cid = id_of_triple[triple]
        elif primary < READING_BUDGET:
            cid = f"c{primary + 1}"
            pid = f"p{(page - 1) * POOL_PAGE + offset + 1}"
            served[cid] = {"triple": list(triple), "text": entry["text"],
                           "note": notes, "rule": entry["rules"][0],
                           "rules": entry["rules"], "pool_id": pid}
            id_of_triple[triple] = cid
            primary += 1
        else:
            unserved += 1
            continue
        lines.append(f"  {cid}. {entry['text']}  [{tag}{notes}]")
    tool_context.state[served_key] = json.dumps(served)

    if unserved:
        lines.append(f"\nYour reading budget is spent; {unserved} lead(s) on "
                     f"this page (and any later pages) stay unexamined.")

    judged = json.loads(tool_context.state.get(
        state_key("verdicts", agent)) or "{}")
    unjudged = sum(1 for cid in served if cid not in judged)
    room = READING_BUDGET - primary
    close = [f"\nJudge every candidate above with submit_verdicts, by your "
             f"norms alone ({unjudged} of your candidates await a verdict). "
             f"A rule's note says why it looked odd; whether it is WRONG by "
             f"your norms is your call."]
    # What remains is judged by what was FETCHED, not by this page's number:
    # an out-of-order fetch must not end the hunt early (review finding).
    unfetched = [p for p in range(1, pages + 1)
                 if p not in pool["pages_seen"]]
    if room > 0 and unfetched:
        close.append(f"Then fetch page {unfetched[0]} -- your budget has "
                     f"room for {room} more candidate(s).")
    elif not unfetched:
        close.append("The whole pool has been served: judge every "
                     "candidate, then you are done.")
    else:
        close.append("Your reading budget is now fully served: judge every "
                     "candidate, then you are done.")
    return "\n".join(lines + close)
