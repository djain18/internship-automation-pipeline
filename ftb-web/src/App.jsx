// ============================================================
// DISPATCH — App shell: nav, clock, routing, GSAP transitions.
// React best-practices applied:
//  - Promise.all for parallel data fetching
//  - toSorted() for immutable sort
//  - useCallback for all passed callbacks
//  - explicit ternary conditional rendering (no &&)
// ============================================================
import { useState, useEffect, useCallback, useRef } from 'react'
import { gsap } from 'gsap'

import { Cursor, Icon, Wordmark, useReducedMotion } from './components/core.jsx'
import { Masthead, Process, Spike } from './components/home.jsx'
import { Selections, DropTeaser, Letters, Notes, Colophon, Footer, Detail } from './components/home2.jsx'
import Board from './components/board.jsx'
import DailyDrop from './components/drop.jsx'
import Subscribe from './components/subscribe.jsx'

import { EDITION, LISTINGS } from './lib/data.js'
import { fetchListings, fetchStats } from './lib/api.js'

// ── Live IST clock ────────────────────────────────────────────
function LiveClock() {
  const [now, setNow] = useState(new Date())
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000)
    return () => clearInterval(id)
  }, [])
  const ist = new Date(now.toLocaleString('en-US', { timeZone: 'Asia/Kolkata' }))
  const p = (x) => String(x).padStart(2, '0')
  return (
    <span className="dk-clock">
      {p(ist.getHours())}:{p(ist.getMinutes())}<i>:{p(ist.getSeconds())}</i> IST
    </span>
  )
}

const NAV_ITEMS = [
  { id: 'home',  label: 'Front Page'  },
  { id: 'index', label: 'The Index'   },
  { id: 'drop',  label: 'Daily Drop'  },
]

// ── Nav ───────────────────────────────────────────────────────
function Nav({ view, go }) {
  const [open, setOpen] = useState(false)
  const close = useCallback(() => setOpen(false), [])
  return (
    <nav className="dk-nav">
      <div className="dk-wrap dk-nav-inner">
        <Wordmark scale={0.62} onClick={() => go('home')} />
        <div className="dk-nav-links">
          {NAV_ITEMS.map(n => (
            <button key={n.id} className={'dk-nav-link ' + (view === n.id ? 'on' : '')} onClick={() => go(n.id)}>
              {n.label}
            </button>
          ))}
        </div>
        <div className="dk-nav-right">
          <LiveClock />
          <button className="dk-btn dk-btn-red dk-btn-sm dk-btn-magnetic" onClick={() => go('subscribe')}>
            Subscribe
          </button>
          <button className="dk-nav-burger" aria-label={open ? 'Close menu' : 'Open menu'} onClick={() => setOpen(o => !o)}>
            <Icon d={open ? 'x' : 'menu'} size={18} />
          </button>
        </div>
      </div>
      {open ? (
        <div className="dk-nav-mobile">
          {NAV_ITEMS.map(n => (
            <button key={n.id} className={view === n.id ? 'on' : ''} onClick={() => { go(n.id); close() }}>
              {n.label}
            </button>
          ))}
          <button className="dk-btn dk-btn-red dk-btn-block" onClick={() => { go('subscribe'); close() }}>
            Subscribe
          </button>
        </div>
      ) : null}
    </nav>
  )
}

// ── App ───────────────────────────────────────────────────────
export default function App() {
  const reduced = useReducedMotion()
  const [view, setView] = useState('home')
  const [detail, setDetail] = useState(null)
  const [saved, setSaved] = useState([])
  const [pressed, setPressed] = useState(reduced)
  const [listings, setListings] = useState(LISTINGS)
  const [edition, setEdition] = useState(EDITION)
  const pageRef = useRef(null)

  // Masthead "going to press" trigger
  useEffect(() => {
    if (reduced) { setPressed(true); return }
    const r = requestAnimationFrame(() => requestAnimationFrame(() => setPressed(true)))
    const t = setTimeout(() => setPressed(true), 1400)
    return () => { cancelAnimationFrame(r); clearTimeout(t) }
  }, [reduced])

  // Parallel data fetch — falls back silently to seed data
  useEffect(() => {
    Promise.all([
      fetchListings().catch(() => null),
      fetchStats().catch(() => null),
    ]).then(([data, stats]) => {
      if (Array.isArray(data) && data.length > 0) setListings(data)
      if (stats && stats.verifiedToday) setEdition(e => ({ ...e, ...stats }))
    })
  }, [])

  // GSAP page transition (fade + translate)
  const go = useCallback((v) => {
    if (v === view) return
    if (!reduced && pageRef.current) {
      gsap.to(pageRef.current, {
        opacity: 0, y: -6, duration: .2, ease: 'power2.in',
        onComplete: () => {
          setView(v)
          window.scrollTo(0, 0)
          gsap.fromTo(
            pageRef.current,
            { opacity: 0, y: 10 },
            { opacity: 1, y: 0, duration: .42, ease: 'power2.out' }
          )
        },
      })
    } else {
      setView(v)
      window.scrollTo(0, 0)
    }
  }, [view, reduced])

  const onSave = useCallback((id) => {
    setSaved(s => s.includes(id) ? s.filter(x => x !== id) : [...s, id])
  }, [])

  // Immutable sort (React best practice: toSorted)
  const topListings = listings.toSorted ? listings.toSorted((a, b) => b.score - a.score)
                                         : [...listings].sort((a, b) => b.score - a.score)

  return (
    <div className="dk-root">
      {reduced ? null : <Cursor />}
      <Nav view={view} go={go} />

      <div ref={pageRef} className="dk-page">
        {view === 'home' ? (
          <main>
            <Masthead go={go} reduced={reduced} pressed={pressed} edition={edition} />
            <Process reduced={reduced} />
            <Spike listings={topListings} edition={edition} />
            <Selections listings={topListings} onOpen={setDetail} saved={saved} onSave={onSave} go={go} edition={edition} />
            <DropTeaser listings={topListings} go={go} />
            <Letters />
            <Notes />
            <Colophon go={go} />
          </main>
        ) : null}

        {view === 'index' ? (
          <main>
            <Board listings={listings} onOpen={setDetail} saved={saved} onSave={onSave} />
          </main>
        ) : null}

        {view === 'drop' ? (
          <main>
            <DailyDrop listings={topListings} edition={edition} go={go} />
          </main>
        ) : null}

        {view === 'subscribe' ? (
          <main>
            <Subscribe onDone={w => go(w)} />
          </main>
        ) : null}

        {view !== 'subscribe' ? <Footer go={go} /> : null}
      </div>

      {detail ? (
        <Detail
          data={detail}
          listings={listings}
          onClose={() => setDetail(null)}
          saved={saved.includes(detail.id)}
          onSave={onSave}
          onOpenOther={r => setDetail(r)}
        />
      ) : null}
    </div>
  )
}
