// ============================================================
// DISPATCH — core: hooks, editorial atoms, custom cursor,
// count-up, scroll-reveal, hairline icons.
// ============================================================
import { useState, useEffect, useRef, useCallback } from 'react'
import { gsap } from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'

gsap.registerPlugin(ScrollTrigger)

// ── motion preference ──────────────────────────────────────
export function useReducedMotion() {
  const [r, setR] = useState(
    typeof window !== 'undefined' && window.matchMedia
      ? window.matchMedia('(prefers-reduced-motion: reduce)').matches : false
  )
  useEffect(() => {
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)')
    const fn = () => setR(mq.matches)
    mq.addEventListener('change', fn)
    return () => mq.removeEventListener('change', fn)
  }, [])
  return r
}

// ── count-up (cubic ease-out, fires once) ────────────────────
export function useCountUp(target, run, reduced, dur = 1200) {
  const [v, setV] = useState(reduced ? target : 0)
  const done = useRef(false)
  useEffect(() => {
    if (!run || done.current) return
    done.current = true
    if (reduced) { setV(target); return }
    const t0 = performance.now()
    let raf
    const tick = (t) => {
      const p = Math.min(1, (t - t0) / dur)
      const e = 1 - Math.pow(1 - p, 4) // ease-out quart
      setV(Math.round(target * e))
      if (p < 1) raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [run, target, reduced, dur])
  return v
}

// ── scroll into view (fires once, for CSS-transition reveals) ─
export function useInView(margin = '-12% 0px') {
  const ref = useRef(null)
  const [seen, setSeen] = useState(false)
  useEffect(() => {
    if (!ref.current) return
    const io = new IntersectionObserver(
      ([e]) => { if (e.isIntersecting) { setSeen(true); io.disconnect() } },
      { rootMargin: margin }
    )
    io.observe(ref.current)
    return () => io.disconnect()
  }, [margin])
  return [ref, seen]
}

// ── text scramble (letterpress settling effect) ──────────────
const CHARS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
export function useScramble(text, trigger, reduced) {
  const [display, setDisplay] = useState(text)
  useEffect(() => {
    if (!trigger || reduced) { setDisplay(text); return }
    let frame = 0
    const total = text.length * 4
    const id = setInterval(() => {
      setDisplay(
        text.split('').map((ch, i) => {
          if (ch === ' ') return ' '
          if (i < Math.floor(frame / 4)) return ch
          return CHARS[Math.floor(Math.random() * CHARS.length)]
        }).join('')
      )
      frame++
      if (frame > total) { clearInterval(id); setDisplay(text) }
    }, 28)
    return () => clearInterval(id)
  }, [trigger, text, reduced])
  return display
}

// ── GSAP stagger reveal on scroll ────────────────────────────
export function useStaggerReveal(containerRef, selector = '.dk-row', reduced = false) {
  useEffect(() => {
    if (reduced || !containerRef.current) return
    const els = containerRef.current.querySelectorAll(selector)
    if (!els.length) return
    const ctx = gsap.context(() => {
      gsap.from(els, {
        opacity: 0,
        y: 10,
        duration: .5,
        stagger: .028,
        ease: 'power2.out',
        scrollTrigger: {
          trigger: containerRef.current,
          start: 'top 88%',
          once: true,
        },
        onComplete: () => {
          els.forEach(el => { el.style.opacity = '1'; el.style.transform = 'none' })
        },
      })
    }, containerRef)
    return () => ctx.revert()
  }, [reduced, selector])
}

// ── GSAP parallax on a single element ───────────────────────
export function useParallax(ref, speed = -60, reduced = false) {
  useEffect(() => {
    if (reduced || !ref.current) return
    const ctx = gsap.context(() => {
      gsap.to(ref.current, {
        y: speed,
        ease: 'none',
        scrollTrigger: {
          trigger: ref.current,
          start: 'top bottom',
          end: 'bottom top',
          scrub: true,
        },
      })
    }, ref)
    return () => ctx.revert()
  }, [speed, reduced])
}

// ── GSAP magnetic button ─────────────────────────────────────
export function useMagnetic(ref, strength = 0.35) {
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const onMove = (e) => {
      const rect = el.getBoundingClientRect()
      const cx = rect.left + rect.width / 2
      const cy = rect.top + rect.height / 2
      const dx = (e.clientX - cx) * strength
      const dy = (e.clientY - cy) * strength
      gsap.to(el, { x: dx, y: dy, duration: .35, ease: 'power2.out' })
    }
    const onLeave = () => gsap.to(el, { x: 0, y: 0, duration: .55, ease: 'elastic.out(1,.4)' })
    el.addEventListener('mousemove', onMove)
    el.addEventListener('mouseleave', onLeave)
    return () => { el.removeEventListener('mousemove', onMove); el.removeEventListener('mouseleave', onLeave) }
  }, [strength])
}

export function rupee(n) { return n ? '₹' + n.toLocaleString('en-IN') : 'Unpaid' }
export function freshWord(h) { return h + 'h ago' }

// ── Hairline icons ────────────────────────────────────────────
const I = {
  arrow:   'M5 12h14M13 6l6 6-6 6',
  arrowUR: 'M7 17L17 7M9 7h8v8',
  check:   'M4 12l5 5L20 6',
  x:       'M6 6l12 12M18 6L6 18',
  search:  'M11 11m-7 0a7 7 0 1 0 14 0a7 7 0 1 0-14 0M20 20l-4-4',
  book:    'M6 4h12v16l-6-4-6 4z',
  mail:    'M3 6h18v12H3zM3 7l9 6 9-6',
  lock:    'M6 10V8a6 6 0 1 1 12 0v2M5 10h14v10H5z',
  chev:    'M6 9l6 6 6-6',
  share:   'M4 12v7h16v-7M12 3v12M8 7l4-4 4 4',
  menu:    'M3 12h18M3 6h18M3 18h18',
}
export function Icon({ d, size = 16, w = 1.6, style, className }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth={w} strokeLinecap="round" strokeLinejoin="round"
      style={style} className={className} aria-hidden="true">
      {I[d].split('M').filter(Boolean).map((seg, i) => <path key={i} d={'M' + seg} />)}
    </svg>
  )
}

// ── Editorial atoms ─────────────────────────────────────────
export function Kicker({ children, className = '', style = {} }) {
  return <span className={'dk-kicker ' + className} style={style}>{children}</span>
}
export function Label({ children, className = '', style = {} }) {
  return <span className={'dk-label ' + className} style={style}>{children}</span>
}
export function Rule({ draw, on, strong, style = {} }) {
  return (
    <div
      className={'dk-rule ' + (draw ? 'dk-draw ' : '') + (draw && on ? 'is-on ' : '')}
      style={{ background: strong ? 'var(--rule-strong)' : 'var(--rule)', ...style }}
      aria-hidden="true"
    />
  )
}
export function DoubleRule({ draw, on }) {
  return (
    <div className={'dk-doubrule ' + (draw ? 'dk-draw ' : '') + (draw && on ? 'is-on ' : '')} aria-hidden="true">
      <span style={{ height: 3, background: 'var(--ink)' }} />
      <span style={{ height: 1.5, background: 'var(--red)', marginTop: 3 }} />
    </div>
  )
}
export function Stamp({ small }) {
  return (
    <span className={'dk-stamp ' + (small ? 'dk-stamp-sm' : '')} aria-label="Verified">
      <Icon d="check" size={small ? 9 : 11} w={2.4} />
      <span>VERIFIED</span>
    </span>
  )
}
export function Grade({ score, big }) {
  return (
    <span className="dk-grade" title={`Desk grade ${score} of 100`}>
      <span className="dk-grade-n" style={big ? { fontSize: '1.5rem' } : null}>{score}</span>
      <span className="dk-grade-meter" aria-hidden="true">
        <span style={{ width: score + '%' }} />
      </span>
    </span>
  )
}
export function OrgMark({ org, size = 34 }) {
  const ini = org.replace(/[""]/g, '').split(/\s+/).map(w => w[0]).slice(0, 2).join('').toUpperCase()
  return <span className="dk-orgmark" style={{ width: size, height: size, fontSize: size * 0.34 }} aria-hidden="true">{ini}</span>
}
export function Wordmark({ onClick, scale = 1 }) {
  return (
    <button onClick={onClick} className="dk-wordmark" aria-label="Dispatch — front page">
      <span style={{ fontSize: 1.5 * scale + 'rem' }}>Dispatch</span>
      <span className="dk-wordmark-sq" aria-hidden="true" />
    </button>
  )
}

// ── Custom editorial cursor ──────────────────────────────────
export function Cursor() {
  const dotRef = useRef(null)
  const ringRef = useRef(null)
  const pos = useRef({ x: -100, y: -100 })
  const ring = useRef({ x: -100, y: -100 })

  useEffect(() => {
    const dot = dotRef.current
    const ringEl = ringRef.current
    if (!dot || !ringEl) return

    let raf
    const update = () => {
      // ring follows with spring lag
      ring.current.x += (pos.current.x - ring.current.x) * 0.14
      ring.current.y += (pos.current.y - ring.current.y) * 0.14
      dot.style.transform = `translate(${pos.current.x}px, ${pos.current.y}px) translate(-50%, -50%)`
      ringEl.style.transform = `translate(${ring.current.x}px, ${ring.current.y}px) translate(-50%, -50%)`
      raf = requestAnimationFrame(update)
    }
    raf = requestAnimationFrame(update)

    const onMove = (e) => {
      pos.current.x = e.clientX
      pos.current.y = e.clientY
    }

    const addHover = () => {
      document.querySelectorAll('a, button, [role="button"], .dk-row, select, input').forEach(el => {
        const isText = el.tagName === 'INPUT' || el.tagName === 'TEXTAREA'
        el.addEventListener('mouseenter', () => {
          dot.classList.toggle('is-link', !isText)
          dot.classList.toggle('is-text', isText)
        })
        el.addEventListener('mouseleave', () => {
          dot.classList.remove('is-link', 'is-text')
        })
      })
    }
    // Delay so DOM is fully ready
    const t = setTimeout(addHover, 600)
    window.addEventListener('mousemove', onMove, { passive: true })

    return () => {
      window.removeEventListener('mousemove', onMove)
      cancelAnimationFrame(raf)
      clearTimeout(t)
    }
  }, [])

  return (
    <>
      <div ref={dotRef} className="cursor" style={{ position: 'fixed', top: 0, left: 0 }} />
      <div ref={ringRef} className="cursor-ring" style={{ position: 'fixed', top: 0, left: 0 }} />
    </>
  )
}
