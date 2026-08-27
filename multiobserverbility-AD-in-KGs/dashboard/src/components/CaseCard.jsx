import { useState } from 'react'
import Evidence from '../evidence/Evidence.jsx'
import { isDisagreement, ruleName } from '../decks.js'

const VERDICT_LABEL = {
  anomaly: 'FLAGGED',
  ok: 'PASSED',
  unsure: 'UNSURE',
  out_of_scope: 'NOT MY DEPARTMENT',
}

export default function CaseCard({ data, deck, index, onPrev, onNext, onHome }) {
  const c = deck.cases[index]
  const split = isDisagreement(c)
  const judgeNames = Object.keys(data.judges)
  // Keyed by case id so navigating can never flash the NEXT case's answer
  // before an effect resets a stale boolean (review finding).
  const [revealedId, setRevealedId] = useState(null)
  const revealed = deck.spoiled || revealedId === c.id

  return (
    <div className="case-shell">
      <nav className="case-nav">
        <button onClick={onHome} className="ghost">&larr; overview</button>
        <span>
          {deck.title} &middot; case {index + 1} of {deck.cases.length}
        </span>
        <span className="rule-chip">found by {ruleName(c.rule)}</span>
      </nav>

      <article className={`case-card${split ? ' split' : ''}`}>
        <h1 className="fact">
          <span className="entity">{c.labels.h}</span>
          <span className="relation">{c.labels.r}</span>
          <span className="entity">{c.labels.t}</span>
        </h1>
        <p className="fact-ids">
          {c.triple.h} &middot; {c.triple.r} &middot; {c.triple.t}
        </p>

        <section className="suspicion">
          <h2>why the machine got suspicious</h2>
          {c.note && <p className="note">{c.note}</p>}
          <Evidence evidence={c.evidence} labels={c.labels} />
        </section>

        <section className="judges">
          {judgeNames.map((name, i) => {
            const judge = data.judges[name]
            const v = c.verdicts[name]
            return (
              <div key={name} className={`judge-panel judge-${i + 1}`}>
                <header>
                  <b>{judge.handle}</b>
                  {v ? (
                    <span className={`stamp stamp-${v.verdict}`}>
                      {VERDICT_LABEL[v.verdict] || v.verdict}
                    </span>
                  ) : (
                    <span className="stamp">NEVER SHOWN</span>
                  )}
                </header>
                {v && <p className="why">&ldquo;{v.why}&rdquo;</p>}
                {v && c.via_second_opinion[name] && (
                  <p className="via">reached this judge as a blind second
                  opinion &mdash; no hint of the other verdict</p>
                )}
              </div>
            )
          })}
        </section>
        {split && (
          <p className="split-banner">
            The judges split on this fact &mdash; and neither is wrong by
            their own rules. No answer key can settle a norm disagreement.
          </p>
        )}

        <section className="reveal">
          {!revealed ? (
            <button onClick={() => setRevealedId(c.id)}>
              Was this one of the planted fakes? Reveal
            </button>
          ) : c.planted ? (
            <p className="reveal-answer planted">
              PLANTED &mdash; one of the {data.stats.planted_total}
              {' '}verified-false facts hidden in the graph.
            </p>
          ) : (
            <p className="reveal-answer unplanted">
              NOT PLANTED &mdash; this fact came with the original data. A
              flag here can still be a real error the source carried, or a
              judgement the judge&rsquo;s norms demand.
            </p>
          )}
        </section>

        <footer className="provenance">
          {data.run} · {c.rule}
          {judgeNames
            .filter((n) => c.cids[n])
            .map((n) => ` · ${data.judges[n].handle}: ${c.cids[n]}`)
            .join('')}
        </footer>
      </article>

      <nav className="pager">
        <button onClick={onPrev} disabled={index === 0}>&larr; previous</button>
        <span className="pager-hint">&larr; &rarr; to page &middot; Esc for overview</span>
        <button onClick={onNext} disabled={index === deck.cases.length - 1}>
          next &rarr;
        </button>
      </nav>
    </div>
  )
}
