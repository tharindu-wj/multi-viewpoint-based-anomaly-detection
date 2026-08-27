# Multi-viewpoint anomaly detection in knowledge graphs

Research workspace for a thesis on **anomaly detection as a property of the
standpoint**: instead of one detector deciding what is wrong in a knowledge
graph, several observers with different norms judge the same facts and are
allowed to disagree. What they disagree about is the result, not a failure.

The work is split across three repositories that stay independent and talk to
each other only through files:

| project | question it answers | repository |
|---|---|---|
| **KGSAGE** | What does a *hard* false fact look like? Trains an adversarial generator that corrupts real triples into plausible-but-false ones. | [tharindu-wj/KGSAGE](https://github.com/tharindu-wj/KGSAGE) |
| **ADKGD** | Which triples look anomalous to a single model? A dual-channel detector (triplet view + entity view) that ranks triples by how much its two views disagree. | [tharindu-wj/ADKGD](https://github.com/tharindu-wj/ADKGD) |
| **Multiobserverbility** | Do different observers see the *same* anomalies? Agentic framework where observers form norms blind, then judge suspects that scanners surface. | *placeholder — see below* |

This repository is the **workspace root**: it holds the multiobserverbility
framework, the orchestration that runs the three together, and nothing that a
script can regenerate.

---

## Getting started

Clone the workspace, then the sibling projects **into it**. They are ignored by
this repository's `.gitignore`, so they stay separate repositories with their
own history — you commit to each one on its own.

```bash
git clone https://github.com/tharindu-wj/multi-viewpoint-based-anomaly-detection.git
cd multi-viewpoint-based-anomaly-detection

git clone https://github.com/tharindu-wj/ADKGD.git   ADKGD
git clone https://github.com/tharindu-wj/KGSAGE.git  KGSAGE

# PLACEHOLDER -- the multiobserverbility framework is not a separate repository
# yet; it currently lives in this workspace at multiobserverbility-AD-in-KGs/.
# When it is split out, replace that folder with:
#
#   git clone https://github.com/tharindu-wj/<MULTIOBSERVERBILITY-REPO>.git \
#       multiobserverbility-AD-in-KGs
#
# Nothing else changes: the three projects only ever exchange files.
```

Expected layout once cloned:

```
multi-viewpoint-based-anomaly-detection/
├── ADKGD/                          cloned, not tracked here
├── KGSAGE/                         cloned, not tracked here
├── multiobserverbility-AD-in-KGs/  tracked here (for now)
├── multiviewpoint-AD-in-KGs/       predecessor, kept for reference
├── multi-observerbility-AD/        predecessor, kept for reference
└── README.md
```

### Datasets are not in the clones

None of the three repositories ship their graph data — it is gitignored
everywhere. Before a first run, place the splits yourself:

- `ADKGD/data/<dataset>/{train,valid,test}.txt`
- `KGSAGE/data/<dataset>/{train,valid,test}.txt` (plus `entity2text.txt` if
  you want readable corruption CSVs — without it the exporter writes an empty
  file and says so)
- `multiobserverbility-AD-in-KGs/data/` **is** tracked, so CoDEx-S is already
  there; nothing to fetch.

Each file is tab-separated `head<TAB>relation<TAB>tail`.

### API key

Only the observer run calls a model. Copy `.env.example` to `.env` in the
workspace root and fill in a Gemini key; the runner also accepts one from the
environment.

---

## Environments

Two interpreters, because the stacks do not overlap:

| environment | needs | used by |
|---|---|---|
| **agent env** | `google-adk`, `google-genai`, `pykeen`, `torch`, `numpy` | multiobserverbility (all four steps) |
| **torch env** | `torch`, `numpy`, `scikit-learn`; `torch-geometric` for KGSAGE training only | ADKGD, KGSAGE |

On the development machine these are conda's base env and the `pytorch` env
respectively. Do not `pip install -r` ADKGD's `reqirements.txt` — it pins
torch 1.7 / numpy 1.19 and the code has since been ported to torch 2.8 and
NumPy 2.x.

---

## Running the pieces

Each project documents itself; this is the map.

**Multiobserverbility** — four steps, in order, from
`multiobserverbility-AD-in-KGs/`:

```bash
python scripts/1_prepare_graph.py     # merge the graph, plant verified-false triples
python scripts/2_train_scorer.py      # train a scorer, write one score per triple
python scripts/3_run_observers.py     # the only step that calls the model
python scripts/4_evaluate_verdicts.py # score the verdicts against the answer key
```

Steps 1 and 2 write into `prepared/`, which is gitignored — a fresh clone has
no graph and no scores, so run them before anything else. Re-running step 1
invalidates the scores (they are bound to the graph by hash), so re-run step 2
after it. The offline probes `check_context.py`, `check_gate.py` and
`check_scanners.py` need no key and no model.

**KGSAGE** — train a generator, choose a snapshot, export corruptions. See its
README; the short version is `python -m kgsage.gan.train`, then
`kgsage.cli.knockout_eval` to pick the snapshot (lowest mean J@10, not the last
epoch), then `kgsage.cli.gen_corruptions_csv`.

**ADKGD** — `experiments/run_experiment.py` is the harness; it runs train and
test and prints the metrics. The raw `Our_TopK%_RankingList.py` does one mode
per invocation and needs `checkpoints/<dataset>/` to exist first.

---

## How the three connect

Only through files. No project imports another, and each can be run, changed
or published on its own.

```
KGSAGE ──── generator checkpoint (.pt) ────► ADKGD
             copied into artifacts/kgsage/, consumed via --neg_source gan
             so the detector trains against hard negatives instead of
             random corruptions

ADKGD ───── per-triple scores ─────────────► Multiobserverbility
             one score per graph row, written to prepared/, read by the
             unlikely_facts scanner as a plain array lookup

Multiobserverbility ── shortlist ──► observers ──► verdicts ──► disagreement set
```

The last hop is the point of the thesis: a detector produces a *ranking*, and
observers with different norms turn that ranking into judgements that need not
agree. Running ADKGD inside the framework and standalone on the same graph
isolates what the framework adds.

*Status: KGSAGE → ADKGD is wired (`experiments/kgsage_bridge`). ADKGD →
multiobserverbility is designed but not yet built; the framework currently
scores with its own DistMult, behind the same file contract ADKGD will use.*

---

## Running on HPC

Clone all three into one directory as above and submit per stage. Two things
to plan around:

- **Compute nodes usually have no outbound internet.** Training and scoring
  belong on the nodes; the observer run calls the Gemini API, so run it from a
  login node or locally against score files the nodes produced. The file-based
  seam is what makes that split possible.
- **Do not carry `OMP_NUM_THREADS=1` onto the cluster.** It is a local Windows
  segfault workaround; the SLURM scripts set thread counts from
  `$SLURM_CPUS_PER_TASK` instead.
