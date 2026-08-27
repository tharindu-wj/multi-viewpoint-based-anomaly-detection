"""Export one observation run as a dashboard view-model. Nothing is judged here.

    python scripts/5_export_dashboard.py                     newest run
    python scripts/5_export_dashboard.py --run runs/run_...json

Reads the answer key alongside 4_evaluate_verdicts.py -- the evaluation
scripts are the ONLY readers of ground_truth.tsv; tools and agents never see
it. The dashboard shows planted status behind a deliberate reveal, so the
export carries it.

The point of this script: the frontend must contain NO graph logic and NO
dataset knowledge. Every case therefore leaves here with a pre-computed
EVIDENCE payload -- the drawable form of the mining rule's argument (the
ghost mirror edge, the parallel edges of a rare pair, the values fan, the
peer comparison) -- recomputed deterministically from the same prepared
graph the rules read. React only renders.

Writes dashboard/public/data/<run>.json and updates manifest.json.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import argparse  # noqa: E402
import collections  # noqa: E402
import datetime  # noqa: E402
import hashlib  # noqa: E402
import re  # noqa: E402
import statistics  # noqa: E402

import numpy as np  # noqa: E402

from loaders.active import DATASET  # noqa: E402
from loaders.context import get_context  # noqa: E402
from tools._observers import OBSERVER_NAMES  # noqa: E402
# The evidence must be computed by the RULES' own thresholds and helpers --
# a literal copied here would silently desynchronize the moment a rule is
# tuned (review finding).
from tools.mining_rules.odd_degrees import (HIGH_MIN, HIGH_RATIO,  # noqa: E402
                                            LOW_RATIO, MIN_PEERS,
                                            SLOT_MIN_PEERS, SOLID_MEDIAN)
from tools.mining_rules.odd_pairs import MIN_SYMMETRY  # noqa: E402
from tools.mining_rules.odd_types import MIN_OCCUPANTS  # noqa: E402
from tools.mining_rules.odd_values import (LOW_RECIPROCITY,  # noqa: E402
                                           MOSTLY_SINGLE, _lookalike_pair,
                                           _nested_pair, _stem)

OUT_DIR = ROOT / "dashboard" / "public" / "data"

parser = argparse.ArgumentParser()
parser.add_argument("--run", default=None, help="run file; default is newest")
parser.add_argument("--serve", action="store_true",
                    help="after exporting, start the Vite dev server")
parser.add_argument("--build", action="store_true",
                    help="after exporting, build the static dist/")
parser.add_argument("--single", action="store_true",
                    help="with --build: one self-contained HTML, data inlined")
args = parser.parse_args()

path = Path(args.run) if args.run else None
if path and not path.is_absolute():
    path = ROOT / path
if path is None:
    found = sorted(DATASET.RUNS.glob("run_*_observers.json"))
    if not found:
        raise SystemExit("no observation runs yet. Run scripts/3_run_observers.py first.")
    path = found[-1]

run = json.loads(path.read_text(encoding="utf-8"))
if run["status"] == "invalid":
    raise SystemExit(f"{path.name} is INVALID -- its blindness proof failed. "
                     "Nothing in it is worth showing.")

# Staleness binding (review finding): re-running 1_prepare_graph.py after a
# run would silently flip planted reveals and percentiles to wrong answers.
kg_hash = hashlib.sha256(DATASET.KG.read_bytes()).hexdigest()
run_hash = run.get("kg_sha256")
if run_hash and run_hash != kg_hash:
    raise SystemExit(f"STALE RUN: {path.name} was recorded against a "
                     f"different graph than the current {DATASET.KG.name}. "
                     "Re-run the observation, or restore that graph.")
if not run_hash:
    print(f"note: {path.name} predates graph-hash stamping -- cannot verify "
          "it matches the current prepared graph.")

ctx = get_context()

# ---- the answer key (evaluation-family privilege) --------------------------
truth = {}
for head, relation, tail, label, kind in (
        line.split("\t") for line in
        DATASET.TRUTH.read_text(encoding="utf-8").splitlines()):
    truth[(head, relation, tail)] = int(label)

# ---- whole-graph statistics the evidence panels draw from ------------------
present = set(ctx.triples)
by_relation = collections.defaultdict(list)
for triple in ctx.triples:
    by_relation[triple[1]].append(triple)

symmetry, reciprocity = {}, {}
for relation, triples in by_relation.items():
    mirrored = sum(1 for t in triples if (t[2], t[1], t[0]) in present)
    symmetry[relation] = mirrored / len(triples)
    reciprocity[relation] = symmetry[relation]

linked_by = collections.defaultdict(set)
tails_of = collections.defaultdict(list)
degree = collections.Counter()
for head, relation, tail in ctx.triples:
    degree[head] += 1
    degree[tail] += 1
    tails_of[(head, relation)].append(tail)
    if head != tail:
        key = (head, tail) if head < tail else (tail, head)
        linked_by[key].add(relation)

members = collections.defaultdict(list)
for entity in degree:
    for kind in ctx.entity_types.get(entity) or []:
        members[kind].append(entity)
peer_groups = {k: g for k, g in members.items() if len(g) >= MIN_PEERS}
median_of = {k: statistics.median(degree[e] for e in g)
             for k, g in peer_groups.items()}

scores = None
if DATASET.SCORES.exists() and DATASET.SCORES_MANIFEST.exists():
    manifest = json.loads(DATASET.SCORES_MANIFEST.read_text(encoding="utf-8"))
    if manifest["kg_sha256"] == kg_hash:
        scores = np.load(DATASET.SCORES)
        row_of = {triple: i for i, triple in enumerate(ctx.triples)}
        order = np.argsort(scores, kind="stable")
        rank_of = np.empty(len(scores), dtype=int)
        rank_of[order] = np.arange(len(scores))
    else:
        print("note: scores.npy is stale for this graph -- score evidence "
              "panels will be omitted.")


def _labels(triple):
    head, relation, tail = triple
    return {"h": ctx.entity_label(head), "r": ctx.relation_label(relation),
            "t": ctx.entity_label(tail)}


def _pair_edges(a, b):
    """Every edge between two entities, both directions, resolved."""
    edges = []
    for head, relation, tail in sorted(present):
        if {head, tail} == {a, b}:
            edges.append({"h": ctx.entity_label(head),
                          "r": ctx.relation_label(relation),
                          "t": ctx.entity_label(tail)})
    return edges


def _mirror_examples(relation, exclude):
    """Two mutual pairs of this relation, for contrast with the gap."""
    examples, seen = [], set()
    for head, rel, tail in sorted(by_relation[relation]):
        if head == tail or {head, tail} == set(exclude):
            continue
        pair = (head, tail) if head < tail else (tail, head)
        if pair in seen or (tail, rel, head) not in present:
            continue
        seen.add(pair)
        examples.append([ctx.entity_label(pair[0]), ctx.entity_label(pair[1])])
        if len(examples) == 2:
            break
    return examples


def _evidence(rule, triple, note=""):
    """The drawable form of the rule's argument for THIS triple.

    The served NOTE decides which case of a rule the panel illustrates
    (review finding: re-deriving the case can disagree with the note that
    actually won the rule's dedup -- note and diagram must argue the SAME
    suspicion). The note prefixes matched here are code-authored constants
    in the rule modules.
    """
    head, relation, tail = triple

    if rule == "odd_pairs":
        if note.startswith("links this entity to itself") or (
                not note and head == tail):
            loops = sum(1 for t in by_relation[relation] if t[0] == t[2])
            return {"type": "self", "loops": loops,
                    "total": len(by_relation[relation])}
        if note.startswith("recorded one way only") or (
                not note and (tail, relation, head) not in present
                and symmetry[relation] >= MIN_SYMMETRY):
            return {"type": "mirror", "symmetry": round(symmetry[relation], 2),
                    "examples": _mirror_examples(relation, (head, tail))}
        return {"type": "combo", "edges": _pair_edges(head, tail)}

    if rule == "odd_values":
        values = sorted(set(tails_of[(head, relation)]))
        heads = {h for h, r in tails_of if r == relation}
        single = sum(1 for h in heads
                     if len(set(tails_of[(h, relation)])) == 1)
        share = single / max(len(heads), 1)
        payload = {"type": "values", "head": ctx.entity_label(head),
                   "values": [ctx.entity_label(v) for v in values],
                   "single_share": round(share, 2), "kind": "extra"}
        if share < MOSTLY_SINGLE:
            # The rule's own helpers, in the rule's own order: all pairs
            # checked for nesting first, lookalikes only after.
            nested = _nested_pair(relation, values, linked_by, reciprocity)
            if nested:
                a, b, linker = nested
                payload.update(kind="nested",
                               pair=[ctx.entity_label(a), ctx.entity_label(b)],
                               link=ctx.relation_label(linker))
            else:
                lookalike = _lookalike_pair(values, ctx)
                if lookalike:
                    payload.update(kind="lookalike",
                                   pair=[ctx.entity_label(lookalike[0]),
                                         ctx.entity_label(lookalike[1])])
                else:
                    payload["kind"] = "many"
        return payload

    if rule == "odd_types":
        for slot, entity in (("head", head), ("tail", tail)):
            occupants = {t[0] if slot == "head" else t[2]
                         for t in by_relation[relation]}
            support = collections.Counter()
            for occupant in occupants:
                for kind in ctx.entity_types.get(occupant) or []:
                    support[kind] += 1
            kinds = ctx.entity_types.get(entity) or []
            if kinds and len(occupants) >= MIN_OCCUPANTS and \
                    max(support[k] - 1 for k in kinds) == 0:
                dominant = support.most_common(1)[0][0]
                sample = sorted(o for o in occupants if o != entity
                                and dominant in (ctx.entity_types.get(o) or []))
                return {"type": "types", "slot": slot, "kinds": kinds,
                        "usual": [[k, n] for k, n in support.most_common(3)],
                        "occupants": len(occupants),
                        "sample": [ctx.entity_label(s) for s in sample[:3]]}
        return {"type": "none"}

    if rule == "odd_degrees":
        # Reproduce the rule's own gates for this triple -- heavy is a
        # per-seat statistic, thin a whole-graph one (review finding: the
        # earlier "most extreme endpoint by whole-graph degree" could draw
        # the wrong entity's bars under the note).
        def _thin():
            for entity in (head, tail):
                kinds = [k for k in ctx.entity_types.get(entity) or []
                         if k in peer_groups]
                if not kinds:
                    continue
                kind = min(kinds, key=lambda k: len(peer_groups[k]))
                median = median_of[kind]
                if median >= SOLID_MEDIAN and degree[entity] * LOW_RATIO <= median:
                    return {"type": "degrees", "seat": False,
                            "entity": ctx.entity_label(entity),
                            "count": degree[entity], "median": round(median),
                            "kind": kind, "peers": len(peer_groups[kind]),
                            "tail_kind": "thin"}
            return None

        def _heavy():
            for slot, entity in (("head", head), ("tail", tail)):
                counts = collections.Counter(
                    t[0] if slot == "head" else t[2]
                    for t in by_relation[relation])
                count = counts[entity]
                best = None
                for kind in ctx.entity_types.get(entity) or []:
                    peers = [c for e, c in counts.items()
                             if kind in (ctx.entity_types.get(e) or [])]
                    if len(peers) < SLOT_MIN_PEERS:
                        continue
                    spread = sorted(peers)
                    median = spread[len(spread) // 2]
                    p99 = spread[int(0.99 * (len(spread) - 1))]
                    if (count >= HIGH_MIN and count >= HIGH_RATIO * median
                            and count > p99):
                        if best is None or len(peers) > best[0]:
                            best = (len(peers), median, kind)
                if best:
                    return {"type": "degrees", "seat": True,
                            "entity": ctx.entity_label(entity),
                            "count": count, "median": best[1],
                            "kind": best[2], "peers": best[0],
                            "tail_kind": "heavy"}
            return None

        checks = [_thin, _heavy] if "has only" in note else [_heavy, _thin]
        for check in checks:
            payload = check()
            if payload:
                return payload
        return {"type": "none"}

    if rule == "unlikely_facts" and scores is not None:
        row = row_of.get(triple)
        if row is not None:
            percentile = 100.0 * rank_of[row] / len(scores)
            return {"type": "score", "score": round(float(scores[row]), 3),
                    "percentile": round(max(percentile, 0.1), 1),
                    "total": len(scores)}
    return {"type": "none"}


def _handle(persona):
    """'You are a strict structural formalist and logical purist...' ->
    'The Structural Formalist'. Generic string surgery, no dataset words."""
    text = re.sub(r"^you are (a|an)\s+", "", (persona or "").strip(),
                  flags=re.IGNORECASE)
    text = re.split(r"[.]| who | and ", text)[0].replace(",", " ").strip()
    words = text.split()
    if not words:
        return "The Judge"
    if len(words) > 2:
        words = words[-2:]      # 'strict structural formalist' -> last two
    return "The " + " ".join(w.capitalize() for w in words)


# ---- assemble the cases ----------------------------------------------------
served_by = dict(zip(OBSERVER_NAMES, run["served"]))
verdicts_by = dict(zip(OBSERVER_NAMES, run["verdicts"]))

def _origins(triple):
    """Every (rule, note, observer) a real rule served this triple under.
    Both observers can reach one fact through DIFFERENT rules -- all
    origins are exported so the per-rule decks stay complete."""
    origins = []
    for name in OBSERVER_NAMES:
        for entry in served_by[name].values():
            if tuple(entry["triple"]) == triple and entry["rule"] != "second_opinion":
                origins.append({"rule": entry["rule"], "note": entry["note"],
                                "observer": name})
    return origins


case_of = {}
for name in OBSERVER_NAMES:
    for cid, v in verdicts_by[name].items():
        triple = tuple(v["triple"])
        case = case_of.setdefault(triple, {"cids": {}, "verdicts": {}})
        case["cids"][name] = cid
        case["verdicts"][name] = {"verdict": v["verdict"], "why": v["why"]}

cases = []
for triple, case in case_of.items():
    origins = _origins(triple) or [{"rule": "unknown", "note": "",
                                    "observer": ""}]
    rule, note = origins[0]["rule"], origins[0]["note"]
    via_review = {name: served_by[name].get(case["cids"].get(name, ""), {})
                  .get("rule") == "second_opinion" for name in case["cids"]}
    cases.append({
        "id": "-".join(triple),
        "cids": case["cids"],
        "triple": {"h": triple[0], "r": triple[1], "t": triple[2]},
        "labels": _labels(triple),
        "rule": rule,
        "note": note,
        "origins": origins,
        "via_second_opinion": via_review,
        "verdicts": case["verdicts"],
        "planted": truth.get(triple) == 1,
        "evidence": _evidence(rule, triple, note),
    })

# Stable, presentable order: cases judged by both observers first (the
# disagreement candidates), then by first candidate id.
def _sort_key(case):
    return (-len(case["verdicts"]), sorted(case["cids"].values())[0])

cases.sort(key=_sort_key)

flagged_by = {name: {c["id"] for c in cases
                     if c["verdicts"].get(name, {}).get("verdict") == "anomaly"}
              for name in OBSERVER_NAMES}
# A genuine split is one committed verdict against the other -- anomaly vs
# ok. An "unsure" judge has not taken a position and "out_of_scope" has
# declined to rule, so neither makes a norm disagreement (review finding).
disagreements = [c for c in cases
                 if {v["verdict"] for v in c["verdicts"].values()}
                 == {"anomaly", "ok"}]

judges = {}
for name, persona, norms, scope, rules in zip(
        OBSERVER_NAMES, run["personas"], run["norms"], run["scopes"],
        run["rules"]):
    judges[name] = {
        "handle": _handle((persona or {}).get("persona", "")),
        "persona": (persona or {}).get("persona", ""),
        "norms": norms or {},
        "scope_size": len((scope or {}).get("scope", [])),
        "rules_used": rules,
    }

view_model = {
    "run": path.stem,
    "dataset": run["dataset"],
    "card": run["card"],
    "status": run["status"],
    "generated": datetime.datetime.now().isoformat(timespec="seconds"),
    "stats": {
        "triples": len(ctx.triples),
        "entities": len(ctx.entities),
        "relations": len(ctx.relations),
        "planted_total": sum(truth.values()),
        "judged": len(cases),
        "flagged_union": len(set().union(*flagged_by.values())),
        "disagreements": len(disagreements),
        "caught": sum(1 for c in cases if c["planted"] and any(
            v["verdict"] == "anomaly" for v in c["verdicts"].values())),
    },
    "judges": judges,
    "blindness": run["blindness"],
    "cases": cases,
}

OUT_DIR.mkdir(parents=True, exist_ok=True)
out = OUT_DIR / f"{path.stem}.json"
out.write_text(json.dumps(view_model, indent=1), encoding="utf-8")

manifest_path = OUT_DIR / "manifest.json"
manifest = (json.loads(manifest_path.read_text(encoding="utf-8"))
            if manifest_path.exists() else [])
manifest = [m for m in manifest if m["file"] != out.name]
manifest.insert(0, {"file": out.name, "run": path.stem,
                    "dataset": run["dataset"],
                    "generated": view_model["generated"],
                    "cases": len(cases),
                    "disagreements": len(disagreements)})
manifest_path.write_text(json.dumps(manifest, indent=1), encoding="utf-8")

print(f"exported {len(cases)} cases ({len(disagreements)} disagreements, "
      f"{view_model['stats']['caught']} planted caught) -> "
      f"{out.relative_to(ROOT)}")

# ---- optional frontend runs ------------------------------------------------
if args.serve or args.build:
    import os  # noqa: E402
    import shutil  # noqa: E402
    import subprocess  # noqa: E402

    dashboard = ROOT / "dashboard"
    npm = shutil.which("npm")
    if npm is None:
        raise SystemExit("npm not found on PATH -- install Node.js first.")
    if not (dashboard / "node_modules").exists():
        print("installing frontend dependencies (first run only)...")
        subprocess.run([npm, "install"], cwd=dashboard, check=True)

    if args.serve:
        subprocess.run([npm, "run", "dev"], cwd=dashboard, check=True)
    else:
        env = dict(os.environ)
        if args.single:
            env["SINGLE"] = "1"
        subprocess.run([npm, "run", "build"], cwd=dashboard, check=True,
                       env=env)
        if args.single:
            # Inline the run data so the one file needs no server at all.
            index = dashboard / "dist" / "index.html"
            html = index.read_text(encoding="utf-8")
            payload = json.dumps(view_model).replace("</", "<\\/")
            html = html.replace(
                "<head>",
                f"<head><script>window.__DASHBOARD_DATA__ = {payload};"
                f"</script>", 1)
            single = dashboard / "dist" / f"dashboard_{path.stem}.html"
            single.write_text(html, encoding="utf-8")
            print(f"self-contained dashboard -> {single.relative_to(ROOT)}")
        else:
            print(f"static build -> {dashboard.relative_to(ROOT)}\\dist "
                  f"(serve it with any static server)")
