// The 30-second setup screen: what happened, who the judges are, and the
// decks. Everything on it is quoted from the run -- personas, norms and
// every number come from the loaded data, never from literals here.

import { useState } from 'react'
import { ruleName } from '../decks.js'

//: how the deck slices are introduced. Decks overlap by design; the
//: grouping and the "n of total" chips are what make that legible.
const DIMENSION_LABELS = {
  verdict: 'the same facts, sliced by how the judges ruled',
  outcome: 'sliced by what they turned out to be',
  rule: 'sliced by which mining rule surfaced them',
}
const DIMENSION_ORDER = ['all', 'verdict', 'outcome', 'rule']

const pipelineSteps = (s) => [
  ['plant', `${s.planted_total.toLocaleString()} verified-false facts are hidden in the graph`],
  ['mine', `deterministic rules sweep all ${s.triples.toLocaleString()} facts for suspects`],
  ['judge blind', 'two judges declare their norms before seeing any data, then rule on the suspects their own rules surface'],
  ['compare', 'each blindly reviews the other’s flags -- agreement and disagreement are both results'],
]

export default function Overview({ data, decks, onOpenDeck }) {
  const s = data.stats
  const judgeNames = Object.keys(data.judges)
  const blindnessVerified = data.blindness.every((b) => b.verified)
  // Hovering (or focusing) a deck lights up exactly the docket dots it
  // holds -- the overlap between decks becomes visible, not explained.
  const [hoverKey, setHoverKey] = useState(null)
  const hovered = decks.find((d) => d.key === hoverKey)
  const lit = hovered ? new Set(hovered.cases.map((c) => c.id)) : null
  return (
    <div className="overview">
      <header>
        <p className="eyebrow">{data.dataset} &middot; {data.run}</p>
        <h1>Two judges, one graph</h1>
        <p className="lede">{data.card} We hid {s.planted_total} facts known
        to be false among {s.triples.toLocaleString()} records, then asked
        two AI judges with different worldviews to find what is wrong &mdash;
        each by their own rules.</p>
      </header>

      <div className="pipeline">
        {pipelineSteps(s).map(([step, text], i) => (
          <div key={step} className="pipeline-step">
            <span className="step-number">{i + 1}</span>
            <b>{step}</b>
            <small>{text}</small>
          </div>
        ))}
      </div>

      <div className="stat-row">
        <Stat n={s.triples.toLocaleString()} label="facts in the graph" />
        <Stat n={s.judged} label="facts judged" />
        <Stat n={s.flagged_union} label="flagged by a judge" />
        <Stat n={s.disagreements} label="split verdicts" accent />
      </div>

      <div className="judge-intro-row">
        {judgeNames.map((name, i) => {
          const j = data.judges[name]
          return (
            <section key={name} className={`judge-intro judge-${i + 1}`}>
              <h2>{j.handle}</h2>
              <p className="persona">&ldquo;{j.persona}&rdquo;</p>
              <dl>
                <dt>calls anomalous</dt>
                <dd>{j.norms.anomalous}</dd>
                <dt>lets pass</dt>
                <dd>{j.norms.lets_pass}</dd>
              </dl>
              <p className="judge-meta">
                watches {j.scope_size} of {s.relations} relations &middot;
                hunts with{' '}
                {Object.keys(j.rules_used).map(ruleName).join(', ') || '—'}
              </p>
            </section>
          )
        })}
      </div>

      <h2 className="decks-title">The case files</h2>
      <p className="decks-sub">
        One docket of {s.judged} judged facts, opened from different sides
        &mdash; the same fact can sit in several files. Hover a file to
        light up the facts it holds.
      </p>
      <div className="dot-strip" aria-hidden="true">
        {data.cases.map((c) => (
          <span
            key={c.id}
            className={`dot${!lit || lit.has(c.id) ? ' on' : ''}`}
          />
        ))}
      </div>
      {DIMENSION_ORDER.map((dim) => {
        const slice = decks.filter((d) => d.dimension === dim)
        if (!slice.length) return null
        return (
          <div key={dim} className="deck-dim">
            {DIMENSION_LABELS[dim] && (
              <p className="deck-dim-label">{DIMENSION_LABELS[dim]}</p>
            )}
            <div className="deck-grid">
              {slice.map((d) => (
                <button
                  key={d.key}
                  className={`deck-button${d.minor ? ' minor' : ''}`}
                  onClick={() => onOpenDeck(d.key)}
                  onMouseEnter={() => setHoverKey(d.key)}
                  onMouseLeave={() => setHoverKey(null)}
                  onFocus={() => setHoverKey(d.key)}
                  onBlur={() => setHoverKey(null)}
                >
                  <b>{d.title}</b>
                  <span className="deck-count">
                    {d.dimension === 'all'
                      ? d.cases.length
                      : `${d.cases.length} of ${s.judged}`}
                  </span>
                  {!d.minor && <small>{d.blurb}</small>}
                </button>
              ))}
            </div>
          </div>
        )
      })}

      <footer className="fine-print">
        {blindnessVerified
          ? 'Norms were declared before either judge saw any data (verified from the run trace). '
          : 'Blindness could not be verified for this run -- treat the norms with care. '}
        Verdicts come from the run file; planted status from the withheld
        answer key, revealed per case on request.
      </footer>
    </div>
  )
}

function Stat({ n, label, accent }) {
  return (
    <div className={`stat${accent ? ' accent' : ''}`}>
      <b>{n}</b>
      <small>{label}</small>
    </div>
  )
}
