import { motion } from "framer-motion";
import { Radar, ShieldX, Sparkles, Send } from "lucide-react";

const STEPS = [
  {
    icon: Radar,
    n: "01",
    head: "We read the whole wire",
    body: "Every night a scraper pulls every internship posted across LinkedIn in the last 24 hours — hundreds of them, raw and unsorted, across ten fields.",
  },
  {
    icon: ShieldX,
    n: "02",
    head: "We spike the junk",
    body: "Registration-fee scams, “earn ₹5,000 a day” schemes, posts with no way to apply, and roles not open to students in India are thrown out.",
  },
  {
    icon: Sparkles,
    n: "03",
    head: "A model grades what's left",
    body: "An LLM reads each surviving post, pulls out the real role, company, stipend and apply link, and scores it on freshness and quality.",
  },
  {
    icon: Send,
    n: "04",
    head: "The best go to the board",
    body: "Only verified, fresh, India-eligible roles are published — here and to your inbox if you want them. Stale posts drop off automatically.",
  },
];

export default function HowItWorks({ stats }) {
  const verified = stats?.verifiedToday;
  const spiked = stats?.spikedToday;

  return (
    <section id="how-it-works" className="relative scroll-mt-20 overflow-hidden border-t border-border bg-paper">
      {/* A faint daybreak echo of the same treeline — the moment this copy is about. */}
      <div
        className="pointer-events-none absolute inset-x-0 top-0 h-56 bg-cover bg-[position:left_bottom] opacity-[0.22] mix-blend-multiply"
        style={{
          backgroundImage: "url(/hero-still.jpeg)",
          maskImage: "linear-gradient(to bottom, black, transparent)",
          WebkitMaskImage: "linear-gradient(to bottom, black, transparent)",
        }}
      />
      <div className="relative mx-auto max-w-3xl px-6 py-20 md:px-10">
        <div className="max-w-2xl">
          <span className="text-sm font-medium uppercase tracking-widest text-muted-foreground">
            How Rise works
          </span>
          <h2 className="mt-3 font-display text-4xl tracking-tight text-foreground md:text-5xl">
            An editor that never sleeps
          </h2>
          <p className="mt-3 text-muted-foreground">
            You shouldn't have to scroll past a hundred fake posts to find one real
            internship. So every night, between you going to bed and waking up, Rise does it
            for you.
          </p>
        </div>

        {/* A process, read top to bottom — not four unrelated tiles. */}
        <div className="mt-14 border-l border-border">
          {STEPS.map((s, i) => (
            <motion.div
              key={s.n}
              initial={{ opacity: 0, y: 8 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: "-80px" }}
              transition={{ duration: 0.35, delay: i * 0.05 }}
              className="relative border-b border-border py-8 pl-8 last:border-b-0 sm:pl-10"
            >
              <span className="absolute -left-[5px] top-9 h-2 w-2 rounded-full bg-foreground" />
              <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                <span className="font-body text-sm tabular-nums text-muted-foreground">{s.n}</span>
                <s.icon className="h-4 w-4 shrink-0 text-muted-foreground" strokeWidth={1.75} />
                <h3 className="font-display text-2xl tracking-tight text-foreground">{s.head}</h3>
              </div>
              <p className="mt-2 max-w-xl text-sm leading-relaxed text-muted-foreground">
                {s.body}
              </p>
            </motion.div>
          ))}
        </div>

        {(verified || spiked) && (
          <div className="mt-10 flex flex-wrap items-center gap-x-2 gap-y-1 border-t border-border pt-6 text-sm tabular-nums text-muted-foreground">
            {verified != null && (
              <span>
                <strong className="font-semibold text-foreground">{verified}</strong> verified tonight
              </span>
            )}
            {verified != null && spiked != null && <span aria-hidden>·</span>}
            {spiked != null && (
              <span>
                <strong className="font-semibold text-foreground">{spiked}</strong> scams &amp; junk spiked
              </span>
            )}
            <span aria-hidden>·</span>
            <span>
              <strong className="font-semibold text-foreground">100%</strong> India-eligible
            </span>
            <span aria-hidden>·</span>
            <span>
              <strong className="font-semibold text-foreground">Free</strong> for students, always
            </span>
          </div>
        )}
      </div>
    </section>
  );
}
