// One renderer per evidence type -- the drawable form of each mining rule's
// argument. All payloads are precomputed by scripts/5_export_dashboard.py;
// nothing here touches the graph. HTML/CSS pills and arrows rather than
// absolute SVG, so long real-world labels wrap instead of overflowing.

export default function Evidence({ evidence, labels }) {
  const Renderer = REGISTRY[evidence.type] || None
  return (
    <div className="evidence">
      <Renderer e={evidence} labels={labels} />
    </div>
  )
}

function Mirror({ e, labels }) {
  return (
    <div>
      <div className="edge-row">
        <span className="pill">{labels.h}</span>
        <span className="arrow solid">
          <i>{labels.r}</i>&nbsp;&#10230;
        </span>
        <span className="pill">{labels.t}</span>
      </div>
      <div className="edge-row ghost-row">
        <span className="pill faint">{labels.t}</span>
        <span className="arrow ghost">
          <i>never recorded</i>&nbsp;&#8674;
        </span>
        <span className="pill faint">{labels.h}</span>
      </div>
      <p className="evidence-caption">
        {Math.round(e.symmetry * 100)}% of &ldquo;{labels.r}&rdquo; records go
        both ways
        {e.examples.length > 0 && (
          <>
            {' '}&mdash; like{' '}
            {e.examples.map((pair, i) => (
              <span key={i} className="example-pair">
                {pair[0]} &#8644; {pair[1]}
                {i < e.examples.length - 1 ? ', ' : ''}
              </span>
            ))}
          </>
        )}
        . This one was written down on one side only.
      </p>
    </div>
  )
}

function Combo({ e }) {
  return (
    <div>
      {e.edges.map((edge, i) => (
        <div key={i} className="edge-row">
          <span className="pill">{edge.h}</span>
          <span className="arrow solid">
            <i>{edge.r}</i>&nbsp;&#10230;
          </span>
          <span className="pill">{edge.t}</span>
        </div>
      ))}
      <p className="evidence-caption">
        The same two entities, linked {e.edges.length} different ways.
      </p>
    </div>
  )
}

function Self({ e, labels }) {
  return (
    <div>
      <div className="edge-row">
        <span className="pill">{labels.h}</span>
        <span className="arrow solid">
          <i>{labels.r}</i>&nbsp;&#8635;
        </span>
        <span className="pill">itself</span>
      </div>
      <p className="evidence-caption">
        Only {e.loops} of {e.total} records of this relation link a thing to
        itself.
      </p>
    </div>
  )
}

function Values({ e, labels }) {
  const highlighted = new Set(e.pair || [])
  return (
    <div>
      <div className="values-fan">
        <span className="pill">{e.head}</span>
        <span className="arrow solid">
          <i>{labels.r}</i>&nbsp;&#10230;
        </span>
        <span className="value-list">
          {e.values.map((v, i) => (
            <span
              key={i}
              className={`pill${highlighted.has(v) ? ' hot' : ' faint'}`}
            >
              {v}
            </span>
          ))}
        </span>
      </div>
      <p className="evidence-caption">
        {e.kind === 'extra' && (
          <>
            {Math.round(e.single_share * 100)}% of entities hold exactly ONE
            value here &mdash; this one holds {e.values.length}.
          </>
        )}
        {e.kind === 'many' && (
          <>This entity holds {e.values.length} values here &mdash; the set
          itself is what drew attention.</>
        )}
        {e.kind === 'nested' && (
          <>
            The graph itself records &ldquo;{e.pair[0]}&rdquo;
            &mdash;{e.link}&mdash; &ldquo;{e.pair[1]}&rdquo;, so one value may
            contain the other.
          </>
        )}
        {e.kind === 'lookalike' && (
          <>
            &ldquo;{e.pair[0]}&rdquo; and &ldquo;{e.pair[1]}&rdquo; differ
            only by a trailing qualifier &mdash; possibly one thing recorded
            twice.
          </>
        )}
      </p>
    </div>
  )
}

function Types({ e, labels }) {
  if (!e.occupants) return <None />
  const seat = e.slot === 'head' ? labels.h : labels.t
  return (
    <div>
      <div className="type-row">
        {e.usual.map(([kind, count]) => (
          <span key={kind} className="pill faint">
            {kind} &times;{count}
          </span>
        ))}
        <span className="pill hot">
          {seat}: {e.kinds.join(', ') || 'untyped'}
        </span>
      </div>
      <p className="evidence-caption">
        Of {e.occupants} entities in this seat
        {e.sample.length > 0 && <> (such as {e.sample.join(', ')})</>}, none
        shares a kind with this one.
      </p>
    </div>
  )
}

function Degrees({ e }) {
  if (!e.peers) return <None />
  const max = Math.max(e.count, e.median, 1)
  const where = e.seat ? 'in this seat' : 'in the whole graph'
  return (
    <div>
      <div className="bar-row">
        <small>typical {e.kind}{e.seat ? ' here' : ''}</small>
        <div className="bar faint" style={{ width: `${(e.median / max) * 100}%` }} />
        <b>{e.median}</b>
      </div>
      <div className="bar-row">
        <small>{e.entity}</small>
        <div className="bar hot" style={{ width: `${(e.count / max) * 100}%` }} />
        <b>{e.count}</b>
      </div>
      <p className="evidence-caption">
        {e.tail_kind === 'heavy'
          ? `Far more records ${where} than the ${e.peers} same-kind entities usually hold.`
          : `Far fewer records ${where} than the ${e.peers} same-kind entities usually hold.`}
      </p>
    </div>
  )
}

function Score({ e }) {
  return (
    <div>
      <div className="score-track">
        <div
          className="score-marker"
          style={{ left: `${Math.min(Math.max(e.percentile, 1.5), 98.5)}%` }}
        />
        <span className="track-label left">least plausible</span>
        <span className="track-label right">most plausible</span>
      </div>
      <p className="evidence-caption">
        A model trained on this graph ranked this fact among its least
        plausible {e.percentile}% of {e.total.toLocaleString()} &mdash;
        surprise, not proof: rare-but-true facts surprise it too.
      </p>
    </div>
  )
}

function None() {
  return (
    <p className="evidence-caption">
      Surfaced for judgement without a statistical exhibit.
    </p>
  )
}

const REGISTRY = {
  mirror: Mirror,
  combo: Combo,
  self: Self,
  values: Values,
  types: Types,
  degrees: Degrees,
  score: Score,
  none: None,
}
