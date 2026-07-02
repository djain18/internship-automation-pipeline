// ============================================================
// DISPATCH — The Daily Drop, rendered as a printed broadsheet.
// 3D perspective tilt on the sheet (hover levels it).
// ============================================================
import { Kicker, Label, Icon, rupee, freshWord } from './core.jsx'

function DropBrief({ r, rank }) {
  return (
    <article className="bs-brief">
      <div className="bs-brief-rank">{String(rank).padStart(2, '0')}</div>
      <div className="bs-brief-main">
        <h4 className="bs-brief-title">{r.title}</h4>
        <div className="bs-brief-org">{r.org} · {r.location} · {r.type}</div>
        <p className="bs-brief-desc">{r.desc}</p>
        <div className="bs-brief-foot">
          <span className="bs-brief-stipend">{rupee(r.stipend)}<i>/mo</i></span>
          <span className="bs-brief-grade">graded {r.score}</span>
          <span className="bs-brief-fresh">{freshWord(r.hoursAgo)}</span>
        </div>
      </div>
    </article>
  )
}

export default function DailyDrop({ listings, edition, go }) {
  const top  = listings.slice(0, 6)
  const lead = top[0]
  const rest = top.slice(1)
  const avg  = top.length > 0
    ? Math.round(top.reduce((s, r) => s + (r.stipend || 0), 0) / top.length)
    : 0

  const today = new Date().toLocaleDateString('en-IN', {
    weekday: 'long', day: 'numeric', month: 'long', year: 'numeric',
    timeZone: 'Asia/Kolkata',
  }).toUpperCase()

  if (!lead) return null

  return (
    <div className="dk-wrap dk-droppage">
      <div className="dk-droppage-head">
        <Kicker>Sent today · 08:00 IST</Kicker>
        <h1 className="dk-droppage-title">The Daily Drop</h1>
        <p className="dk-droppage-deck">
          This is the edition that lands in your inbox each morning — set in type, printed on paper.
        </p>
      </div>

      {/* 3D perspective broadsheet */}
      <div className="bs-sheet-wrap">
        <div className="bs-sheet paper-grain">
          {/* masthead */}
          <div className="bs-topline">
            <span>VOL. {edition.vol} · No. {edition.no}</span>
            <span>{today}</span>
            <span>FOR YOU · BENGALURU</span>
          </div>
          <div className="bs-rule-d"><span /><span className="bs-rule-red" /></div>
          <h2 className="bs-name">The Daily Drop</h2>
          <div className="bs-motto">— Your morning edition of the internship market —</div>
          <div className="bs-rule-d"><span /><span className="bs-rule-red" /></div>

          {/* intro */}
          <p className="bs-intro">
            Good morning. The market opened with <b>{edition.verifiedToday} verified roles</b> and{' '}
            <b>{edition.spikedToday} spiked</b>. Here are the six freshest matched to your fields and cities.
          </p>

          {/* stat strip */}
          <div className="bs-stats">
            {[
              [edition.verifiedToday,  'verified today'    ],
              ['6',                    'selected for you'  ],
              [rupee(avg),             'average stipend'   ],
              ['100%',                 'India-eligible'    ],
            ].map(([v, l]) => (
              <div className="bs-stat" key={l}>
                <span className="bs-stat-n">{v}</span>
                <span className="bs-stat-l">{l}</span>
              </div>
            ))}
          </div>

          {/* lead pick */}
          <div className="bs-lead">
            <span className="bs-lead-tag">★ Lead pick</span>
            <div className="bs-lead-grid">
              <div>
                <h3 className="bs-lead-title">{lead.title}</h3>
                <div className="bs-lead-org">{lead.org} · {lead.location} · {lead.type}</div>
                <p className="bs-lead-desc">
                  <span className="dk-dropcap">{lead.desc[0]}</span>{lead.desc.slice(1)}
                </p>
              </div>
              <div className="bs-lead-side">
                <span className="bs-lead-stipend">{rupee(lead.stipend)}<i>/mo</i></span>
                <span className="bs-lead-grade">Graded {lead.score}/100</span>
                <span className="bs-lead-fresh">Filed {freshWord(lead.hoursAgo)}</span>
                <span className="bs-verified">✓ VERIFIED AT THE DESK</span>
              </div>
            </div>
          </div>

          <div className="bs-section-label">★ Also in today's edition</div>
          <div className="bs-briefs">
            {rest.map((r, i) => <DropBrief key={r.id} r={r} rank={i + 2} />)}
          </div>

          {/* footer */}
          <div className="bs-foot">
            <a className="bs-foot-btn" href="#" onClick={e => { e.preventDefault(); go('index') }}>
              Open the full board →
            </a>
            <p className="bs-foot-fine">
              Free for students, and meant to stay that way. One email a day, at most.<br />
              Unsubscribe any morning · dispatch.press
            </p>
          </div>
        </div>
      </div>

      <div className="dk-droppage-cta">
        <button className="dk-btn dk-btn-red dk-btn-lg dk-btn-magnetic" onClick={() => go('subscribe')}>
          <Icon d="mail" size={16} /> Have this delivered every morning
        </button>
      </div>
    </div>
  )
}
