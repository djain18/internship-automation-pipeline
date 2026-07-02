// ============================================================
// DISPATCH — The Index (board). GSAP stagger reveal on rows.
// React best practices: useMemo for filtered rows, useCallback,
// content-visibility on the row list for long lists.
// ============================================================
import { useState, useMemo, useRef, useEffect, useCallback } from 'react'
import { gsap } from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'

import {
  Icon, Label, Stamp, Grade, rupee, freshWord, useReducedMotion,
} from './core.jsx'
import { ROLE_CLUSTERS, CITIES } from '../lib/data.js'

gsap.registerPlugin(ScrollTrigger)

// ── Shared listing row ────────────────────────────────────────
export function ListingRow({ data, onOpen, saved, onSave, i, on }) {
  return (
    <button
      className={'dk-row ' + (on ? 'on' : '')}
      style={{ '--i': Math.min(i, 14) }}
      onClick={() => onOpen(data)}
    >
      <span className="dk-row-no">{String(i + 1).padStart(2, '0')}</span>
      <span className="dk-row-role">
        <span className="dk-row-title">
          <span className="dk-row-titletext">{data.title}</span>
          <Stamp small />
        </span>
        <span className="dk-row-org">
          {data.org} <i>·</i> <span className="dk-row-field">{data.cluster}</span>
        </span>
      </span>
      <span className="dk-row-loc">
        <span className="dk-row-type">{data.type}</span>
        {data.location}
      </span>
      <span className="dk-row-stipend">
        {rupee(data.stipend)}<i>{data.stipend ? '/mo' : ''}</i>
      </span>
      <span className="dk-row-fresh">{freshWord(data.hoursAgo)}</span>
      <span className="dk-row-grade"><Grade score={data.score} /></span>
      <span
        role="button"
        tabIndex={0}
        className={'dk-row-save ' + (saved ? 'is-saved' : '')}
        onClick={e => { e.stopPropagation(); onSave(data.id) }}
        onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); e.stopPropagation(); onSave(data.id) } }}
        aria-label={saved ? 'Clip removed' : 'Clip this listing'}
      >
        <Icon d="book" size={15} style={{ fill: saved ? 'var(--red)' : 'none' }} />
      </span>
    </button>
  )
}

export function IndexHead() {
  return (
    <div className="dk-row dk-row-head" aria-hidden="true">
      <span className="dk-row-no">№</span>
      <Label>Role · Organisation</Label>
      <Label>Type · Location</Label>
      <Label>Stipend</Label>
      <Label>Filed</Label>
      <Label>Grade</Label>
      <span />
    </div>
  )
}

// ── Labelled select ───────────────────────────────────────────
function Sel({ label, value, onChange, opts }) {
  return (
    <label className="dk-select">
      <Label style={{ color: 'var(--ink-70)' }}>{label}</Label>
      <div className="dk-select-box">
        <select value={value} onChange={e => onChange(e.target.value)}>
          {opts.map(o => <option key={o.v} value={o.v}>{o.l}</option>)}
        </select>
        <Icon d="chev" size={14} />
      </div>
    </label>
  )
}

// ── Board ─────────────────────────────────────────────────────
export default function Board({ listings, onOpen, saved, onSave }) {
  const reduced = useReducedMotion()
  const [f, setF] = useState({
    q: '', cluster: 'All', city: 'All', type: 'All',
    sort: 'fresh', fresh24: false, today: false, paid: false, part: false,
  })
  const set = useCallback((k, v) => setF(p => ({ ...p, [k]: v })), [])
  const indexRef = useRef(null)

  // Memoised filter + sort (React best practice)
  const rows = useMemo(() => {
    const q = f.q.trim().toLowerCase()
    const filtered = listings.filter(x => {
      if (q) {
        const hay = (x.title + ' ' + x.org + ' ' + (x.tags || []).join(' ') + ' ' + (x.subchips || []).join(' ') + ' ' + x.cluster + ' ' + x.location).toLowerCase()
        if (!hay.includes(q)) return false
      }
      if (f.cluster !== 'All' && x.cluster !== f.cluster) return false
      if (f.city !== 'All' && x.location !== f.city) return false
      if (f.type !== 'All' && x.type !== f.type) return false
      if (f.fresh24 && x.hoursAgo >= 24) return false
      if (f.today && x.hoursAgo > 12) return false
      if (f.paid && !x.stipend) return false
      if (f.part && x.timing !== 'Part-time') return false
      return true
    })
    const sorted = filtered.toSorted
      ? filtered.toSorted((a, b) => f.sort === 'stipend' ? b.stipend - a.stipend : f.sort === 'grade' ? b.score - a.score : a.hoursAgo - b.hoursAgo)
      : [...filtered].sort((a, b) => f.sort === 'stipend' ? b.stipend - a.stipend : f.sort === 'grade' ? b.score - a.score : a.hoursAgo - b.hoursAgo)
    return sorted
  }, [f, listings])

  // GSAP stagger on row entrance
  useEffect(() => {
    if (reduced || !indexRef.current) return
    const rowEls = indexRef.current.querySelectorAll('.dk-row:not(.dk-row-head)')
    if (!rowEls.length) return
    const ctx = gsap.context(() => {
      gsap.from(rowEls, {
        opacity: 0, y: 7, stagger: .022, duration: .4, ease: 'power2.out',
        scrollTrigger: {
          trigger: indexRef.current,
          start: 'top 88%',
          once: true,
        },
        onComplete: () => rowEls.forEach(el => { el.style.opacity = '1'; el.style.transform = 'none' }),
      })
    }, indexRef)
    return () => ctx.revert()
  }, [reduced, rows])

  // Active filter pills
  const pills = []
  if (f.cluster !== 'All') pills.push({ k: 'cluster', v: 'All', l: f.cluster })
  if (f.city    !== 'All') pills.push({ k: 'city',    v: 'All', l: f.city    })
  if (f.type    !== 'All') pills.push({ k: 'type',    v: 'All', l: f.type    })
  ;[['fresh24','Under 24h'],['today','Today only'],['paid','Paid only'],['part','Part-time']]
    .forEach(([k, l]) => { if (f[k]) pills.push({ k, v: false, l }) })

  const reset = useCallback(() =>
    setF({ q: '', cluster: 'All', city: 'All', type: 'All', sort: f.sort, fresh24: false, today: false, paid: false, part: false })
  , [f.sort])

  return (
    <div className="dk-wrap dk-board">
      <div className="dk-board-mast">
        <div className="dk-topline" style={{ borderBottom: 'none', marginBottom: 6 }}>
          <span>SECTION B</span>
          <span className="dk-topline-c">THE INDEX</span>
          <span>{rows.length} OF {listings.length} LISTED</span>
        </div>
        <Rule />
        <h1 className="dk-board-title">The Index</h1>
        <p className="dk-board-deck">
          Every entry verified, open to students in India, and filed within the day. Search it, sort it, clip what you like.
        </p>
      </div>

      {/* filters */}
      <div className="dk-filters">
        <label className="dk-search">
          <Label style={{ color: 'var(--ink-70)' }}>Search</Label>
          <div className="dk-search-box">
            <Icon d="search" size={15} />
            <input
              value={f.q}
              onChange={e => set('q', e.target.value)}
              placeholder="role, company, skill…"
              aria-label="Search listings"
            />
          </div>
        </label>
        <div className="dk-filter-selects">
          <Sel label="Field"    value={f.cluster} onChange={v => set('cluster', v)} opts={[{ v: 'All', l: 'All fields' },    ...ROLE_CLUSTERS.map(c => ({ v: c, l: c }))]} />
          <Sel label="Location" value={f.city}    onChange={v => set('city', v)}    opts={[{ v: 'All', l: 'Anywhere' },       ...CITIES.map(c => ({ v: c, l: c }))]} />
          <Sel label="Type"     value={f.type}    onChange={v => set('type', v)}    opts={[{ v: 'All', l: 'Any' }, { v: 'Remote', l: 'Remote' }, { v: 'Hybrid', l: 'Hybrid' }, { v: 'Onsite', l: 'Onsite' }]} />
          <Sel label="Order"    value={f.sort}    onChange={v => set('sort', v)}    opts={[{ v: 'fresh', l: 'Freshest' }, { v: 'stipend', l: 'Highest stipend' }, { v: 'grade', l: 'Best graded' }]} />
        </div>
      </div>

      <div className="dk-toggles">
        {[['fresh24','Under 24h'],['today','Today only'],['paid','Paid only'],['part','Part-time']].map(([k, l]) => (
          <button key={k} className={'dk-toggle ' + (f[k] ? 'on' : '')} onClick={() => set(k, !f[k])}>{l}</button>
        ))}
        <span className="dk-toggles-spacer" />
        <span className="dk-updated">Updated 2h ago · <b>{rows.length}</b> listed</span>
      </div>

      {pills.length > 0 ? (
        <div className="dk-pills">
          <Label style={{ color: 'var(--ink-70)' }}>Filtering</Label>
          {pills.map((p, i) => (
            <button key={i} className="dk-pill" onClick={() => set(p.k, p.v)}>
              {p.l}<Icon d="x" size={12} w={2} />
            </button>
          ))}
          <button className="dk-pill-clear" onClick={reset}>clear all</button>
        </div>
      ) : null}

      {/* row list — content-visibility for perf on long lists */}
      <div className="dk-index" ref={indexRef} style={{ contentVisibility: 'auto' }}>
        <IndexHead />
        {rows.length > 0 ? rows.map((r, i) => (
          <ListingRow
            key={r.id}
            data={r}
            onOpen={onOpen}
            saved={saved.includes(r.id)}
            onSave={onSave}
            i={i}
            on={reduced}
          />
        )) : (
          <div className="dk-empty">
            <div className="dk-empty-mark">※</div>
            <h3>Nothing filed under those terms.</h3>
            <p>The board is quieter here. Loosen a filter — or wait for tomorrow's edition at eight.</p>
            <button className="dk-btn dk-btn-red" onClick={reset}>Reset the filters</button>
          </div>
        )}
      </div>
    </div>
  )
}

// Rule is used in home2 but imported from core — re-export for convenience
export { Rule } from './core.jsx'
