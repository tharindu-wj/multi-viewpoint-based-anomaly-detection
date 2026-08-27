import { useEffect, useState, useCallback } from 'react'
import Overview from './components/Overview.jsx'
import CaseCard from './components/CaseCard.jsx'
import { buildDecks } from './decks.js'

// Data arrives one of two ways: injected by the exporter's --single build
// (window.__DASHBOARD_DATA__), or fetched from public/data/ in dev and in
// the normal static build.
async function loadData() {
  if (window.__DASHBOARD_DATA__) return window.__DASHBOARD_DATA__
  const manifest = await (await fetch('./data/manifest.json')).json()
  if (!manifest.length) throw new Error('no exported runs in data/')
  const run = await (await fetch(`./data/${manifest[0].file}`)).json()
  return run
}

export default function App() {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [deckKey, setDeckKey] = useState(null) // null -> overview
  const [index, setIndex] = useState(0)

  useEffect(() => {
    loadData().then(setData, (e) => setError(String(e)))
  }, [])

  const decks = data ? buildDecks(data.cases) : []
  const deck = decks.find((d) => d.key === deckKey) || null

  const goHome = useCallback(() => setDeckKey(null), [])
  const openDeck = useCallback((key) => {
    setDeckKey(key)
    setIndex(0)
  }, [])

  useEffect(() => {
    function onKey(e) {
      if (!deck) return
      if (e.key === 'ArrowRight')
        setIndex((i) => Math.min(i + 1, deck.cases.length - 1))
      if (e.key === 'ArrowLeft') setIndex((i) => Math.max(i - 1, 0))
      if (e.key === 'Escape') goHome()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [deck, goHome])

  if (error)
    return (
      <div className="shell">
        <p className="loading">
          Could not load run data: {error}. Run
          scripts/5_export_dashboard.py first.
        </p>
      </div>
    )
  if (!data) return <div className="shell"><p className="loading">loading…</p></div>

  return (
    <div className="shell">
      {!deck && <Overview data={data} decks={decks} onOpenDeck={openDeck} />}
      {deck && (
        <CaseCard
          data={data}
          deck={deck}
          index={Math.min(index, deck.cases.length - 1)}
          onPrev={() => setIndex((i) => Math.max(i - 1, 0))}
          onNext={() => setIndex((i) => Math.min(i + 1, deck.cases.length - 1))}
          onHome={goHome}
        />
      )}
    </div>
  )
}
