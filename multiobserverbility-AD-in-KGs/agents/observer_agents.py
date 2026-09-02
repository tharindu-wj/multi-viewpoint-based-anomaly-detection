"""The two observers: blind norms first, then the data, then a scope.

A factory rather than two hand-written agents so the twins cannot drift
apart -- the ONLY difference between them is which persona they carry and
which state keys they write. Any other asymmetry would confound the
experiment.

The two-phase separation is enforced twice over: the phase gate refuses every
data tool until the observer's norms exist, and the run script later verifies
from the trace that declare_semantics really did precede the first look.
"""
from google.adk.agents.llm_agent import Agent

from agents import telemetry
from agents.config import MODEL, OBSERVER_TOOLS, OBSERVER_TOOL_BUDGET
from agents.pacing import pace_model_calls
from agents.phase_gate import keep_norms_blind
from loaders.active import DATASET
from tools._observers import OBSERVER_NAMES, state_key
from tools.find_suspects import READING_BUDGET

OBSERVER_INSTRUCTION = f"""\
You are an observer. You will eventually judge facts for anomalies; today you
establish your observability point -- the position you will judge from.

All you know about the dataset is this:
  "{DATASET.CARD}"

WHO YOU ARE:
PERSONA_SLOT

Work in two strict phases.

PHASE 1 -- DECLARE YOUR NORMS, before looking at anything.
From your persona and what you know about the world, call declare_semantics:
what a normal fact of this domain looks like to you, what YOU flag as
anomalous (which, depending on who you are, may include things that are
factually true), and what you deliberately let pass that another judge might
flag. Speak in world terms -- you have not seen the dataset, and every data
tool will refuse you until your norms are recorded.

PHASE 2 -- MAP YOUR NORMS ONTO THE DATASET.
Once your norms are recorded the data opens. Look at what this graph actually
records -- describe_dataset first, then whatever you need -- and call
select_scope with the relations your norms apply to, saying which norm makes
each of them yours. Your norms are fixed; only the mapping is yours to
choose now.

PHASE 3 -- SURVEY, SHORTLIST, JUDGE.
You cannot read the whole graph, so mining rules sweep it for you and pool
what they found in your scope -- every lead named, with the rule's reason
in plain words. Survey the WHOLE pool with find_suspects (every page; at
most three). Then call shortlist_candidates with the pool ids YOUR NORMS
speak to, up to your reading budget of {READING_BUDGET}, saying which norm
drove the choice: the pool is larger than your budget, so choose the leads
that matter by your norms -- including ones another judge would let pass --
and leave aside leads your norms are silent on, however odd a rule found
them. Then judge every shortlisted candidate through submit_verdicts, by
YOUR norms alone: anomaly, ok, out_of_scope, or unsure, each with one
sentence of why. A lead a rule found odd can still be ok by your norms, and
a fact that is literally true can still be an anomaly by them -- the rules
find, you select and judge.

You are done when every shortlisted candidate is judged. Use at most
{OBSERVER_TOOL_BUDGET} tool calls in all.
"""


def make_observer(name: str) -> Agent:
    """One observer, bound to its own persona, norms and scope keys."""
    persona_key = state_key("persona", name)
    return Agent(
        model=MODEL,
        name=name,
        description=("Declares its own norms blind, then maps them onto the "
                     "dataset's vocabulary as a scope."),
        # {persona_N} is filled from session state -- the root wrote it there.
        instruction=OBSERVER_INSTRUCTION.replace(
            "PERSONA_SLOT", "{" + persona_key + "}"),
        tools=OBSERVER_TOOLS,
        # The gate reads the CALLER's name, so one callback serves both twins
        # and neither can satisfy the other's precondition.
        before_tool_callback=keep_norms_blind,
        include_contents="none",
        before_model_callback=pace_model_calls,
        after_model_callback=telemetry.record_response,
        on_model_error_callback=telemetry.record_error,
    )


observers = [make_observer(name) for name in OBSERVER_NAMES]
