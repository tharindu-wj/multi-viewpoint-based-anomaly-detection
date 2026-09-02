# Improvement plan — Precision@K / Recall@K on the union

Selected metrics: **P@K and R@K on the union of observer anomaly flags**
(DESIGN.md §18). This plan raises them in staged, cheapest-first action
items. Every stage has an **expected result** and a **gate**; a stage that
fails its gate escalates to the *further research* list at the bottom
instead of being silently absorbed. One change per stage, so improvements
stay attributable.

## Ground rules (from §18.1 — non-negotiable)

1. **The funnel fact**: observers have missed ZERO served planted facts in
   every measured run. Judging is not the bottleneck; SERVING is. Every
   lever below works by improving what reaches the pages read.
2. **The anti-lever**: never steer observers toward planted-heavy rules or
   facts. The observers have never seen the answer key — that is the
   claim. Improvements live in rules, scorer, and diversity mechanisms.
3. **Offline before API**: every change is first verified with the free
   probes (`check_mining_rules.py`, planted-reach counts) before spending
   quota on live runs.
4. **Blindness invariants hold throughout**: `check_gate.py` all-PASS and
   BLINDNESS VERIFIED are preconditions for counting any run.

## Baseline (to beat)

| run | K | P@K | R@K (ceiling) | complementarity (primary) |
|---|---|---|---|---|
| 20260828_005921 | 24 | 25% | 1.2% (4.8%) | 11 + 11 unique / 2 shared |
| 20260901_081533 | 22 | 0% | 0% (4.4%) | 14 + 8 / 0 |

Superseded 2 Sep 2026 by the Stage-1b pool batch: **P@K 78.5% ± 4.3%,
R@K 2.9% ± 0.5%, K 18.7 ± 3.1** (table under Stage 1b). That is now the
number to beat.

Union recall ceiling of the current rule roster: 102/500 = 20%.
Scorer channel: DistMult AUC 0.617, ~0 planted in early pages (memorization).

---

## Stage 0 — measurement protocol (prerequisite, ~1 h)

**Do:** a small batch runner: N=3 seeded runs per configuration,
`4_evaluate_verdicts.py` over each, report mean ± sd of K, P@K, R@K,
complementarity. (Not the full seed harness — just enough to judge gates.)

**Expected:** a baseline distribution instead of two anecdotes.
**Gate:** none — this stage cannot fail; it defines pass/fail for the rest.

## Stage 1 — in-rule ranking (free, offline-verifiable, ~2 h)

**Do:** order every rule's candidates strongest-lead-first:
- `odd_values`: serve extra-values relations in descending single-share
  (a 98%-single relation's extra value is a stronger lead than a 91% one);
- `odd_degrees`: already ratio-ranked — verify emission order honors it;
- `odd_types`: rank by slot population (more occupants = stronger "never");
- `odd_pairs`: already symmetry-ranked.

**Precedent:** the odd_values interleave fix alone moved planted-in-first-30
from 1 → 5.
**Expected:** planted density in each rule's first 30 rises; P@K follows.
**Gate (offline):** union of first-30s planted count > current (odd_pairs 15,
odd_values 5, others ≤1). **Gate (live):** mean P@K over 3 runs ≥ baseline
mean + 5 points. Fail → the pages are already as good as the rules can
make them → escalate to Stage 3 (new rule) with priority.

**Result (1 Sep 2026):** offline gate passed. Live batch `stage1`, 3 runs
(20260901_163745 / 163923 / 164149): P@K 11% / 0% / 42%, **mean 17.7 ±
22.1**, K 28 / 33 / 40. Not a pass on the +5 gate against a 12.5% baseline
in any meaningful sense — the sd is bigger than the mean. Reading the runs
gave the reason: the planted yield swung on WHICH rule each observer
picked (the 42% run was the one where an observer chose odd_pairs; the 0%
run had one observer on odd_types and the other on unlikely_facts). The
rule-choice lottery, not page quality, was binding → Stage 1b.

## Stage 1b — the pool: every rule runs, norms select (DONE 2 Sep 2026)

**Do:** stop making observers pick one rule. Run all rules on the scope,
merge into a ranked POOL (corroborated leads first, then round-robin over
rules strongest-first, cap 120, 3 free survey pages), and have the
observer SHORTLIST the leads its norms speak to (≤ 30), then judge those.
Retire `unlikely_facts` from the registry (0 planted in ~160 reads;
memorized scorer). Add 4 s pacing before every model call (DESIGN §19).

**Why this respects the anti-lever:** nothing points at planted-heavy
rules. Every rule's leads are shown; the observer's own semantics choose.
The lottery is removed by exposure, not by coaching.

**New baseline for this stage:** the rules-only equal-K union —
`interleave(pools, K)` — what the merged rules give with no LLM in the
loop. Offline: 10% / 17% / 20% / 20% at K = 20 / 30 / 40 / 60.
**Gate (live):** mean union P@K over 3 runs > rules-only top-K on the
same runs AND ≥ Stage-1 mean (17.7). Fail → the LLM selection subtracts
value; fall back to serving the pool head directly and escalate to Stage 3.

**First run** 20260902_075018: K 36, P@K 22%, R@K 1.6% (ceiling 7.2%),
rules-only top-36 8% → beats (8 vs 3). One-sided: 8/8 hits from the
historian's odd_values shortlist; the structuralist's 30-lead odd_types
shortlist held 0.

**Batch `pool`, 3 runs (2 Sep 2026, all BLINDNESS VERIFIED):**

| run | K | P@K | R@K (ceiling) | hits | rules-only @K | complementarity (primary) |
|---|---|---|---|---|---|---|
| 20260902_075018 (single, pre-batch) | 36 | 22% | 1.6% (7.2%) | 8 | 8% | 28 + 8 / 0 |
| 20260902_075410 | 16 | 75% | 2.4% (3.2%) | 12 | 0% | 4 + 12 / 0 |
| 20260902_075656 | 22 | 77% | 3.4% (4.4%) | 17 | 5% | 5 + 17 / 0 |
| 20260902_075917 | 18 | 83% | 3.0% (3.6%) | 15 | 6% | 10 + 1 / 7 |
| **batch mean ± sd** | **18.7 ± 3.1** | **78.5% ± 4.3%** | **2.9% ± 0.5%** | 14.7 | 3.4% ± 3.0% | |

**Gate: PASSED.** 78.5% vs rules-only 3.4% at the same K, and vs the
Stage-1 mean of 17.7% (best previous single run 42%). The sd collapsed
from 22 points to 4 — the rule-choice lottery is gone. Hits per run
doubled or better (3/0/17 → 12/17/15) at roughly half the K.

What the runs show:
- Observers shortlist FAR below budget (4 / 12, 7 / 18, 21 / 11 of 30):
  they say their norms are silent on the rest and stop, as instructed.
  Precision is high because K is small and self-selected; recall is
  bound by that K (ceilings 3.2–4.4%), not by the roster (whose pooled
  reach is 102/500). Raising K without coaching is the next question
  (Stage 5 budget sweep is moot while budget is unspent; the lever is
  what the observer counts as "spoken to").
- Selection is semantic, not rule-following: the pool served odd_types
  first on every page, and the observers walked past it to odd_pairs
  leads whose two entities they could name as unrelated ("Mickey Rooney
  --spouse-- R. Kelly", "Irène Joliot-Curie --sibling-- Tito Jackson").
  odd_pairs was picked by both personas in all three runs; odd_values in
  one; odd_types 5 leads total; odd_degrees never.
- The pre-batch single run (22%) is the outlier: its structuralist spent
  the full 30 on odd_types (0 planted). Personas were formalist +
  pragmatist in all four runs (the §18.1 lever-4 convergence, unchanged).
- The rules-only head is dry (0–6%): the pool leads with the 8
  corroborated Don Rickles pairs and odd_types' queue, both planted-empty
  — the LLM's value is precisely skipping them.

## Stage 2 — fix the plausibility channel (SHELVED 2 Sep 2026)

Superseded: the channel's rule (`unlikely_facts`) is retired from the
registry under Stage 1b, so there is nothing at K for a held-out fix to
improve until it re-enters. **Stage 2b (ADKGD dual-channel swap) remains
the planned comparison arm** — standalone scorer top-K vs the observer
union at equal K — and would re-admit a plausibility queue to the pool.
Original plan kept for the record:

**Do:** cross-scoring in `2_train_scorer.py`: split kg.tsv into 5 folds,
train on 4, score the held-out fold, rotate — every triple scored by a
model that never trained on it. Same `scores.npy` contract; the rule is
untouched.

**Why:** the channel currently contributes nothing at K (AUC 0.617,
memorized planted positives).
**Expected:** planted facts stop scoring "comfortably plausible".
**Gate (offline):** AUC ≥ 0.70 AND ≥ 3 planted in `unlikely_facts`'
first 30. Fail → **Stage 2b: ADKGD dual-channel swap** via the existing
file-contract bridge (the bigger gun; also yields the standalone-vs-inside
comparison arm at equal K). Gate for 2b: same, plus AUPR reported.

## Stage 3 — sixth rule: path corroboration (SEKA CPA port, ~1–2 days)

**Do:** offline precompute of SEKA-style corroboration (do alternative
paths ≤2 hops support each triple?) into a sha-bound file; new mining rule
`uncorroborated_facts` serving least-corroborated in-scope facts with
readable notes. Public code exists (AsaraSenaratne/SEKA,
`triple_features.py`); port the feature idea, not the 3.6-era stack.

**Expected:** a falsehood lead with different blind spots; union recall
ceiling rises above 20%.
**Gate (offline):** the new rule's first 30 contains ≥ 5 planted AND the
5-rule union ceiling > 20%. **Gate (live):** union P@K not degraded, R@K
up. Fail → rule joins the roster as coverage anyway if precision is
acceptable; else shelve and escalate.

## Stage 4 — standpoint diversity (axis lottery, ~half day)

**Do:** seeded axis list in `3_run_observers.py` (completeness, recency,
provenance, cultural neutrality, formal structure, empirical plausibility,
…); the trigger message hands the root ONE drawn axis pair; the root still
authors the personas. Optional stronger variant: scope-disjointness
encouragement in `select_scope`'s closing text.

**Why:** three runs dealt the same formalist/empiricist pair; which
standpoints get dealt currently decides P@K (Sep-1 pair: 0%).
**Expected:** varied archetypes across runs; union gain over best single
observer grows; rule-portfolio coverage widens (odd_values finally gets
picked by someone).
**Gate:** across 5 runs, ≥ 3 distinct archetype pairs AND mean union gain
(union hits − best single's hits, primary flags) > 0. Fail → diversity
must be injected at scope level instead → further research item F3.

## Stage 5 — budget sweep (raises the recall ceiling, ~1 h + quota)

**Do:** runs at READING_BUDGET 30 / 60 / 120 (ceilings 4.8% / 9.6% /
19.2%); plot P@B.
**Expected:** recall grows near-linearly if serving quality holds at depth;
where the curve bends is a finding either way.
**Gate:** none to pass — this stage produces the paper's curve. But if P@B
collapses at 60+, the rules' deep pages are weak → reprioritize Stage 3.

---

## Decision flow

Run stages in order. A passed gate → next stage. A failed gate → the named
escalation, then re-measure. After Stage 5, freeze the configuration and
run the full evaluation protocol (§18) for the write-up.

## Further research (only if gates fail)

- **F1 — noise-aware scorer training** (CKRL-style confidence weighting)
  if held-out scoring AND the ADKGD swap both fail their gates.
- **F2 — validated precision re-baselining**: manual adjudication of the
  union's unplanted flags (Senaratne top-100 protocol) — if P@K stalls, it
  may be measurement error: norm-true and real-source-error flags counted
  against us. ~18 facts per run; an afternoon.
- **F3 — scope partitioning**: root assigns complementary scopes
  explicitly if the axis lottery fails to diversify hunts.
- **F4 — dormant-rule activation**: the literal-module rules and the
  rare-combination scanner idea if a literal-bearing dataset lands.
- **F5 — review-phase widening**: cross-review a sample of 'ok' verdicts —
  currently pointless (zero served-planted missed) but the guard if the
  funnel fact ever breaks at higher budgets.
