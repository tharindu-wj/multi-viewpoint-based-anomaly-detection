"""Tool: run one mining rule over the graph, a page of findings at a time.

THE ONLY WAY AN OBSERVER REACHES THE GRAPH'S CONTENTS AT SCALE. The
mining rules sweep the whole graph deterministically; this tool serves what
they found -- restricted to the caller's scope, resolved to labels, in pages
sized for reading, capped at the observer's total reading budget.

Every served candidate gets a stable id (c1, c2, ...). submit_verdicts only
accepts ids that were really served to the caller -- an observer cannot pass
judgement on a fact it was never shown.

Adding a rule to the menu does NOT change any agent's tool list -- the
predecessor's lesson: the menu lives behind one tool, in
tools/mining_rules/.
"""
import json

from loaders.context import get_context
from tools._observers import OBSERVER_NAMES, state_key
from tools.mining_rules import RULES

PAGE_SIZE = 10

#: an observer's total reading budget, across all rules and pages
READING_BUDGET = 30


def find_suspects(rule: str, why: str = "", page: int = 1,
                    tool_context=None) -> str:
    """Get a page of suspicious facts from one mining rule. Judge every one.

    The rules, and the kind of suspicious each one finds:
      odd_pairs       the links between two things do not sit together --
                        a combination almost never seen in the graph, a
                        thing linked to itself, or a mostly-mutual link
                        recorded one way only. Leads on CONTRADICTIONS and
                        WRONG or ONE-SIDED links.
      odd_types       an entity of a kind its seat has never held -- no
                        other entity of its kind fills this slot of this
                        relation. Leads on records using a relation with
                        the WRONG KIND of thing.
      odd_values      one entity's set of values under one relation --
                        extra values where one is the rule, values the
                        graph itself records as containing each other, or
                        values that look like one thing recorded twice.
                        Leads on AMBIGUOUS or REDUNDANT records.
      odd_degrees     an entity with far fewer or far more records than
                        entities of its kind usually have. Leads on
                        UNUSUAL entities -- thin records and hubs, often
                        true, sometimes the shadow of an error.
      unlikely_facts  facts a link predictor trained on this graph finds
                        unlikely. Leads on FALSE facts at large.

    Pick rules that match YOUR norms -- each surfaces only its own kind
    of suspicious, and none of them judges anything. Candidates come back as
    "c1. <head> --<relation>-- <tail>  [note]"; every one, suspicious or not, is
    judged by YOU via submit_verdicts.

    Args:
        rule: which mining rule to run.
        why: first call to each rule only -- one sentence connecting it
            to your norms.
        page: 1 for the first ten candidates, 2 for the next ten, and so on.
    """
    ctx = get_context()
    agent = tool_context.agent_name
    if agent not in OBSERVER_NAMES:
        return f"ERROR: only an observer asks for candidates; '{agent}' is not one."

    scope_raw = tool_context.state.get(state_key("scope", agent))
    if not scope_raw:
        return ("ERROR: select your scope first. Candidates are drawn from "
                "the relations your norms apply to.")
    scope_ids = {entry["id"] for entry in json.loads(scope_raw)["scope"]}

    if rule not in RULES:
        return (f"ERROR: no mining rule named '{rule}'. "
                f"The menu: {', '.join(sorted(RULES))}.")

    # First use of each rule must be tied to a norm -- recorded, so the
    # run file shows WHY this agent hunted the way it did.
    used_key = state_key("rules", agent)
    used = json.loads(tool_context.state.get(used_key) or "{}")
    if rule not in used:
        if not why or not why.strip():
            return (f"ERROR: first call to {rule} -- say in one sentence "
                    f"which of your norms this rule serves (why=...).")
        used[rule] = why.strip()
        tool_context.state[used_key] = json.dumps(used)

    try:
        found = RULES[rule].find(scope_ids, ctx)
    except RuntimeError as refusal:
        return f"ERROR: {refusal}"

    served_key = state_key("served", agent)
    served = json.loads(tool_context.state.get(served_key) or "{}")
    id_of_triple = {tuple(entry["triple"]): cid for cid, entry in served.items()}

    page = max(1, int(page))
    page_rows = found[(page - 1) * PAGE_SIZE: page * PAGE_SIZE]
    if not page_rows:
        return (f"{rule} has nothing on page {page} -- it found "
                f"{len(found)} candidates in your scope in total.")

    lines = [f"{rule}: page {page} of "
             f"{(len(found) + PAGE_SIZE - 1) // PAGE_SIZE} "
             f"({len(found)} candidates in your scope)."]
    budget_hit = False
    for triple, note in page_rows:
        if triple in id_of_triple:
            # Another rule already served it: same id, no extra budget.
            lines.append(f"  {id_of_triple[triple]}. {ctx.triple_text(triple)}"
                         f"  [{note}] (already served)")
            continue
        if len(served) >= READING_BUDGET:
            budget_hit = True
            break
        candidate_id = f"c{len(served) + 1}"
        served[candidate_id] = {"triple": list(triple),
                                "text": ctx.triple_text(triple),
                                "note": note, "rule": rule}
        id_of_triple[triple] = candidate_id
        lines.append(f"  {candidate_id}. {ctx.triple_text(triple)}  [{note}]")

    tool_context.state[served_key] = json.dumps(served)

    if budget_hit:
        lines.append(f"\nREADING BUDGET REACHED ({READING_BUDGET}). No more "
                     f"candidates will be served -- judge what you have.")
    lines.append("\nJudge these with submit_verdicts. Nothing here says "
                 "whether a candidate is actually wrong -- that is your job.")
    return "\n".join(lines)
