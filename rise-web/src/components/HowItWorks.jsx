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
    <section id="how-it-works" className="scroll-mt-20 border-t border-border bg-secondary/30">
      <div className="mx-auto max-w-6xl px-6 py-20 md:px-10">
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

        <div className="mt-12 grid gap-6 md:grid-cols-2 lg:grid-cols-4">
          {STEPS.map((s, i) => (
            <motion.div
              key={s.n}
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: "-80px" }}
              transition={{ duration: 0.5, delay: i * 0.08 }}
              className="rounded-2xl border border-border bg-background p-6"
            >
              <div className="flex items-center justify-between">
                <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-secondary text-foreground">
                  <s.icon className="h-5 w-5" />
                </div>
                <span className="font-display text-2xl text-muted-foreground/50">{s.n}</span>
              </div>
              <h3 className="mt-5 text-lg font-semibold text-foreground">{s.head}</h3>
              <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{s.body}</p>
            </motion.div>
          ))}
        </div>

        {(verified || spiked) && (
          <div className="mt-10 flex flex-wrap gap-x-10 gap-y-3 text-sm text-muted-foreground">
            {verified != null && (
              <span>
                <strong className="font-semibold text-foreground">{verified}</strong> verified tonight
              </span>
            )}
            {spiked != null && (
              <span>
                <strong className="font-semibold text-foreground">{spiked}</strong> scams &amp; junk spiked
              </span>
            )}
            <span>
              <strong className="font-semibold text-foreground">100%</strong> India-eligible
            </span>
            <span>
              <strong className="font-semibold text-foreground">Free</strong> for students, always
            </span>
          </div>
        )}
      </div>
    </section>
  );
}
