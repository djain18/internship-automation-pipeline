// ============================================================
// DISPATCH — Front page: Masthead (with scramble reveal),
// Process grid, Spike section.
// Awwwards animations:
//  - "going to press" masthead (opacity + translateY CSS)
//  - text scramble on the big title
//  - parallax on the hero numeral via GSAP
//  - GSAP ScrollTrigger stagger on process items
// ============================================================
import { useState, useEffect, useRef } from 'react'
import { gsap } from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'

import {
  useCountUp, useInView, useScramble, useParallax, useReducedMotion,
  Icon, Kicker, Label, Rule, DoubleRule, Stamp, Grade, OrgMark,
  rupee,
} from './core.jsx'
import { PROCESS, SPIKED, RAN } from '../lib/data.js'

gsap.registerPlugin(ScrollTrigger)

// ── Masthead ("going to press") ──────────────────────────────
export function Masthead({ go, reduced, pressed, edition }) {
  const [countRun, setCountRun] = useState(reduced)
  const figNumRef = useRef(null)

  // start count-up 620ms after masthead settles
  useEffect(() => {
    if (reduced) return
    const t = setTimeout(() => setCountRun(true), 620)
    return () => clearTimeout(t)
  }, [reduced])

  const n = useCountUp(edition.verifiedToday, countRun, reduced, 1100)
  const title = useScramble('Dispatch', pressed, reduced)

  // parallax on hero numeral
  useParallax(figNumRef, -50, reduced)

  const dateStr = new Date().toLocaleDateString('en-IN', {
    weekday: 'long', year: 'numeric', month: 'long', day: 'numeric',
    timeZone: 'Asia/Kolkata',
  })

  return (
    <header className="dk-wrap dk-masthead">
      {/* top folio */}
      <div className={'dk-topline ' + (pressed ? 'p' : '')} style={{ '--d': '.02s' }}>
        <span>VOL. {edition.vol} · No. {edition.no}</span>
        <span className="dk-topline-c">BENGALURU · EST. MMXXVI</span>
        <span>PRICE · FREE FOR STUDENTS</span>
      </div>
      <Rule draw on={pressed} style={{ margin: '10px 0 0' }} />

      {/* the name — scramble-settles into "Dispatch" */}
      <h1 className={'dk-title ' + (pressed ? 'p' : '')} style={{ '--d': '.10s' }}>
        {title}
      </h1>

      <div className={'dk-subtitle ' + (pressed ? 'p' : '')} style={{ '--d': '.18s' }}>
        <span className="dk-sub-side">Verified before dawn.</span>
        <span className="dk-sub-mid">— The Internship Edition —</span>
        <span className="dk-sub-side dk-sub-right">Delivered by eight.</span>
      </div>
      <DoubleRule draw on={pressed} />

      {/* dateline */}
      <div className={'dk-dateline ' + (pressed ? 'p' : '')} style={{ '--d': '.26s' }}>
        <span>{dateStr}</span>
        <span className="dk-dateline-mid">THE MORNING EDITION</span>
        <span>EIGHT O'CLOCK · IST</span>
      </div>

      {/* lead story */}
      <div className="dk-lead">
        <div className={'dk-lead-story ' + (pressed ? 'p' : '')} style={{ '--d': '.34s' }}>
          <Kicker>Today's Market</Kicker>
          <h2 className="dk-headline">
            Eighty-two roles cleared the desk this morning.
          </h2>
          <p className="dk-standfirst">
            <span className="dk-dropcap">W</span>e read every internship posted to LinkedIn overnight,
            spike the fee scams and the international listings, and print only what is real
            and open to students in India. The rest never reaches your inbox.
          </p>
          <div className="dk-lead-actions">
            <button className="dk-btn dk-btn-red dk-btn-magnetic" onClick={() => go('subscribe')}>
              Subscribe to the edition <Icon d="arrow" size={15} />
            </button>
            <button className="dk-btn dk-btn-ghost" onClick={() => go('index')}>
              Read the board
            </button>
          </div>
          <p className="dk-fineprint">
            <Icon d="lock" size={12} style={{ verticalAlign: '-2px', marginRight: 6 }} />
            Your address is used for the morning edition and nothing else. Unsubscribe any day.
          </p>
        </div>

        {/* hero numeral with parallax */}
        <aside className={'dk-lead-figure ' + (pressed ? 'p' : '')} style={{ '--d': '.42s' }}>
          <Label style={{ color: 'var(--ink-70)' }}>Verified &amp; in print today</Label>
          <div ref={figNumRef} className="dk-fig-num">{n}</div>
          <div className="dk-fig-caption">
            <Label style={{ color: 'var(--ink-70)' }}>real internships</Label>
            <span className="dk-fig-delta">▲ 6 more than yesterday</span>
          </div>
          <div className="dk-fig-grid">
            {[
              [edition.spikedToday, 'spiked today',      true ],
              [edition.indiaEligible + '%', 'India-eligible', false],
              ['< 6h',  'median freshness',  false],
              ['8:00',  'delivered, IST',    false],
            ].map(([v, l, red]) => (
              <div key={l} className="dk-fig-cell">
                <span className="dk-fig-cell-n" style={{ color: red ? 'var(--red)' : 'var(--ink)' }}>{v}</span>
                <Label style={{ color: 'var(--ink-70)' }}>{l}</Label>
              </div>
            ))}
          </div>
        </aside>
      </div>
    </header>
  )
}

// ── Section heading (rule draws on scroll) ───────────────────
export function SecHead({ kicker, title, right }) {
  const [ref, on] = useInView()
  return (
    <div className="dk-sechead" ref={ref}>
      <Rule draw on={on} />
      <div className="dk-sechead-row">
        <div>
          <Kicker>{kicker}</Kicker>
          <h2 className="dk-sectitle">{title}</h2>
        </div>
        {right ? right : null}
      </div>
    </div>
  )
}

// ── Process grid (GSAP stagger on scroll) ────────────────────
export function Process({ reduced }) {
  const containerRef = useRef(null)

  useEffect(() => {
    if (reduced || !containerRef.current) return
    const items = containerRef.current.querySelectorAll('.dk-proc')
    if (!items.length) return
    const ctx = gsap.context(() => {
      ScrollTrigger.create({
        trigger: containerRef.current,
        start: 'top 82%',
        once: true,
        onEnter: () => items.forEach(el => el.classList.add('on')),
      })
    }, containerRef)
    return () => ctx.revert()
  }, [reduced])

  return (
    <section className="dk-wrap dk-sec">
      <SecHead kicker="How the edition is made" title="From the wire to your inbox by eight." />
      <div className="dk-process" ref={containerRef}>
        {PROCESS.map((p) => (
          <article
            key={p.n}
            className={'dk-proc ' + (reduced ? 'on' : '')}
            style={reduced ? {} : { transitionDelay: `${PROCESS.indexOf(p) * 0.07}s` }}
          >
            <div className="dk-proc-n">{p.n}</div>
            <h3 className="dk-proc-head">{p.head}</h3>
            <p className="dk-proc-body">{p.body}</p>
            <div className="dk-proc-fig">
              <span className="dk-proc-fig-n" style={{ color: p.red ? 'var(--red)' : 'var(--ink)' }}>{p.figure}</span>
              <Label style={{ color: 'var(--ink-70)' }}>{p.figLabel}</Label>
            </div>
          </article>
        ))}
      </div>
    </section>
  )
}

// ── Spike section ─────────────────────────────────────────────
export function Spike({ listings, edition }) {
  // pick top listing as "what ran instead"
  const ran = listings && listings.length > 0
    ? listings[0]
    : RAN

  return (
    <section className="dk-wrap dk-sec">
      <SecHead kicker="What doesn't make the page" title="Three stories we spiked this morning." />
      <div className="dk-spike">
        <div className="dk-spike-killed">
          <div className="dk-spike-hd">
            <Label style={{ color: 'var(--red)' }}>The spike — killed at the desk</Label>
            <span className="dk-spike-count">−{edition ? edition.spikedToday : 287} today</span>
          </div>
          {SPIKED.map((s, i) => (
            <div className="dk-spike-row" key={i}>
              <div className="dk-spike-main">
                <span className="dk-spike-title">{s.title}</span>
                <span className="dk-spike-filed">{s.filed}</span>
              </div>
              <div className="dk-spike-side">
                <span className="dk-spike-reason">{s.reason}</span>
                <span className="dk-spike-note">{s.note}</span>
              </div>
            </div>
          ))}
        </div>

        <div className="dk-spike-ran">
          <Label style={{ color: 'var(--ink-70)' }}>What ran instead</Label>
          <div className="dk-ran-org">
            <OrgMark org={ran.org} size={30} />
            <div>
              <div className="dk-ran-title">{ran.title}</div>
              <div className="dk-ran-meta">{ran.org} · {ran.location}</div>
            </div>
          </div>
          <div className="dk-ran-figs">
            <span className="dk-ran-stipend">{rupee(ran.stipend)}<i>/mo</i></span>
            <Grade score={ran.score} />
          </div>
          <Stamp />
          <p className="dk-ran-note">{ran.note || `Real company · India-eligible · live link · graded ${ran.score}.`}</p>
        </div>
      </div>
    </section>
  )
}
