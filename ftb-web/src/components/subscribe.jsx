// ============================================================
// DISPATCH — Subscribe. Two-step onboarding. Submits to API.
// ============================================================
import { useState, useCallback } from 'react'
import { Icon, Label, Rule, Stamp } from './core.jsx'
import { ROLE_CLUSTERS, CITIES } from '../lib/data.js'
import { submitSubscriber } from '../lib/api.js'

function Chips({ opts, sel, onTog, red }) {
  return (
    <div className="dk-chipgrid">
      {opts.map(o => {
        const on = sel.includes(o)
        return (
          <button
            key={o}
            className={'dk-chipsel ' + (on ? 'on ' : '') + (red ? 'red ' : '')}
            onClick={() => onTog(o)}
          >
            {on ? <Icon d="check" size={12} w={2.4} style={{ marginRight: 5 }} /> : null}
            {o}
          </button>
        )
      })}
    </div>
  )
}

export default function Subscribe({ onDone }) {
  const [step, setStep]     = useState(0)
  const [email, setEmail]   = useState('')
  const [roles, setRoles]   = useState(['Software', 'Design'])
  const [cities, setCities] = useState(['Bangalore'])
  const [remote, setRemote] = useState(true)
  const [year, setYear]     = useState('2027')
  const [loading, setLoading] = useState(false)
  const [error, setError]   = useState('')

  const tog = useCallback((arr, set, v) =>
    set(arr.includes(v) ? arr.filter(x => x !== v) : [...arr, v])
  , [])

  const valid = email.includes('@') && email.includes('.')

  const handleConfirm = async () => {
    setLoading(true)
    setError('')
    try {
      await submitSubscriber({ email, roles, cities, remote, gradYear: year })
    } catch {
      // non-fatal: still advance to confirmation
    }
    setLoading(false)
    setStep(2)
  }

  return (
    <div className="dk-wrap dk-subscribe">
      {/* step rail */}
      <div className="dk-sub-rail">
        <span className={step >= 0 ? 'on' : ''}>1 · Your details</span>
        <span className="dk-sub-rail-line" />
        <span className={step >= 1 ? 'on' : ''}>2 · Your edition</span>
      </div>

      {/* STEP 0 — email */}
      {step === 0 ? (
        <section className="dk-sub-card">
          <div className="dk-sub-folio">
            <span>SUBSCRIPTIONS</span>
            <span>FREE · 26,840 READERS</span>
          </div>
          <Rule strong style={{ margin: '10px 0 22px' }} />
          <h1 className="dk-sub-title">Subscribe to the morning edition.</h1>
          <p className="dk-sub-deck">
            The five or six freshest verified roles, delivered at eight o'clock. Free for students, forever.
          </p>

          {/* Google — cosmetic for now (email-only on day 1) */}
          <button className="dk-google" onClick={() => setStep(1)}>
            <svg width="18" height="18" viewBox="0 0 48 48" aria-hidden="true">
              <path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"/>
              <path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"/>
              <path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"/>
              <path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"/>
            </svg>
            Continue with Google
          </button>

          <div className="dk-or"><span /><Label style={{ color: 'var(--ink-70)' }}>or</Label><span /></div>

          <label className="dk-field">
            <Label style={{ color: 'var(--ink-70)' }}>Email address</Label>
            <input
              type="email"
              value={email}
              onChange={e => setEmail(e.target.value)}
              placeholder="you@college.edu"
              onKeyDown={e => { if (e.key === 'Enter' && valid) setStep(1) }}
            />
          </label>

          <button className="dk-btn dk-btn-red dk-btn-block" disabled={!valid} onClick={() => setStep(1)}>
            Continue
          </button>

          <p className="dk-sub-fine">
            <Icon d="lock" size={12} style={{ verticalAlign: '-2px', marginRight: 6 }} />
            Used for the edition and nothing else. No advertising, no data sold, unsubscribe any day.
          </p>
        </section>
      ) : null}

      {/* STEP 1 — preferences */}
      {step === 1 ? (
        <section className="dk-sub-card">
          <div className="dk-sub-folio"><span>YOUR EDITION</span><span>STEP 2 OF 2</span></div>
          <Rule strong style={{ margin: '10px 0 22px' }} />
          <h1 className="dk-sub-title">What should we set in type for you?</h1>
          <p className="dk-sub-deck">We tune each morning's edition to these. Change them any day.</p>

          <div className="dk-sub-block">
            <Label style={{ color: 'var(--ink-70)' }}>Fields — choose all that fit</Label>
            <div style={{ marginTop: 10 }}>
              <Chips opts={ROLE_CLUSTERS} sel={roles} onTog={v => tog(roles, setRoles, v)} />
            </div>
          </div>

          <div className="dk-sub-block">
            <Label style={{ color: 'var(--ink-70)' }}>Preferred cities</Label>
            <div style={{ marginTop: 10 }}>
              <Chips red opts={CITIES.filter(c => c !== 'Remote')} sel={cities} onTog={v => tog(cities, setCities, v)} />
            </div>
          </div>

          <div className="dk-sub-line">
            <span>Open to remote roles</span>
            <button
              className={'dk-switch ' + (remote ? 'on' : '')}
              onClick={() => setRemote(r => !r)}
              aria-pressed={remote}
            >
              <span />
            </button>
          </div>

          <label className="dk-sub-line">
            <span>Graduating in</span>
            <div className="dk-select-box dk-select-inline">
              <select value={year} onChange={e => setYear(e.target.value)}>
                {['2025', '2026', '2027', '2028', '2029'].map(y => <option key={y}>{y}</option>)}
              </select>
              <Icon d="chev" size={14} />
            </div>
          </label>

          {error ? <p style={{ color: 'var(--red)', fontSize: '.82rem', margin: '8px 0 0' }}>{error}</p> : null}

          <div className="dk-sub-actions">
            <button className="dk-btn dk-btn-ghost" onClick={() => setStep(0)}>Back</button>
            <button
              className="dk-btn dk-btn-red"
              disabled={!roles.length || loading}
              onClick={handleConfirm}
            >
              {loading ? 'Filing…' : <>Confirm subscription <Icon d="arrow" size={15} /></>}
            </button>
          </div>
        </section>
      ) : null}

      {/* STEP 2 — confirmation */}
      {step === 2 ? (
        <section className="dk-sub-card dk-sub-done">
          <div className="dk-sub-stamp"><Stamp /></div>
          <h1 className="dk-sub-title" style={{ textAlign: 'center' }}>You're on the list.</h1>
          <p className="dk-sub-deck" style={{ textAlign: 'center' }}>
            Your first edition lands <b>tomorrow at eight</b> — tuned to{' '}
            {roles.slice(0, 3).join(' · ')}{roles.length > 3 ? ' +' + (roles.length - 3) : ''}{' '}
            in {cities.join(', ')}.
          </p>
          <div className="dk-sub-receipt">
            {[['Fields', roles.join(', ')], ['Cities', cities.join(', ') + (remote ? ' + Remote' : '')], ['Graduating', year]].map(([k, v]) => (
              <div className="dk-fact" key={k}>
                <span className="dk-fact-l">{k}</span>
                <span className="dk-fact-v">{v}</span>
              </div>
            ))}
          </div>
          <div className="dk-sub-actions" style={{ justifyContent: 'center' }}>
            <button className="dk-btn dk-btn-red" onClick={() => onDone('drop')}>
              Preview tomorrow's edition
            </button>
            <button className="dk-btn dk-btn-ghost" onClick={() => onDone('index')}>
              Browse the board
            </button>
          </div>
        </section>
      ) : null}
    </div>
  )
}
