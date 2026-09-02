"""Tool: the observer's selection -- pool leads become served candidates.

THE STEP WHERE THE VIEWPOINT ACTS. The pool is the same for any observer
with the same scope; what differs between observers is which leads their
norms speak to. Shortlisting moves chosen leads (p-ids) into the caller's
served store under candidate ids (c1, c2, ...), up to the reading budget --
and only served candidates can receive verdicts.

Recorded with a why, so the run file shows WHAT was on offer (the pool), WHAT
was chosen (the shortlist) and by WHICH norm. Leads left in the pool are
"not examined" -- never an implicit ok -- which keeps the disagreement set
honest: it holds only facts two observers actually judged.
"""
import json

from tools._observers import OBSERVER_NAMES, state_key
from tools.find_suspects import READING_BUDGET


def shortlist_candidates(ids: list[str], why: str, tool_context=None) -> str:
    """Choose the pool leads your norms speak to. They become your candidates.

    Give pool ids from find_suspects ("p7", "p12", ...) and one or two
    sentences on which of your norms drove the choice. The chosen leads are
    served to you as candidates (c1, c2, ...) for submit_verdicts; leads you
    do not choose are simply not examined.

    You may shortlist up to your reading budget in all, over one call or
    several. The pool is larger than your budget, so choose: take the leads
    that matter BY YOUR NORMS -- including ones another judge would let
    pass -- and skip leads your norms are silent on, however odd a rule
    found them.

    Args:
        ids: pool ids to shortlist, e.g. ["p3", "p7", "p41"].
        why: which norm(s) these leads answer to, in a sentence or two.
    """
    agent = tool_context.agent_name
    if agent not in OBSERVER_NAMES:
        return f"ERROR: only an observer shortlists; '{agent}' is not one."

    stored = tool_context.state.get(state_key("pool", agent))
    if not stored:
        return ("ERROR: survey the pool first -- call find_suspects; the "
                "pool ids come from there.")
    entries = json.loads(stored)["entries"]

    if not ids:
        return "ERROR: an empty shortlist chooses nothing."
    if not why or not why.strip():
        return ("ERROR: 'why' is empty. Say which of your norms these leads "
                "answer to.")

    served_key = state_key("served", agent)
    served = json.loads(tool_context.state.get(served_key) or "{}")
    id_of_triple = {tuple(e["triple"]): cid for cid, e in served.items()}
    primary = sum(1 for cid in served if cid.startswith("c"))

    chosen = []
    for raw in ids:
        pid = (raw or "").strip().lower()
        if not (pid.startswith("p") and pid[1:].isdigit()
                and 1 <= int(pid[1:]) <= len(entries)):
            return (f"ERROR: '{raw}' is not a pool id. The pool holds p1 to "
                    f"p{len(entries)}. Nothing from this call was recorded.")
        if pid not in chosen:
            chosen.append(pid)

    room = READING_BUDGET - primary
    if room <= 0:
        return (f"ERROR: your reading budget of {READING_BUDGET} is already "
                f"shortlisted. Judge what you have with submit_verdicts.")

    lines, added, skipped = [], 0, []
    for pid in chosen:
        entry = entries[int(pid[1:]) - 1]
        triple = tuple(entry["triple"])
        if triple in id_of_triple:
            lines.append(f"  {id_of_triple[triple]}. {entry['text']}  "
                         f"(already on your shortlist)")
            continue
        if added >= room:
            skipped.append(pid)
            continue
        cid = f"c{primary + added + 1}"
        note = " | ".join(f"{rule}: {entry['notes'][rule]}"
                          for rule in entry["rules"])
        served[cid] = {"triple": list(triple), "text": entry["text"],
                       "note": note, "rule": entry["rules"][0],
                       "rules": entry["rules"], "pool_id": pid}
        id_of_triple[triple] = cid
        added += 1
        lines.append(f"  {cid}. {entry['text']}  [{note}]")
    tool_context.state[served_key] = json.dumps(served)

    log_key = state_key("shortlist", agent)
    log = json.loads(tool_context.state.get(log_key) or "[]")
    log.append({"ids": chosen, "added": added, "why": why.strip()})
    tool_context.state[log_key] = json.dumps(log)

    head = [f"Shortlisted {added} lead(s) as candidates "
            f"({primary + added} of {READING_BUDGET} used)."]
    if skipped:
        head.append(f"Budget reached; not shortlisted: {', '.join(skipped)}.")
    tail = ["\nJudge every candidate above with submit_verdicts, by your "
            "norms alone. A rule's note says why it looked odd; whether it "
            "is WRONG by your norms is your call."]
    return "\n".join(head + lines + tail)
