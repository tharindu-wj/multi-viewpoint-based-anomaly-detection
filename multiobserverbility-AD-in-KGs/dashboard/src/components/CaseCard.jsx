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
  const observerNames = Object.keys(data.observers)
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
        <span className="rule-chip">
          {(c.rules || []).length > 1
            ? `caught by ${c.rules.length} rules: ${c.rules.map(ruleName).join(' and ')}`
            : `found by ${ruleName(c.rule)}`}
        </span>
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

        <h2 className="observers-title">how each observer ruled</h2>
        <section className="observers">
          {observerNames.map((name, i) => {
            const observer = data.observers[name]
            const v = c.verdicts[name]
            // Same entity, two roles: the observer whose own rule turned this
            // fact up, and the one handed it blind afterwards.
            const reviewing = c.via_second_opinion[name]
            const origin = (c.origins || []).find((o) => o.observer === name)
            return (
              <div key={name} className={`observer-panel observer-${i + 1}`}>
                <header>
                  <b>{observer.handle}</b>
                  {v ? (
                    <span className={`stamp stamp-${v.verdict}`}>
                      {VERDICT_LABEL[v.verdict] || v.verdict}
                    </span>
                  ) : (
                    <span className="stamp">NEVER SHOWN</span>
                  )}
                </header>
                {v && (
                  <p className={`role ${reviewing ? 'role-reviewing' : 'role-primary'}`}>
                    <span className="role-tag">
                      {reviewing ? 'reviewing observer' : 'primary observer'}
                    </span>
                    <span className="role-note">
                      {reviewing
                        ? 'handed the bare fact afterwards — the primary observer’s verdict and reasons hidden'
                        : origin
                          ? `found it first: ${ruleName(origin.rule)} turned it up inside their own scope`
                          : 'found it first, inside their own scope'}
                    </span>
                  </p>
                )}
                {v && <p className="why">&ldquo;{v.why}&rdquo;</p>}
              </div>
            )
          })}
        </section>
        {split && (
          <p className="split-banner">
            The two observers split on this fact &mdash; and neither is wrong
            by their own norms. No answer key can settle a disagreement about
            what counts as an anomaly.
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
              judgement the observer&rsquo;s norms demand.
            </p>
          )}
        </section>

        <footer className="provenance">
          {data.run} · {c.rule}
          {observerNames
            .filter((n) => c.cids[n])
            .map((n) => ` · ${data.observers[n].handle}: ${c.cids[n]}`)
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
