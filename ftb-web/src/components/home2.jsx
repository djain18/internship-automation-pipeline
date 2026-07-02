// ============================================================
// DISPATCH — home lower half: Selections (featured listings),
// DropTeaser, Letters, Notes/FAQ, Colophon, Footer, Detail modal.
// ============================================================
import { useState, useRef, useEffect } from 'react'
import { gsap } from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'

import {
  Icon, Kicker, Label, Rule, Stamp, Grade, OrgMark, rupee, freshWord,
  useInView, useReducedMotion,
} from './core.jsx'
import { SecHead } from './home.jsx'
import { LETTERS, NOTES } from '../lib/data.js'
import { ListingRow, IndexHead } from './board.jsx'

gsap.registerPlugin(ScrollTrigger)

// ── TODAY'S SELECTIONS ───────────────────────────────────────
export function Selections({ listings, onOpen, saved, onSave, go, edition }) {
  const rows = listings.slice(0, 5)
  const containerRef = useRef(null)
  const reduced = useReducedMotion()

  // Stagger rows in on scroll
  useEffect(() => {
    if (reduced || !containerRef.current) return
    const rows = containerRef.current.querySelectorAll('.dk-row:not(.dk-row-head)')
    if (!rows.length) return
    const ctx = gsap.context(() => {
      ScrollTrigger.create({
        trigger: containerRef.current,
        start: 'top 85%',
        once: true,
        onEnter: () => rows.forEach(el => el.classList.add('on')),
      })
    }, containerRef)
    return () => ctx.revert()
  }, [reduced, listings])

  return (
    <section className="dk-wrap dk-sec" ref={containerRef}>
      <SecHead
        kicker="Today's selections"
        title="Highest-graded on the board."
        right={
          <button className="dk-readmore" onClick={() => go('index')}>
            All {edition ? edition.verifiedToday : listings.length} listings <Icon d="arrow" size={14} />
          </button>
        }
      />
      <div className="dk-index dk-index-feat">
        <IndexHead />
        {rows.map((r, i) => (
          <ListingRow
            key={r.id}
            data={r}
            onOpen={onOpen}
            saved={saved.includes(r.id)}
            onSave={onSave}
            i={i}
            on={reduced}
          />
        ))}
      </div>
    </section>
  )
}

// ── DAILY DROP TEASER ─────────────────────────────────────────
export function DropTeaser({ listings, go }) {
  const top = listings.slice(0, 4)
  return (
    <section className="dk-wrap dk-sec">
      <div className="dk-droptease-grid">
        <div>
          <Kicker>The Daily Drop</Kicker>
          <h2 className="dk-sectitle dk-droptease-title">
            A broadsheet, set in type and delivered at eight.
          </h2>
          <p className="dk-droptease-body">
            The five or six freshest, highest-graded roles matched to your fields and
            cities — laid out like a morning paper and read in under a minute.
          </p>
          <button className="dk-btn dk-btn-red dk-btn-magnetic" onClick={() => go('drop')}>
            <Icon d="mail" size={15} /> Read a sample edition
          </button>
        </div>
        <button className="dk-minipaper" onClick={() => go('drop')} aria-label="Open the Daily Drop">
          <div className="dk-minipaper-mast">
            <span className="dk-minipaper-name">The Daily Drop</span>
            <span className="dk-minipaper-date">MON · 08:00</span>
          </div>
          {top.map(r => (
            <div className="dk-minipaper-row" key={r.id}>
              <span>{r.title} · {r.org}</span>
              <span className="dk-minipaper-fig">{rupee(r.stipend)}</span>
            </div>
          ))}
          <div className="dk-minipaper-more">+ two more · tap to read the full edition</div>
        </button>
      </div>
    </section>
  )
}

// ── LETTERS ───────────────────────────────────────────────────
export function Letters() {
  return (
    <section className="dk-wrap dk-sec">
      <SecHead kicker="Letters to the editor" title="From our readers." />
      <div className="dk-letters">
        {LETTERS.map((l, i) => (
          <figure className="dk-letter" key={i}>
            <blockquote className="dk-letter-body">{l.body}</blockquote>
            <figcaption className="dk-letter-cap">
              <span className="dk-letter-name">{l.name}</span>
              <span className="dk-letter-meta">{l.meta}</span>
            </figcaption>
          </figure>
        ))}
      </div>
    </section>
  )
}

// ── NOTES (FAQ) ───────────────────────────────────────────────
export function Notes() {
  const [open, setOpen] = useState(0)
  return (
    <section className="dk-wrap dk-sec dk-notes-sec">
      <SecHead kicker="Notes" title="Questions, answered plainly." />
      <div className="dk-notes">
        {NOTES.map((it, i) => (
          <div className={'dk-note ' + (open === i ? 'open' : '')} key={i}>
            <button
              className="dk-note-q"
              onClick={() => setOpen(open === i ? -1 : i)}
              aria-expanded={open === i}
            >
              <span>{it.q}</span>
              <span className="dk-note-mark">{open === i ? '–' : '+'}</span>
            </button>
            <div className="dk-note-a" style={{ maxHeight: open === i ? 220 : 0 }}>
              <p>{it.a}</p>
            </div>
          </div>
        ))}
      </div>
    </section>
  )
}

// ── COLOPHON / FINAL CALL ─────────────────────────────────────
export function Colophon({ go }) {
  return (
    <section className="dk-wrap dk-sec">
      <div className="dk-finalcall">
        <Kicker>The next edition</Kicker>
        <h2 className="dk-finalcall-h">Tomorrow's roles are already on the wire.</h2>
        <p className="dk-finalcall-p">
          Be on the list before eight o'clock. Free for students, and meant to stay that way.
        </p>
        <button className="dk-btn dk-btn-red dk-btn-lg dk-btn-magnetic" onClick={() => go('subscribe')}>
          Subscribe to the edition <Icon d="arrow" size={16} />
        </button>
      </div>
    </section>
  )
}

// ── FOOTER ────────────────────────────────────────────────────
const NAV_ITEMS = [
  { id: 'home',      label: 'Front Page'  },
  { id: 'index',     label: 'The Index'   },
  { id: 'drop',      label: 'Daily Drop'  },
  { id: 'subscribe', label: 'Subscribe'   },
]

export function Footer({ go }) {
  return (
    <footer className="dk-footer">
      <div className="dk-wrap">
        <Rule strong />
        <div className="dk-colophon">
          <div className="dk-colophon-main">
            <div className="dk-colophon-name">Dispatch</div>
            <p>
              The internship market, reported daily. Printed every morning at eight for students
              across India. Real roles, no scams, no advertising.
            </p>
            <span className="dk-colophon-est">BENGALURU · EST. MMXXVI</span>
          </div>
          <nav className="dk-colophon-col">
            <Label style={{ color: 'var(--ink-70)' }}>Sections</Label>
            {NAV_ITEMS.map(n => (
              <button key={n.id} onClick={() => go(n.id)}>{n.label}</button>
            ))}
          </nav>
          <div className="dk-colophon-col">
            <Label style={{ color: 'var(--ink-70)' }}>The masthead</Label>
            <span>Free for students</span>
            <span>India-eligible only</span>
            <span>No data sold, ever</span>
            <span>One email a day, at most</span>
          </div>
        </div>
        <div className="dk-colophon-foot">
          <span>© MMXXVI Dispatch · dispatch.press</span>
          <span>Not affiliated with LinkedIn · Set in Instrument Serif &amp; Hanken Grotesk</span>
        </div>
      </div>
    </footer>
  )
}

// ── DETAIL MODAL ──────────────────────────────────────────────
export function Detail({ data, listings, onClose, saved, onSave, onOpenOther }) {
  const ref = useRef(null)
  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKey)
    document.body.style.overflow = 'hidden'
    ref.current && ref.current.focus()
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = ''
    }
  }, [onClose])

  if (!data) return null

  const more = listings.filter(r => r.cluster === data.cluster && r.id !== data.id).slice(0, 4)
  const facts = [
    { l: 'Eligibility', v: (data.experience || 'Fresher') + ' · open to students in India' },
    { l: 'Work',        v: data.type + ' · ' + data.timing },
    { l: 'Location',    v: data.location },
    { l: 'Term',        v: data.duration },
    { l: 'Apply by',    v: data.deadline },
    { l: 'Desk contact',v: data.editor || '—' },
    { l: 'Write to',    v: data.contact },
  ]

  return (
    <div className="dk-modal-scrim" onClick={onClose} role="dialog" aria-modal="true" aria-label={data.title + ' — ' + data.org}>
      <article
        className="dk-modal"
        ref={ref}
        tabIndex={-1}
        onClick={e => e.stopPropagation()}
      >
        <button className="dk-modal-x" onClick={onClose} aria-label="Close">
          <Icon d="x" size={18} />
        </button>

        <div className="dk-clip-head">
          <div className="dk-clip-folio">
            <span>THE INDEX · {data.cluster.toUpperCase()}</span>
            <span>FILED {freshWord(data.hoursAgo).toUpperCase()}</span>
          </div>
          <Rule strong style={{ margin: '8px 0 14px' }} />
          <Kicker>{data.org}</Kicker>
          <h2 className="dk-clip-title">{data.title}</h2>
          <div className="dk-clip-byline">
            <Stamp />
            <span>Graded {data.score} of 100 · edited by {data.editor || 'the desk'}</span>
          </div>
        </div>

        <div className="dk-clip-body">
          <div className="dk-clip-text">
            <div className="dk-clip-figs">
              <div>
                <span className="dk-clip-stipend">
                  {rupee(data.stipend)}<i>{data.stipend ? ' /mo' : ''}</i>
                </span>
                <Label style={{ color: 'var(--ink-70)' }}>monthly stipend</Label>
              </div>
              <Grade score={data.score} big />
            </div>
            <p className="dk-clip-lede">
              <span className="dk-dropcap">{data.desc[0]}</span>{data.desc.slice(1)}
            </p>
            <div className="dk-chips">
              <Label style={{ color: 'var(--ink-70)' }}>Also filed as</Label>
              <div className="dk-chips-row">
                {(data.subchips || []).map(s => <span key={s} className="dk-chip">{s}</span>)}
              </div>
            </div>
            <div className="dk-chips">
              <Label style={{ color: 'var(--ink-70)' }}>Adjacent fields</Label>
              <div className="dk-chips-row">
                {(data.similar || []).map(s => <span key={s} className="dk-chip dk-chip-red">{s}</span>)}
              </div>
            </div>
          </div>

          <aside className="dk-clip-box">
            <div className="dk-factbox">
              <Label style={{ color: 'var(--ink-70)' }}>The facts</Label>
              {facts.map(f => (
                <div className="dk-fact" key={f.l}>
                  <span className="dk-fact-l">{f.l}</span>
                  <span className="dk-fact-v">{f.v}</span>
                </div>
              ))}
              <div className="dk-tags-row">
                {(data.tags || []).map(t => <span key={t} className="dk-tag">{t}</span>)}
              </div>
            </div>
          </aside>
        </div>

        {more.length > 0 ? (
          <div className="dk-clip-more">
            <Label style={{ color: 'var(--ink-70)' }}>More in {data.cluster}</Label>
            {more.map(r => (
              <button key={r.id} className="dk-clip-more-row" onClick={() => onOpenOther(r)}>
                <span>{r.title} · <i>{r.org}</i></span>
                <span className="dk-clip-more-fig">{rupee(r.stipend)}</span>
              </button>
            ))}
          </div>
        ) : null}

        <div className="dk-clip-actions">
          <a
            className="dk-btn dk-btn-red dk-btn-lg"
            href={data.applyLink || data.postUrl || '#'}
            target={data.applyLink && data.applyLink !== '#' ? '_blank' : undefined}
            rel="noopener noreferrer"
          >
            Apply now <Icon d="arrowUR" size={15} />
          </a>
          <button
            className={'dk-icon-btn ' + (saved ? 'is-saved' : '')}
            onClick={() => onSave(data.id)}
            aria-label={saved ? 'Remove clip' : 'Clip this listing'}
          >
            <Icon d="book" size={17} style={{ fill: saved ? 'var(--red)' : 'none' }} />
          </button>
          <button className="dk-icon-btn" aria-label="Share">
            <Icon d="share" size={16} />
          </button>
        </div>
      </article>
    </div>
  )
}
