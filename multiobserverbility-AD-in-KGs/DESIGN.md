# Software design — the observability-point pipeline on CoDEx

A living document: **DECIDED** is settled, **PROPOSED** is my current suggestion
awaiting agreement, **OPEN** needs a decision before code.

Target architecture: <https://claude.ai/code/artifact/3a99a9c7-9adf-4372-92c1-12ca1079ea49>
(the technical redraw of the 26/02 whiteboard sketch — numbering ①–⑦ below
matches it). Worked-run transcript — the same pipeline as the LLMs actually
saw it, every prompt and output verbatim from run_20260826_082940:
<https://claude.ai/code/artifact/69a217f6-6016-4f11-a861-ced5563edb0c>. Predecessor project: `../multiviewpoint-AD-in-KGs/`, whose
mechanics we port, not its tools.

---

## 1. The data, as measured (26 Aug 2026)

`data/` is the CoDEx repository layout, CoDEx-S slice:

| file | contents | measured |
|---|---|---|
| `triples/codex-s/{train,valid,test}.txt` | the graph, tab-separated ids | 36,543 triples, 2,034 entities, 42 relations |
| `triples/codex-s/{valid,test}_negatives.txt` | **hand-verified FALSE triples** | 3,655 |
| `entities/en/entities.json` | id → label, description, wiki url | 77,951 total; **2,034/2,034** of ours labelled, 2,019 described |
| `relations/en/relations.json` | id → label, description | 71 total; **42/42** of ours labelled + described |
| `types/entity2types.json` | entity id → type ids | **2,034/2,034** of ours typed |
| `types/en/types.json` | type id → label, description | 3,443 types |

A fully resolved triple: `Q7604 P1412 Q188` → *Leonhard Euler —languages
spoken, written, or signed— German* (head type: human).

**Label collisions inside the codex-s vocabulary: zero** — entity labels and
relation labels are both unique. Verified 26 Aug.

---

## 2. Layer ①/③ — dataset context (the definitions store)

**DECIDED — labels only, ids in artifacts.** No agent ever sees a bare
`Q…`/`P…` id. Every tool resolves ids to labels on output and accepts labels on
input (unique, so unambiguous — re-verify this invariant if the slice ever
changes). Run files and state store *both* id and label: ids for exactness,
labels for the human reading the run.

**DECIDED — one loader, loaded once.** `loaders/context.py` reads the four
JSON files a single time per process, immediately subsets 77,951 entities to
the 2,034 in the graph, and builds the id↔label indexes. ~11 MB parse, once.

**DECIDED — tools read prepared artifacts only, never `data/` raw.** The
negatives files ARE the answer key now. The firewall therefore moves up a
level: step-1 output (`contaminated_kg.tsv`, `ground_truth.tsv`) is the only
triple source any tool may touch, and the firewall grep gains a pattern:
nothing in `tools/` or `agents/` may name `_negatives`. Definitions
(`entities/relations/types` JSONs) are safe for tools — they contain no triples.

---

## 3. The tool surface (PROPOSED — under discussion)

Two families, same split as the gate rule that already works: **context tools
return facts and are never gated; pipeline tools move the audit forward and
are ordered.**

### Context tools — ungated, read-only, both agents + root

| tool | returns | replaces |
|---|---|---|
| `describe_dataset()` | totals + all 42 relations: label, triple count, distinct heads/tails | `list_relations` |
| `describe_relation(name)` | Wikidata description + stats (cardinality, symmetry, top tails **as labels**) + 3 example triples | old profiler + definitions, merged |
| `lookup(term)` | entity: label, description, types (as labels), degree. relation: label, description, usage count | **new** — the definitions store made queryable |
| `sample(relation?, n)` | up to 10 resolved triples | same, now labelled |

### Pipeline tools — ordered, caller-keyed, writes are tool calls

| # | tool | who | contract |
|---|---|---|---|
| ② | `assign_observability_point(agent, scope, goal, norms)` | **root only** | validates scope relations exist and agent name is real; writes `op_a`/`op_b` state. Root must place BOTH before the parallel phase starts. |
| ④ | `select_scope(relations)` | sub agent | must be a subset of its OP's scope; registers the subgraph, returns its size. Prerequisite for candidates — this is the gate, relocated. |
| ⑤ | `get_candidates(page)` | sub agent | serves the top-N of the agent's scope subgraph, ~10 per page, resolved to labels, with scores. Refuses until `select_scope`. |
| ⑥ | `submit_verdicts(verdicts)` | sub agent | batch of `{triple, verdict ∈ anomaly/ok/out_of_scope, why}`; rejects triples it never served; accumulates findings. |

Rationale carried from the predecessor, measured there:
- **every artifact the run needs is written by a tool call** (tool-call writes
  landed 12/12; final-message scraping lost 5/12 in the same conditions);
- tools must have **function** docstrings — module docstrings transmit 0 chars
  to the model (four tools silently shipped empty for weeks);
- validation errors return as text so the agent self-corrects in-loop.

### PROPOSED — scores are precomputed, not computed in the loop

`2_train` scores the **entire contaminated graph** once and writes
`scores.npy` beside the model. `get_candidates` = load array → mask to scope →
top-N → page. No model, no torch, no 40-second load inside an agent turn, and
scoring is byte-identical across runs. The stale-model guard extends to the
score file (hash of the graph it scored).

This also enforces the diagram's redline mechanically: scores computed against
the FULL graph — the scope only *selects* — because the file is written before
any scope exists.

---

## 4. Contamination (①-adjacent, feeds everything)

**PROPOSED.** `1_prepare` builds
`contaminated_kg = train ∪ valid ∪ test ∪ sample(negatives, ratio)` and writes
`ground_truth.tsv` with `kind = verified_false`. No `corrupt()` — CoDEx's
negatives are type-consistent, human-checked false facts (*Mariah Carey
—spouse— Sean Penn*), which retires the "anomalies match the KGE negative
sampler" risk outright.

**OPEN** — additionally inject a slice of synthetic corruptions as a second
`kind`, for continuity with the Countries numbers? My lean: not in v1; one
honest anomaly family first.

---

## 5. Ported unchanged from `multiviewpoint-AD-in-KGs`

- `agents/telemetry.py` + `health` block + `truncated` status (the quota
  lesson: a refused request must never read as agent behaviour)
- `HttpRetryOptions` on the model (10/20/40/70s waits)
- `.env` key naming (`GOOGLE_API_KEY`), win32 thread guards
- `loaders/active.py` dataset-switch pattern
- scripts naming: numbered = pipeline, `check_*` = test rigs
- ParallelAgent branch isolation + state-key discipline + the
  `include_contents="none"` rule

---

## 6. Open questions (the current brainstorm)

1. **Who sets N (the reading budget)?** The diagram says N = reading capacity,
   absolute. Options: fixed config (simplest, comparable across runs) / root
   sets it per OP (one more thing to validate) / agent chooses under a cap.
   My lean: **config default, agent may lower, never raise.**
2. **Is the OP's scope binding?** `select_scope ⊆ OP.scope` (my lean — the OP
   is an assignment, and drift would blur whose findings are whose) vs
   advisory.
3. **Verdict vocabulary.** `anomaly / ok / out_of_scope` — is `unsure` a
   fourth verdict or is that what `ok` + a low-confidence `why` means? My
   lean: add `unsure`; forcing a binary call manufactures false confidence.
4. **Quota arithmetic.** ~4 context calls + 1 scope + N/10 pages + N/10
   verdict batches per agent. N=60 → ~35 model calls/run vs 15/min free tier.
   Retry absorbs it, but a run becomes ~3 minutes. Acceptable, or argue for
   N=30 in v1?
5. **Where does the root's context come from?** `describe_dataset` +
   `describe_relation` + `lookup` may be enough (labels are meaningful). The
   type vocabulary (3,443 types) is loaded but unexposed — add a
   `common_types()` tool later if root goals come out too vague.

---

## 7. Not yet designed (deliberately)

Evaluation (⑦'s scoring side): verified-false triples give objective
precision/recall per agent and for the union; norm disagreements on true facts
have no key and are reported, not scored. The evaluator redesign gets its own
section once the tool surface is agreed.

---

## 8. Milestone 1 (DECIDED 26 Aug) — root + context tools only

Scope: everything upstream of the sub agents. Produce OPs; consume nothing.

| piece | what | ~lines | needs API? |
|---|---|---|---|
| `scripts/1_prepare_graph.py` | merge train+valid+test → `kg.tsv` (no negatives yet) | 30 | no |
| `loaders/context.py` | 4 JSONs → graph-vocab subset, id↔label maps | 100 | no |
| `tools/` context ×4 | `describe_dataset` · `describe_relation` · `lookup` · `sample` | 180 | no |
| `tools/assign_observability_point.py` | root's only write; validates scope + agent name | 60 | no |
| `agents/` | root only + ported telemetry/retry/config | 150 | run only |
| `scripts/check_context.py`, `scripts/2_run_root.py` | eyeball rig · the run | 120 | 2nd only |

Excluded on purpose: training, scorer, subgraph/candidates/verdicts, sub
agents, contamination, evaluator.

Exit question this milestone answers: **asked for two OPs with differing norms
over a shared scope, does the root produce coherent ones?** (Self-written
frames converged 44/44; root assignment is the fix under test.)
Run cost ~5–7 model calls.

### Milestone 1 — built and measured (26 Aug 2026)

All 17 files built; every offline check passes (parse, ADK discovery, all 5
tool descriptions transmit, firewall grep clean, OP-tool validation incl. the
punctuation-proof norms guard). Two live runs, both `completed`, 4–6 model
calls, 8–10s — nowhere near quota.

**Exit question — does the root produce two coherent, differing norms?**

| | run 002523 | run 002553 |
|---|---|---|
| OPs placed | 2/2, via tool calls | 2/2 |
| scopes | disjoint partition (biographic vs geographic) | **overlapping** (3 shared relations) |
| norms differ | yes — symmetry-stance vs geo-consistency | yes — logical-consistency vs reciprocity/topology |
| "anomalous even if true" stance | partially (unreciprocated spouse = anomaly) | no |

Verdict: **the machinery works and the norms guard holds, but the full
same-scope/different-norms pair has not yet appeared** — the root leans toward
partitioning by relation, and neither run produced a clean norm of the
"flag it even if correctly recorded" kind. n=2. Options if this persists:
strengthen the instruction (ask for shared scope explicitly rather than
calling it "most valuable"), or have the tool enforce scope overlap. Decide
after more runs, not from two.

Also observed: run 1's norm for sub_agent_1 mentions "places of birth", which
is not in that agent's scope — the tool validates scope names, not norm prose.
Acceptable; the sub agent's out_of_scope verdict handles stray prose later.

---

## 9. Blind norms — the two-phase observability point (brainstormed 26 Aug)

**The principle.** Like people: a person's sense of what a normal relationship
looks like is formed by their background BEFORE they meet the community they
judge. The data teaches them the local vocabulary and where their values
apply; it does not supply the values. So:

    PHASE 1  who I am      norms from world knowledge alone
                           sees: DATASET_CARD (domain, 2-3 sentences)
                           never: relations, counts, samples
            -- the gate, inverted --
    PHASE 2  where I look  inspect the dataset, map norms onto its
                           vocabulary -> scope (relevant relations)

**Why structural, not prompted — our own evidence.** Both Milestone-1 runs
produced norms soaked in dataset vocabulary ("diplomatic relations",
"spouses", even "degree distributions" — data statistics, explicitly ruled
out). A root that browses first reverse-engineers "what would be anomalous
given this schema". Same failure family as frames-after-scores; same fix:
ordering enforced in code.

**Generalised gate rule (replaces the v1 rule).** A tool is blocked while it
could contaminate a commitment not yet made. Phase 1: context tools blocked.
Phase 2: context open, scoring (later) still gated behind scope.

**PROPOSED — personas solve the convergence problem.** Blind self-derived
norms would reconverge (44/44 precedent). The root — seeing ONLY the card,
needing no tools at all — assigns each sub agent a differing PERSONA (a
stance, e.g. legal formalist vs descriptive empiricist); each sub agent then
articulates its OWN norms from its persona. The root is the circumstance that
makes people different, not the author of their views.

**"Clearly show the separation" = three proofs.**
1. Code: per-agent phase gate on the context tools.
2. Trace: run script mechanically verifies first-context-call > norms-commit,
   per run, and marks violations invalid (like the firewall grep).
3. Artifact: blind norms contain no dataset vocabulary by construction, so
   they are PORTABLE across datasets — re-run phase 2 on another graph with
   the same norms. Norms that transfer are proof they never came from one.

**Build delta.** DATASET_CARD in the loader (domain + subject kinds, never
attribute kinds); root loses all tools, `assign_perspective` x2 with the
differing guard; sub agents get `declare_semantics` (blind, first) then
context tools then `select_scope`; OP splits into persona/norms/scope, each
stamped with call order.

**OPEN.**
1. Card grain — proposed line: name the domain and subjects, never attributes.
2. Personas: root-generated per run (agentic, variable) vs a fixed pair in
   config (reproducible, less agentic)? Lean: root-generated, seed-harness
   later measures variance.
3. Does phase 2 allow `sample()`? Seeing instances teaches vocabulary but also
   leaks "what is common" — norms are already fixed by then, so yes, allow.

**DECIDED (26 Aug) — card delivery.** The card is a `CARD` constant in the
dataset loader, injected into agent instructions like `{DATASET.NAME}` --
never the typed user prompt (unowned, leakable, unprovable) and never a tool
(costs calls, skippable). The run script pins the trigger message to a fixed
"Prepare the audit." so the card is the only domain channel, and records the
card verbatim in the run JSON as provenance. Residual hole, accepted: in
`adk web` a human can type schema into the chat; the scripted pipeline is the
measured path. Card text: "An encyclopedic knowledge graph about notable real
people, organisations and places." -- "encyclopedic" and "notable" kept
deliberately (they anchor the right world-knowledge prior); subjects only,
never attributes.

---

## 10. The pipeline on real data — worked example (all triples real)

**STEP 0 — the card** (the only thing phase 1 may see):
"An encyclopedic knowledge graph about notable real people, organisations and
places."

**PHASE 1a — root assigns personas** (sees the card, has no tools):

    sub_agent_1  FORMALIST   "a relationship is defined by its rules --
                              mutuality, exclusivity, consistency of record.
                              A rule violation is an anomaly even when every
                              fact in it is accurate."
    sub_agent_2  EMPIRICIST  "only a factually false claim can be wrong.
                              Unusual or incomplete arrangements that really
                              happened are not your concern."

**PHASE 1b — blind norms.** A peek is refused by the gate:

    -> describe_dataset()
    <- ERROR: you have not formed your view yet. Declare what YOU consider
       a normal relationship before looking at any data.

    formalist:  "a marriage is mutual by definition -- a record of an
                 inherently two-way bond held by one party only is anomalous
                 EVEN IF the underlying fact is real"
    empiricist: "a claim is anomalous only when false in the world;
                 incomplete but real relationships pass"

Note the vocabulary: "marriage", "two-way bond" -- world words. Neither agent
knows the dataset calls anything `spouse`.

**PHASE 2 — the gate lifts; norms map onto the actual vocabulary.**
`describe_dataset()` reveals the 42 relations; each agent selects the scope
its norms apply to:

    formalist:  spouse, unmarried partner, sibling, diplomatic relation
    empiricist: spouse, unmarried partner, sibling, child

Same slice, different reasons -- shared-scope/different-norms by construction.

**PHASES 5-6 — judged candidates** (later milestones; the triples are real):

| candidate | truth | formalist | empiricist |
|---|---|---|---|
| Mariah Carey --spouse-- Sean Penn | verified false | anomaly | anomaly |
| Russell Brand --spouse-- Katy Perry | TRUE, but the graph's one unreciprocated spouse edge | **anomaly** (mutuality violated) | **ok** (really married) |
| Katharine McPhee --spouse-- David Foster | true, both ways | ok | ok |

**7 — composed final list:**

    A AND B agree   Mariah Carey --spouse-- Sean Penn     <- scores both agents
    A only          Russell Brand --spouse-- Katy Perry   <- THE DISAGREEMENT SET
    B only          (empty here)

The disagreement row is the architecture's product: a true fact, anomalous
from one observability point, unremarkable from another.

**Portability, one line:** hand the formalist's norms to the Countries graph
and phase 2 maps them to `neighbor` (borders are mutual). Same norms, new
dataset, new scope -- the viewpoint never came from either dataset.

---

## 11. Milestone 2 — implementation plan (blind setup, ①–④)

Rebuild of the setup stage on the §9 design. Ends at scopes selected; scorer,
candidates and verdicts stay out of scope.

| # | piece | change | ~lines |
|---|---|---|---|
| 1 | `loaders/codexs.py` | add `CARD` (the §9-grain text, exactly as in §10) | +6 |
| 2 | `tools/assign_perspective.py` | NEW, replaces `assign_observability_point` (deleted): root's only tool; validates agent name, non-empty persona, differing-personas `_essence` guard; writes `persona_1/2` | 80 |
| 3 | `tools/declare_semantics.py` | NEW, sub agent, phase 1b: `(normal, anomalous, lets_pass)`; caller-keyed → `norms_1/2`; NOT validated against the dataset (it is blind); immutable once set; cross-agent identical-norms guard | 90 |
| 4 | `tools/select_scope.py` | NEW, sub agent, phase 2: `(relations, why)`; requires own norms first; validates labels via context; writes `scope_1/2` with ids+labels | 70 |
| 5 | `agents/phase_gate.py` | NEW: `before_tool_callback` — no norms yet → only `declare_semantics` allowed, context tools refused with the teaching error; norms set → context + `select_scope` open, re-declaration refused | 60 |
| 6 | `agents/root_agent.py` | REWRITE: no context tools — `[assign_perspective]` only; instruction = card + "two genuinely differing personas" | 60 |
| 7 | `agents/sub_agents.py` | NEW factory (twin discipline as before): instruction = card + persona via `{persona_N}` state templating + the two-phase contract; tools = `[declare_semantics, select_scope]` + context tools; gate + telemetry callbacks | 110 |
| 8 | `agents/config.py` | update keys (`PERSONA/NORMS/SCOPE_KEYS`), tool lists, budgets | ~30 Δ |
| 9 | `agents/agent.py` | tree becomes `SequentialAgent(root, ParallelAgent(sub_1, sub_2))` | ~15 Δ |
| 10 | `scripts/2_run_setup.py` | replaces `2_run_root.py`: runs the tree; prints personas/norms/scopes; records the card verbatim; **ordering proof** — per agent, verify from the trace that `declare_semantics` precedes the first context call, print BLINDNESS VERIFIED or mark the run invalid | 140 |
| 11 | `scripts/check_gate.py` | NEW rig, no API: gate blocks/opens correctly, immutability, persona guard, scope-requires-norms | 80 |

Unchanged: `1_prepare_graph.py`, `check_context.py`, the four context tools,
`context.py`, `telemetry.py`, `graph.py`, `active.py`.

Order: 1–2 + 6 (root testable alone, ~3 calls) → 3–5 → 11 (offline gate
proof) → 7–9 → 10 → offline suite (parse, ADK load, declaration transmission,
firewall, check_context, check_gate) → 2–3 live runs.

Quota: root ~3 + each sub agent ~5–7 → **~15–17 calls/run**, at the ceiling;
retry absorbs it.

Exit questions this milestone answers:
1. Do blind norms come out free of dataset vocabulary and data-statistics
   language? (Milestone 1's did not -- that is the regression test.)
2. Do persona-derived norms actually differ, or reconverge despite personas?
3. Does phase-2 mapping choose sensible, overlapping scopes?

### Milestone 2 — built and measured (26 Aug 2026)

All 11 pieces built. Offline: 25/25 gate checks pass; tree loads; all 7 tool
descriptions transmit; no cross-key leak; no schema words in the root's
instruction; firewall clean. Two live runs, both `completed`:

| | run 072336 | run 072441 |
|---|---|---|
| calls / time | 10 / 12.3s | 13 / 44.4s (4 retries -- ceiling absorbed) |
| **blindness proof** | **VERIFIED both agents** (norms at #2/#3, first data call at #4/#5) | **VERIFIED both agents** |
| personas | structural formalist vs empirical realist | structural formalist vs empirical historian |
| norms differ | yes -- and BOTH carry the "may flag what is factually true" stance | yes |
| scope overlap | 6 relations shared (spouse, sibling, diplomatic relation, citizenship, birth, death) | agent 1's scope (spouse, sibling, diplomatic relation) is a SUBSET of agent 2's 14 |

Exit questions:
1. **Blind norms free of dataset vocabulary?** Yes, and mechanically proven
   per run. Norms speak in world/ontology terms ("cardinality", "birthplaces")
   -- no codex-s labels, no data statistics. The Milestone-1 regression
   (norms soaked in schema) is gone.
2. **Do persona-derived norms differ?** Yes, sharply: the formalist flags
   structural violations "regardless of real-world plausibility" (= flags
   TRUE facts); the realist flags falsehoods "even if the graph schema is
   formally unbroken". The worked example's target pair, produced unprompted.
3. **Sensible overlapping scopes?** Yes -- substantial overlap both runs,
   including the disagreement-relevant symmetric relations. The
   Russell Brand one-way spouse edge falls in BOTH agents' scopes in both
   runs: the disagreement case is live.

Observed, for the seed harness later: the root's persona AXIS was
formalist-vs-external-truth in both runs. Within-run difference is what the
design needs and it is strong; across-run persona variance is unmeasured.

---

## 12. Finding anomalies — norm-shaped candidate generators (brainstormed 26 Aug)

**The dilemma.** Option 1 (agent reads all 36,543 triples) dies on context.
Option 2 (one link predictor shortlists for every goal) dies on a fact:
DistMult is mathematically symmetric -- score(h,r,t) = score(t,r,h) -- so the
formalist's first signal, a mutual bond recorded one-way, is invisible to it
IN PRINCIPLE. One scorer cannot serve different norms, and forcing it would
reopen the predecessor's seam (norms with no causal path into detection).

**DECIDED-pending-agreement: Option 3.** A small menu of CANDIDATE
GENERATORS, each norm-shaped. Phase 2 extends: norms -> scope -> generators.
Generators FIND (deterministic, graph-scale); the agent JUDGES (reading-budget
scale, by its norms). The LLM never scores or ranks -- it removes and
explains (INV-3 preserved).

Menu v1, grounded in the graph (probed 26 Aug):

| generator | mechanism | serves | measured yield |
|---|---|---|---|
| `implausible_links` | KGE low score, precomputed | "false in the world" norms | 3,655 planted negatives to find |
| `reciprocity_gaps` | one-way edges on mostly-symmetric relations | mutuality norms | **191 real**: 180 diplomatic, 10 unmarried partner, 1 spouse (Russell Brand) |
| `multiplicity_outliers` | heads with >1 value on typically-unique relations | cardinality norms | **9 real**: double causes of death (Fuller, Cole...) |
| `type_clashes` | entity types vs relation's typical types | typing norms | 0 here -- the slice is type-clean; absence is still a findable answer |

Unservable norm, recorded honestly: anachronisms -- no date relations in
codex-s; judge-time world knowledge only.

**Bonus finding.** The 9 double-causes-of-death are a second LIVE
disagreement family: formalist flags multiplicity, realist judges medical
coherence and may pass. With Russell Brand that is two real
true-fact-disagreement families before M3 is built.

**M3 deltas.** `get_candidates` -> `find_candidates(generator, ...)`: one
tool, menu behind it (fixed tool list as the menu grows). Recall ceiling =
union of chosen generators. OPEN: gate generator choice behind a commitment
tool, or inline `why` only? Lean: no third gate -- norms are already frozen,
generator choice is instrumentation; record choice + why in the run file.

**§12 in plain words.** Each agent is a judge who can only read a small stack
of files; the generators are its assistants. An assistant is dumb but fast --
plain code that sweeps all 36,543 triples in seconds and knows exactly one
kind of suspicious. The judge picks the assistants that match its OWN norms
(the link predictor suits a "false facts" norm; the reciprocity query suits a
"mutual bonds recorded one-way" norm -- the link predictor cannot see that
kind at all), reads their shortlists a page at a time, and gives each
candidate a verdict by its norms: anomaly / ok / out of scope / unsure, with
one line of why. **Code finds, the agent judges** -- code covers the whole
graph but has no viewpoint; the agent has the viewpoint but cannot cover the
graph.

---

## 13. Milestone 3 — implementation plan (find and judge, ⑤–⑥)

Ends at verdicts recorded per agent. Evaluation/composition (⑦) is M4.

| # | piece | change | ~lines |
|---|---|---|---|
| 1 | `scripts/1_prepare_graph.py` | EXTEND: after merging, sample verified negatives (`--ratio`, `--seed`) into `prepared/kg.tsv` and write `prepared/ground_truth.tsv` (label, kind=verified_false). Guards: a negative must not already be in the graph, no duplicates, all-zeros line printed | +60 |
| 2 | `scripts/2_train_scorer.py` | NEW: PyKEEN (DistMult default) on the contaminated graph; win32 thread guards; saves model AND `prepared/scores.npy` scoring every triple, plus a manifest (graph hash, model) so a stale score file refuses loudly | 120 |
| 3 | `tools/generators/` | NEW package, one file per assistant, shared contract `find(scope_ids, ctx) -> [(triple, note)]`, all deterministic: `implausible_links` (reads scores.npy + manifest check) · `reciprocity_gaps` (one-way edges where symmetry ≥ 50%) · `multiplicity_outliers` (>1 value on typically-single-valued relations) · `type_clashes` (types outside the relation's dominant types) | 4 × ~60 |
| 4 | `tools/find_candidates.py` | NEW, the ONE agent-facing finder: `find_candidates(generator, why, page)` — requires the caller's scope; restricts every generator to it; pages of 10, labels + per-candidate note ("no reverse edge recorded"); assigns stable ids (c1, c2…); records what was served per agent; total capped at the reading budget N | 110 |
| 5 | `tools/submit_verdicts.py` | NEW: batch of `{id, verdict ∈ anomaly/ok/out_of_scope/unsure, why}`; rejects ids never served to the caller; accumulates `verdicts_N` across batches | 90 |
| 6 | `agents/sub_agents.py` + `config.py` | EXTEND: phase 3 in the instruction (pick assistants matching YOUR norms, read, judge); budgets: `READING_BUDGET_N = 30`, `PAGE_SIZE = 10`, tool budget → ~16 | ~40 Δ |
| 7 | `scripts/3_run_audit.py` | RENAME+EXTEND `2_run_setup.py`: same tree, now runs through verdicts; run file adds generators chosen (with why), candidates served, verdicts; blindness proof unchanged | +80 |
| 8 | `scripts/check_generators.py` | NEW rig, no API: every generator on the full graph and on a sample scope — counts, examples, determinism. The eyeball checkpoint before any agent touches them | 90 |

Unchanged: context store, the four data tools, `assign_perspective`,
`declare_semantics`, `select_scope`, phase gate (candidate/verdict ordering is
enforced inside the new tools: no scope -> no candidates; not served -> no
verdict).

Order: 1 → 8a (generators on the clean merge, pre-contamination sanity) → 2 →
3–5 → 8 (full rig) → 6–7 → offline suite → live runs.

Quota: setup ~10–13 + per agent ~7–9 (generators + 3 pages + 3 verdict
batches) → **~28–32 calls/run**, two quota windows; retry absorbs.

OPEN before build: negatives `--ratio` (lean: ~500 planted ≈ 1.4%, keeps
reading budgets meaningful) · N=30 v1 (agent may lower, never raise) ·
`implausible_links` model: DistMult is fine for falsehood-hunting even though
symmetric — its blindness to direction is exactly why reciprocity_gaps exists.

Exit questions:
1. Do agents pick generators that MATCH their norms (formalist → reciprocity/
   multiplicity, realist → implausible_links)?
2. Do the two agents give DIFFERENT verdicts on the same true fact
   (Russell Brand, double causes of death)?
3. Does the realist actually catch planted verified-false candidates the
   generator surfaces?

### Milestone 3 — built and measured (26 Aug 2026)

All pieces built; 36/36 gate checks; firewall clean. One handoff bug found
live and fixed: select_scope's confirmation still said "you are done" from
M2, and both auditors obediently stopped before phase 3 -- the tool response
is the last thing the model reads, and it steers.

**The scorer finding.** DistMult trained ON the contaminated graph cannot
separate CoDEx's hard negatives: AUC 0.617 (dim 64/100ep) vs 0.617 (dim
128/500ep) -- not undertraining. Training memorizes the planted triples as
positives; type-consistent negatives break no regularity. Per-generator
reachability of the 500 planted: multiplicity_outliers 70 (29% precision),
reciprocity_gaps 31 (14%), type_clashes 6, implausible_links top-100: **0**.
Structural generators carry detection; the KGE alone would have been blind.

**First full audit run (075904): everything worked.**
- Blindness verified both agents; 14 calls, 11.8s.
- Generator<->norm match EXACT: formalist -> reciprocity_gaps ("topological
  symmetry"), realist -> implausible_links ("empirical plausibility").
- Formalist: 10/10 anomaly -- ALL true facts (one-way diplomatic edges),
  flagged per its norms "regardless of real-world plausibility". The
  true-but-anomalous class, en masse.
- Realist: 7 anomaly / 3 ok; **5 of 7 anomalies are planted falsehoods**
  (Mendelssohn/Tocqueville/Obruchev US citizenship, Sennett born Moscow),
  each with correct world-knowledge reasoning. One planted missed (Lieberman
  -- an honest reviewer error, the thing reviewer-validation measures). Two
  flagged "true" facts may be REAL Wikidata errors (Illich US citizenship)
  -- kind=real means un-planted, not verified-true.
- **The scope rescued the weak scorer**: implausible_links top-100 globally
  holds 0 planted, but the realist's biographical SCOPE filtered the noise
  -- its served page held 6 planted in 10. norms -> scope -> generator
  composition turned AUC 0.617 into 71% verdict precision.

Not yet observed: the same candidate judged differently by both agents (the
scopes and pages did not intersect this run). That is M4's union/disagreement
report, plus more runs.

---

## 14. Milestone 4 — built and measured (26 Aug 2026)

Built: the evaluator (sole reader of ground_truth), the reciprocity
interleave fix (a page is now a cross-section, not the front of the largest
queue), and the second-opinion phase (each auditor judges the other's flags
BLIND -- neutral note, no verdicts, no hint another auditor exists; reviewer
agents resolve to their principal's stores). 42/42 offline checks.

**Run 082940 (30 calls, 99.8s, 3 retries absorbed, blindness verified):**

| | formalist | empiricist |
|---|---|---|
| judged | 15 (10 own + 5 second-opinion) | 20 (10 own + 10 second-opinion) |
| anomaly precision vs planted | 7/10 | 7/12 |
| planted seen but missed | 0 | 0 |

**Composed:** union 15 flags, agreement 7 -- and the agreement set IS the
planted set (all 7 planted that were served, caught by both). The
disagreement set has 8 members, all unplanted, in exactly the two designed
shapes:

1. TRUE facts the formalist flags and the empiricist passes: one-way
   diplomatic edges ("lacks the reciprocal link" vs "Cape Verde maintains
   normal diplomatic relations with the EU"). The Russell Brand structure,
   live, on real triples.
2. Facts the empiricist flags and the formalist DECLINES to judge:
   occupation errors ("Goethe was a writer, not a composer") met with a
   principled out_of_scope ("my norms evaluate schema compliance, not
   factual accuracy"). The abstention verdict working as designed -- and
   these unplanted flags are candidate REAL Wikidata errors.

The worked example's three-row structure (§10) is realised: agreement =
the verified-false; disagreement = the norm-dependent; and no answer key is
asked to settle what norms legitimately dispute.

M4 exit questions: (1) same-fact dual verdicts -- YES, 8. (2) numbers --
70%/58% precision, zero misses on served planted; union adds breadth (15 vs
10/12 flags) though both caught the same 7 planted, BECAUSE second opinions
propagate every flag to both judges. (3) disagreements read as viewpoints --
yes: coherent norm-grounded reasons on both sides, n=1 run.

**Naming (DECIDED 26 Aug).** The sub agents are OBSERVERS, not auditors.
"Auditor" implied an external standard of correctness; the architecture's
claim is the opposite -- anomaly is a property of the standpoint, and an
observer sees according to who it is. It is also the thesis's own word: the
project is multi-observerbility, the predecessor multi-observer, and an
observability point is where an observer stands. Code names: observer_1/2,
observer_1_reviewer for the second-opinion phase. Old run files store agent
names positionally, so they still evaluate; their stored "agent" fields keep
the historical name.

**Naming, completed (26 Aug).** The whole vocabulary is now the observer
family: the tree is `observation`, one run is an observation, scripts are
`3_run_observers.py` / `4_evaluate_verdicts.py`, run files are
`run_*_observers.json`, the ADK app is `multi_observer`, and the trigger
message is "Begin the observation." `agents/reviewer_agents.py` holds the
returning observers (second opinions). "Audit"/"auditor" survive only in
historical sections of this document and in old run filenames, which the
evaluator still accepts via --run.

**Tool naming, tightened (26 Aug).** `sample` -> `show_examples` (actionable,
matches the describe_ family), `lookup` -> `explain_term` (says what it looks
up), `find_candidates` -> `find_suspects`, and the generators package ->
`tools/scanners/` -- they scan the whole graph for one kind of suspicious
each and hand the observer suspects to judge. "Scanner" kept over "scorer
assistant" deliberately: three of the four produce no scores at all, only the
KGE-backed one does, and calling them scorers would smuggle back the idea
that the machinery ranks while the observer rubber-stamps. The observer is
the only judge; scanners only point.

**Plain-word scanner names (26 Aug).** The scanner menu and the inspection
tool are model-facing vocabulary -- the observer TYPES these as arguments --
so academic words became plain ones: reciprocity_gaps -> `one_way_links`,
multiplicity_outliers -> `too_many_values`, type_clashes -> `odd_types`
("odd", not "wrong": scanners point, they do not judge), implausible_links ->
`unlikely_facts`, and show_examples -> `inspect_triples`, completing the
inspection family (describe_dataset, describe_relation, explain_term,
inspect_triples). Old run files keep historical scanner names in their
records; the evaluator only displays them.

---

## 15. Dataset-leak audit and purge (27 Aug 2026)

Principle enforced: dataset-specific content lives ONLY in the dataset's
loader module (`loaders/codexs.py`: CARD, paths, NEGATIVE_SPLITS) and in what
the inspection tools return from the loaded data at runtime. A 5-lens audit
(model-facing strings, agent instructions, comments, behavioral hardcoding,
plus a synthetic-dataset switch test) found and fixed:

- **Model-facing (7)**: `describe_dataset` hardcoded a CARD-like sentence
  (now interpolates `DATASET.CARD`); `declare_semantics` hinted the domain
  ("marriages, careers, places" -- deleted; "people or places" -> "entities");
  `describe_relation`/`explain_term` said "Wikidata description" (-> "the
  description shipped with the dataset"); `find_suspects` used
  "Alice --spouse-- Bob" (-> "<head> --<relation>-- <tail>");
  `unlikely_facts`' stale error hardcoded paths (-> loader values).
- **Behavioral (6)**: negatives paths moved into the loader as
  `NEGATIVE_SPLITS`; label uniqueness is now CHECKED at load (a colliding
  dataset fails loudly) instead of assumed from one dataset's audit; all
  three rigs derive their probes from the loaded dataset -- check_gate picks
  its scope relation by the scanner's own criterion, so the rigs port with
  the switch.
- **Human-facing (12)**: scanner and loader docstrings de-specified
  (mechanisms stay, anecdotes point to this document, which keeps them).

Verified after: transmitted tool descriptions contain no dataset words
(checked via FunctionTool declarations), all rigs pass, prepare runs with
guards at zero. Note for future audits: the workflow's limit-killed verify
agents were mislabeled "refuted" -- treat a null verdict as UNVERIFIED.

### §15 closure — the two remaining audit items (27 Aug 2026)

**Empirical switch test: PASSED.** A scratch copy of the machinery was
pointed at a synthetic "machines and parts" dataset (9 entities, 3 relations,
its own CARD, its own negatives file) by editing only loaders/active.py plus
a new 25-line loader module. Results: 1_prepare ran with guards at zero;
describe_dataset opened with the MACHINES card; all 42 gate checks passed
with probes the rig derived itself (it found "linked with" as its gappy
relation); the scanners ran deterministically (one_way_links caught the
planted one-way edge); the ADK tree loaded; and a word-boundary sweep of
every instruction and every transmitted tool description found ZERO
people-domain words reaching any agent. The one caution for future sweeps:
"persona" contains "person" -- use word boundaries.

**Re-baseline run (027_ era, purged text): complete**, blindness verified,
20 calls, 6 retries absorbed. Notable: this run caught 0 planted falsehoods
-- the observers' scanner and scope choices simply never reached them
(observer_1 flagged 12 structural one-ways, all unplanted; observer_2 passed
18 of 20). Against the earlier run's 5/7 precision this is the variance the
seed harness exists to measure: per-run objective performance swings on
which observability points the root deals out. The disagreement set (10)
remains rich either way.

## 16. Mining rules — the TAXO-grounded roster (28 Aug 2026)

**DECIDED — "scanners" are now "mining rules"**, `tools/mining_rules/`, and
the roster is grounded in the TAXO anomaly taxonomy (Senaratne et al.,
arXiv:2412.04780, §5) instead of ad-hoc: every non-missingness,
entity-to-entity TAXO type maps onto one of four counting rules, plus the
kept plausibility channel. Ten paper types → five rules. Full audited survey
(16 designed rules, 3 adversarial audits, yields measured on kg.tsv):
<https://claude.ai/code/artifact/515dcfa9-eeaa-4eab-96f7-0bd6b68da80d>.

| rule | TAXO types | mechanism |
|---|---|---|
| `odd_pairs` | contradicting facts, incorrect predicate, entity ambiguity, one-way records | rare (relation, direction) combination on one entity pair (≤2 pairs graph-wide, both relations ≥20 pairs); self links on non-looping relations; missing mirrors on ≥50%-two-way relations (the retired `one_way_links`, absorbed) |
| `odd_types` | invalid predicate | leave-one-out type support: no OTHER entity of any of the occupant's kinds ever filled this (relation, slot). Replaces the 80%-dominance version — 49 of 65 findings fall where dominance never fired, and minority-but-attested kinds no longer false-fire |
| `odd_values` | predicate ambiguity, redundant facts, duplicate facts | extra values on ≥90%-single relations (the retired `too_many_values`, absorbed); value pairs the graph itself links by a hierarchy-shaped (<0.2 reciprocity) relation; stem-equal value labels |
| `odd_degrees` | rare entity, prolific entity | degree vs same-kind peer median, both tails, audit-tightened gates (≥5× median AND >p99) and hard caps (5 thin + 10 heavy) — findings are usually TRUE; their value is the note |
| `unlikely_facts` | incorrectness at large | unchanged KGE percentile — kept because its provable blind spots (symmetry, popularity bias, per-triple scoring) are exactly the counting rules' ground |

Missingness types stay at the storage layer per TAXO itself → ingest guards
in `1_prepare_graph.py` (duplicates already guarded: GUARDS prints 0).

**Measured on the contaminated graph (500 planted):** odd_pairs 244
candidates / 31 planted (15 in first 30 — round-robin pays); odd_types 65 /
0 planted (expected: CoDEx negatives are type-clean — this rule is
norm-coverage, not a planted-catcher); odd_values 269 / 70 planted (5 in
first 30 after per-relation interleave fix; a pooled queue had diluted it to
1); odd_degrees 15 / 1. Union of the four counting rules: 585 candidates,
102/500 planted — the same ~20% recall ceiling as the old roster, now with
contradiction/ambiguity/redundancy coverage the old roster lacked.

**Ordering lesson re-learned:** cross-section beats concatenation, but
pooled case-queues dilute measured detectors — one queue per relation
inside a case, then round-robin across everything.

State/JSON renames: `scanners_N` → `rules_N`, run JSON `"scanners"` →
`"rules"`, served/verdict field `"scanner"` → `"rule"`,
`check_scanners.py` → `check_mining_rules.py`. Older run files keep the old
keys; the evaluator reads only new-format runs from here on.

## 17. The reading-budget fix — measured (28 Aug 2026)

Diagnosis: observers judged one page (10) and stopped, using a third of the
30-candidate budget. Two "you are done" sites caused it — the phase-3
instruction and submit_verdicts' closing line (the select_scope lesson
again: the tool response is the last thing the model reads). Fixed both:
the instruction now says SPEND the budget across every norm-matching rule,
and submit_verdicts hands the hunt back while room remains (reviewers, and
a spent budget, still end the phase). OBSERVER_TOOL_BUDGET 16 → 20.

Before (run_20260827_155020) → after (run_20260828_005921), same graph:
facts read 20 → 54 · rules used 1+1 → 3+1 · flagged union 11 → 24 ·
disagreement set 2 → 5 committed splits · planted caught 6 → 6 ·
precision 55%/67% → 26%/32%.

The result behind the numbers: reading volume no longer binds — RULE
CHOICE does. The formalist spent pages on odd_types (a 0-planted,
norm-coverage rule) and unlikely_facts (0 planted in early pages, the
memorization effect); the empiricist put all 30 on unlikely_facts. Nobody
chose odd_values, the roster's top planted-catcher. The planted-yield of a
run is now a function of which rules the observer's NORMS select — a
measured property of the standpoint design, not a bug. We deliberately do
NOT nudge the menu toward planted-heavy rules: observers judge by norms,
not by the answer key, and coaching rule choice would optimize the metric
by contaminating the design. Run-to-run rule-choice variance belongs to
the seed harness.

The precision drop is the flip side of coverage: the extra flags are
norm-true verdicts (voice-as-instrument, empire-as-country, region-as-
diplomatic-partner) — exactly the standpoint judgments the disagreement
set exists to hold. Same-fact splits tripled, including the first
REVERSED split (James Taylor: empiricist flags, formalist passes).

## 18. Selected evaluation metrics (1 Sep 2026)

**DECIDED — the headline metrics are Precision@K and Recall@K on the
UNION of observer anomaly flags**, K = the union's own size. Detection is
"flagged by at least one observer": the research question is what DIFFERENT
perspectives find, so agreement is a confidence tier inside the union,
never the definition of detection. Implemented in 4_evaluate_verdicts.py
(UNION block).

Protocol per run: K, K/|graph|, P@K (planted hits / K), R@K (hits / 500)
printed beside its ceiling min(K,500)/500 — recall is budget-bound and must
never be read bare. Companion metric: COMPLEMENTARITY on primary flags
(c-ids only — found by the observer's own hunt): alone/alone/both, and
union gain over the best single observer. Primary flags because the review
phase deliberately converges the sets afterwards (measured: run
20260828 shows 11+11 unique vs 2 shared before review; "6 = 6 = 6" after).
Baseline: the standalone scorer's top-K at the same K, same graph.
Reported numbers are mean ± sd over seeded runs (single-run values swing
25% → 0% between consecutive runs; the seed harness is a prerequisite for
any published number).

Prior art anchoring: ADKGD (Eq. 33-34) and CAGED (Eq. 12) use P@K/R@K
ladders (noting P@K = R@K when K = anomaly ratio); SEKA evaluates
precision/recall at expert budget b = 100 ("the number of triples an
expert can handle manually") — the budget framing is our reading budget,
published by the home group. SEKA Table 11 (per-TAXO-type coverage of two
detectors in the top-100) is the field's only detector-agreement
evaluation and the direct precedent for our complementarity metric.
AUC/AUPR are RESERVED for the scorer layer (which ranks every triple;
DistMult AUC 0.617 measured): the observer layer emits a decision set,
not a ranking — there is no threshold to slide, so curve metrics do not
exist there and will not be fabricated. Validated precision (manual
adjudication of the union's unplanted flags, Senaratne-group top-100
style) is the planned upgrade that turns P@K from a lower bound into a
true value plus a discovery count.

### 18.1 Improvement levers, ranked (light survey, session evidence + repo papers)

The funnel fact that orders everything: in both measured runs, observers
missed ZERO planted facts that were served to them ("planted seen but not
flagged: 0"). Judging is not the bottleneck — SERVING is. P@K rises by
putting more planted into the pages read; R@K rises the same way (its
ceiling only via budget).

1. **In-rule ranking** (cheap, no design change): order each rule's
   candidates strongest-lead-first — odd_values extra case by
   single-share, odd_degrees by peer ratio (odd_pairs already sorts by
   symmetry). Measured precedent: the odd_values interleave fix alone
   moved planted-in-first-30 from 1 to 5.
2. **Fix the plausibility channel's memorization**: held-out scoring for
   DistMult (score each triple from a model that never trained on it) or
   the planned ADKGD dual-channel swap (bridge exists). Evidence: AUC
   0.617 + zero planted in early pages = the channel currently
   contributes nothing at K; ADKGD/CAGED report large gains over
   translational baselines exactly at K ≤ 5%.
3. **A corroboration rule from the survey backlog**: SEKA's CPA
   path-corroboration as a sixth mining rule (judged yes-fit in the
   adoption survey; code public) — a falsehood lead with different blind
   spots from both the KGE and the counting rules.
4. **Standpoint diversity → complementarity**: the axis-lottery for root
   personas (seeded axis list in the trigger). Evidence: three runs dealt
   the same formalist/empiricist pair; the Sep-1 pair's rule choices
   yielded P@K = 0 — which standpoints get dealt currently decides the
   number. Scope disjointness guidance is the stronger variant (union
   covers more graph); both preserve norms-choose-rules integrity.
5. **Budget sweep** (raises the recall ceiling itself): budgets 30/60/120
   → ceilings 4.8%/9.6%/19.2%; linear API cost; also produces the short
   P@B curve for the paper.
6. NOT a lever: coaching rule choice toward planted-heavy rules — that
   optimizes the metric by contaminating the design (observers must never
   be steered by the answer key).

## 19. The pool — survey, shortlist, judge (2 Sep 2026)

**DECIDED — observers no longer pick ONE mining rule and read its pages;
every rule runs on the observer's scope, the leads are merged into one
POOL, and the observer's norms SELECT from the pool.** §17 measured that
rule choice, not reading volume, bound the planted yield: an observer that
picked odd_types (0 planted) or unlikely_facts (0 planted, memorization)
spent its whole budget on a dry rule, and the answer-key-blind design
forbids steering that choice. The pool removes the choice without adding
a nudge: the observer sees what all the counting rules turned up and uses
its semantics to decide which leads its norms speak to. Every rule's leads
reach the observer; the norms still do the selecting.

Mechanics (tools/mining_rules/pool.py, find_suspects, shortlist_candidates):
- `build_pool(scope, ctx)` runs each registered rule on the scope, merges
  by triple, puts leads two rules agree on first (by agreement count, then
  best rank), then round-robins the rules in registry order, each
  strongest-first (the §17/Stage-1 in-rule ranking is what makes the
  round-robin worth anything). Capped at POOL_CAP = 120, paged at
  POOL_PAGE = 40 (≤ 3 pages), ids p1..pN, deterministic for a scope.
- **Surveying is free**: find_suspects serves pool pages and spends no
  budget. The observer is told to read the whole pool before choosing.
- `shortlist_candidates(ids, why)` turns pool ids into served c-ids, up to
  READING_BUDGET = 30. Unshortlisted leads are "not examined" — never an
  implicit ok. Validation refuses out-of-range ids, an empty why, and
  shortlisting before the survey; duplicates and repeats are absorbed.
- submit_verdicts is unchanged downstream (every shortlisted c-id needs a
  verdict; it hands the hunt back while budget room remains). Reviewers,
  the dashboard and the evaluator are untouched except for a new
  "caught by N rules" chip and pool meta.
- A served entry carries every rule that surfaced it (`rules`, and a
  `rule: note | rule: note` merged note) so corroboration is visible to
  the observer and exportable.

**Rules-only baseline.** `interleave(pools, K)` zips the two observers'
pools strongest-first, dedupes and cuts at K — what the union would be if
the LLM made no selection at all. Reported by the evaluator ("the
observers' selection beats / does not beat it") and as the `base` column
of the batch runner. This is the honest equal-K comparison for the pool
design: the observers must add value OVER the merged rules, not merely
over a single rule.

**unlikely_facts RETIRED.** Removed from the RULES registry (module kept,
dormant). Evidence: across the Sep-1 runs it took ~160 of ~330 reads and
surfaced 0 planted — the DistMult scorer memorized the planted positives
(AUC 0.617; §18.1 lever 2). It stays retired until the held-out/ADKGD
channel fix (IMPROVEMENT_PLAN Stage 2b) gives it a measured reason to
return; it would re-enter as a fifth queue in the round-robin.

**Pacing.** Free-tier 15 RPM was hit once the pool added calls. Every
model call on root, observers and reviewers is preceded by an async
CALL_PAUSE = 4.0 s (agents/pacing.py, before_model_callback). A full run
is ~27 model calls, ~100 s wall.

Offline measurements (probe over TRUTH, evaluator-side only):
- uncapped all-relations pool: 585 leads / 102 planted (the roster's
  ceiling); corroborated leads: 8 (odd_pairs + odd_types, all one Don
  Rickles religion pair), 0 planted — corroboration is harmless but not a
  lever at this roster.
- capped pool (120): 25 planted (21%), pages holding 8 / 9 / 8.
- rules-only top-20/30/40/60: 10% / 17% / 20% / 20%.
- on the three Sep-1 scopes: pools of 120 with 25–50 planted (one
  70-lead pool with 1).

First live run, **run_20260902_075018** (BLINDNESS VERIFIED both, gate
all-PASS, 27 calls, 98 s): both observers surveyed pages 1-2-3 then
shortlisted then judged, exactly as designed. The structuralist (42
relations) shortlisted 30 (odd_types 22, odd_pairs 6, odd_values 2) and
flagged 36 with 0 planted; the pragmatic historian (11 relations)
shortlisted 11, all odd_values place-of-birth extras, flagged 10 with 8
planted. Union K = 36, **P@K 22%, R@K 1.6% (ceiling 7.2%)**; rules-only
top-36 = 8% (3/36) — the observers' selection beats the merged rules
(8 vs 3). Complementarity: 28 + 8 unique, 0 shared, all 8 hits from one
side. Same §17 lesson in a new form: the formalist's norms select
odd_types (norm-true, planted-empty); the pool did not change WHAT the
norms want, it changed what they could see.

Batch `pool`, 3 runs (`6_run_batch.py --n 3 --label pool`, all BLINDNESS
VERIFIED): **P@K 78.5% ± 4.3%, R@K 2.9% ± 0.5%, K 18.7 ± 3.1, hits
12/17/15**; rules-only top-K on the same pools 3.4% ± 3.0%; Stage-1 (one
rule per observer) was 17.7% ± 22.1%. The lottery is gone — the sd fell
from 22 points to 4. Two readings: (i) selection is semantic — the pool
serves odd_types first on every page and the observers walked past it to
odd_pairs leads whose entities they could name as unrelated; (ii)
observers shortlist well under budget (4–21 of 30) and say their norms
are silent on the rest, so K is small and self-chosen: precision is high
because of it and recall is bound by it (ceilings 3–4%). Raising K
without coaching is the open question; the full table and per-run
observations are in IMPROVEMENT_PLAN.md (Stage 1b). §20 is the answer.

## 20. Read-and-rule + the P@K ladder (2 Sep 2026)

**DECIDED — two changes that make the numbers comparable to the detector
literature (ADKGD/CAGED report P@K ladders at fixed K; SEKA at expert
budget b): (i) observers judge the pool PAGE BY PAGE instead of
shortlisting from it; (ii) the evaluator reports P@K/R@K at fixed
K = 50/100/150/200 (+500 footnoted) off a confidence-tier ranking.**

**Why shortlisting had to go.** The §19 batch measured that observers
shortlist 4–21 of a 30 budget and declare their norms silent on the rest:
precision 78% but K self-chosen at ~19, recall capped at ~3% by
reticence, not by the roster (whose pooled reach is 102/500). A fixed-K
protocol needs the budget SPENT. Survey-then-shortlist made stopping the
default; read-and-rule makes coverage the default while the viewpoint
moves wholly into the verdicts — anomaly / ok / out_of_scope ("my norms
are silent") / unsure, every served lead ruled on explicitly, nothing an
implicit ok. No coaching is involved: nobody points at planted-heavy
anything; the protocol says only that every candidate served gets a
ruling.

Mechanics: find_suspects now SERVES each page's leads as candidates
(c-ids) directly — READING_BUDGET 30 → 160, POOL_CAP 120 → 200 (5 pages
of 40), OBSERVER_TOOL_BUDGET 20 → 32; re-fetching a page re-serves the
same ids and charges nothing; submit_verdicts hands back "fetch page
N+1" while budget and pool both have room. shortlist_candidates is
RETIRED (module kept for the §19 run files). Reviewers unchanged
(REVIEW_CAP 15). Offline probe on the §19 scopes: planted in the first
160 pool leads = 33 (observer_1, uncapped pool 585) and 42 (observer_2,
uncapped pool 174) — if the funnel fact holds, recall's reachable range
moves from ~3% to ~10–14%.

**The ranking that makes fixed-K honest.** The system emits a decision
set, not a ranking, so the evaluator builds one from what a run records,
ordered by confidence tier:
  1. flagged anomaly by BOTH observers,
  2. flagged by one,
  3. unsure,
  4. unexamined pool leads (pool order) — judged out_of_scope ranks here
     too: "my norms are silent" carries no information about truth,
  5. judged ok (an informative negative — examined and passed),
then nothing (triples no rule surfaced; the ladder reports exhaustion).
Within a tier: best rank across the observers' UNCAPPED pools (rebuilt
deterministically from the run's recorded scopes — pool.py's cap=None).
Each rung reports its JUDGED SHARE, so a reader can see which K the LLM
actually owns and where the ranking degrades into the rules-only tail;
the rules-only interleave at the same K prints beside every rung. K=500
is the conventional rung where P@K = R@K (500 planted); with the current
roster P@500 ≤ 20% by reach — that ceiling printed is the standing
argument for a fifth rule (Stage 3) or the ADKGD scorer arm.

Implemented in scripts/eval_lib.py (ranking, truth-free) +
4_evaluate_verdicts.py (ladder section) + 6_run_batch.py (per-rung
mean ± sd). Live numbers recorded in IMPROVEMENT_PLAN.md Stage 1c.

Measured (3-run batch, 3 Sep 2026): **P@50 43.3% ± 10.1 / P@100 37.0% ±
4.4 / P@150 30.0% ± 2.4 / P@200 25.0% ± 1.8** vs rules-only 16/21/21/21;
R@200 ≈ 10%; ~34 planted caught per run (2.3× the §19 shortlist design)
at ~30-35 model calls, ~3 min per run. The top-50 rung is 100%
LLM-judged. Two findings worth carrying into the write-up: (i) the funnel
fact broke ASYMMETRICALLY — the structuralist passes 13-17 planted per
run because its norms are silent on factual falsity, the pragmatist
passes 1-5: judging-at-volume is a property of the STANDPOINT, which is
the thesis's point made measurable; (ii) an adversarial verification pass
(2 Sep) found and fixed: review r-id overwrite on re-fetch, REVIEW_CAP
15 → 40 (cap-15 silently truncated the agreement tier to the first 15
flags), out-of-order page fetches ending the hunt early, odd_types note
hash-seed nondeterminism, duplicate-id verdict batches, and a missing
kg_sha256 staleness bind in the evaluator — all covered by new
check_gate checks (all-PASS).
