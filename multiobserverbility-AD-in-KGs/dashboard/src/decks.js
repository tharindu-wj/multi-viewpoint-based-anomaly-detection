// Deck definitions -- pure filters over the exported cases array.
// The frontend never computes graph statistics; it only groups what the
// exporter already established.

// Viewer-facing names for internal rule ids. Snake_case identifiers must
// never reach a non-technical viewer; the raw ids stay in the provenance
// footer for traceability.
export const RULE_NAMES = {
  odd_pairs: 'the odd-pairings rule',
  odd_types: 'the odd-types rule',
  odd_values: 'the odd-values rule',
  odd_degrees: 'the odd-record-counts rule',
  unlikely_facts: 'the implausibility score',
  second_opinion: 'cross-review',
  unknown: 'cross-review',
}
export const ruleName = (rule) => RULE_NAMES[rule] || rule

// A genuine split is one committed verdict against the other. An "unsure"
// judge has not taken a position and "out_of_scope" has declined to rule,
// so neither makes a norm disagreement.
export const isDisagreement = (c) => {
  const verdicts = Object.values(c.verdicts).map((v) => v.verdict)
  return (
    verdicts.length === 2 &&
    verdicts.includes('anomaly') &&
    verdicts.includes('ok')
  )
}

export const isAgreedAnomaly = (c) =>
  Object.keys(c.verdicts).length === 2 &&
  Object.values(c.verdicts).every((v) => v.verdict === 'anomaly')

export const isCaught = (c) =>
  c.planted && Object.values(c.verdicts).some((v) => v.verdict === 'anomaly')

const caseRules = (c) => (c.origins || []).map((o) => o.rule)

// Decks are overlapping VIEWS of one docket, never disjoint bins -- the
// same fact sits in several. Each deck carries a `dimension` so the
// overview can group them into labeled slices and show counts as
// "n of <total>", and the dot strip can light up membership on hover.
export function buildDecks(cases) {
  const decks = [
    {
      key: 'all',
      dimension: 'all',
      title: 'Every judged fact',
      blurb: 'The full docket, including the ones that passed.',
      cases,
    },
    {
      key: 'disagree',
      dimension: 'verdict',
      title: 'Where the judges disagree',
      blurb:
        'The same fact, two verdicts -- both right by their own rules. ' +
        'This is what the architecture exists to surface.',
      cases: cases.filter(isDisagreement),
    },
    {
      key: 'agreed',
      dimension: 'verdict',
      title: 'Where both agree it is wrong',
      blurb: 'Flagged by both judges, each for their own reason.',
      cases: cases.filter(isAgreedAnomaly),
    },
    {
      key: 'caught',
      dimension: 'outcome',
      title: 'Caught fakes',
      blurb:
        'Every card here is a planted falsehood a judge flagged -- ' +
        'so these cards arrive already revealed.',
      // Membership is defined by planted status, so the guess-then-reveal
      // would be dead on arrival -- CaseCard shows these pre-revealed.
      spoiled: true,
      cases: cases.filter(isCaught),
    },
  ]
  const rules = [...new Set(cases.flatMap(caseRules))].sort()
  for (const rule of rules) {
    if (rule === 'unknown') continue
    decks.push({
      key: `rule:${rule}`,
      dimension: 'rule',
      title: `Found by ${ruleName(rule)}`,
      blurb: 'All judged facts this mining rule surfaced.',
      cases: cases.filter((c) => caseRules(c).includes(rule)),
      minor: true,
    })
  }
  return decks.filter((d) => d.cases.length > 0)
}
