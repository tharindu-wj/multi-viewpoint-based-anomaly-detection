"""Tool: survey the pool -- every mining rule's findings in the caller's
scope, merged and ranked, a page at a time.

THE ONLY WAY AN OBSERVER REACHES THE GRAPH'S CONTENTS AT SCALE. The mining
rules sweep the whole graph deterministically; the pool
(tools/mining_rules/pool.py) merges what they found in the caller's scope;
this tool shows it, resolved to labels, in pages sized for reading.

Surveying is free -- a pool line is a LEAD, not a served candidate. Nothing
here is judged. The observer reads the pool, then shortlist_candidates moves
the leads its norms speak to into its reading budget, and only those get
verdicts. Every entry has a stable pool id (p1, p2, ...) that means the same
thing on every call, because the pool is deterministic given the scope.

The pool is built once per observer and kept in state exactly as the observer
saw it -- the run file records what was on offer, not just what was chosen,
so a rules-only shortlist at the same budget can be scored beside the
observer's (the equal-K baseline).
"""
import json

from loaders.context import get_context
from tools._observers import OBSERVER_NAMES, state_key
from tools.mining_rules.pool import POOL_CAP, build_pool

#: pool lines per page -- compact lines, so a page is a survey, not a read
POOL_PAGE = 40

#: an observer's reading budget: how many leads it may shortlist for judging
READING_BUDGET = 30


def find_suspects(page: int = 1, tool_context=None) -> str:
    """Survey the pool of leads the mining rules found in your scope.

    Four deterministic rules have swept the whole graph; this shows what
    they found INSIDE YOUR SCOPE, merged and ranked -- strongest leads
    first, a cross-section of every rule on every page. Each line reads
    "p7. <head> --<relation>-- <tail>  [rule: why the rule flagged it]".
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

    Surveying costs nothing. Read every page (there are at most three),
    then call shortlist_candidates with the pool ids YOUR NORMS speak to.
    Nothing in the pool is a verdict; a rule finds, only you judge.

    Args:
        page: 1 for the first forty leads, 2 for the next forty, and so on.
    """
    ctx = get_context()
    agent = tool_context.agent_name
    if agent not in OBSERVER_NAMES:
        return f"ERROR: only an observer surveys the pool; '{agent}' is not one."

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
                "shortlist -- you are done, stop here.")

    page = max(1, int(page))
    pages = (len(entries) + POOL_PAGE - 1) // POOL_PAGE
    rows = entries[(page - 1) * POOL_PAGE: page * POOL_PAGE]
    if not rows:
        return (f"The pool has no page {page} -- it holds {len(entries)} "
                f"leads on {pages} page(s).")

    if page not in pool["pages_seen"]:
        pool["pages_seen"].append(page)
    tool_context.state[pool_key] = json.dumps(pool)

    lines = [f"Pool page {page} of {pages} ({len(entries)} leads in your "
             f"scope; you may shortlist up to {READING_BUDGET} in all)."]
    for offset, entry in enumerate(rows):
        pid = f"p{(page - 1) * POOL_PAGE + offset + 1}"
        notes = " | ".join(f"{rule}: {entry['notes'][rule]}"
                           for rule in entry["rules"])
        tag = "TWO RULES AGREE -- " if len(entry["rules"]) > 1 else ""
        lines.append(f"  {pid}. {entry['text']}  [{tag}{notes}]")

    remaining = [p for p in range(1, pages + 1) if p not in pool["pages_seen"]]
    if remaining:
        lines.append(f"\nPages not yet surveyed: "
                     f"{', '.join(str(p) for p in remaining)}. Survey them, "
                     f"then shortlist_candidates with the pool ids your norms "
                     f"speak to.")
    else:
        lines.append("\nYou have surveyed the whole pool. Now call "
                     "shortlist_candidates with the pool ids your norms "
                     "speak to -- leads only, judged afterwards.")
    return "\n".join(lines)
